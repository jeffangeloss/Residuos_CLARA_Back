"""Capa de persistencia de CLARA+.

Concentra las operaciones que escriben o consultan el esquema 3FN para que las
rutas HTTP no manejen transacciones. Cada operación pública abre y cierra una
sola transacción: una declaración se guarda completa —cabecera, insumos,
pictogramas, observaciones y movimiento de kardex— o no se guarda.
"""

from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from core.catalogos import clave_persona, normalizar_tipo_envase
from core.codigos import codigo_formato, codigo_identificador, siguiente_secuencia, token_fecha
from core.db_models import (
    CategoriaULimaDB,
    DeclaracionInsumoDB,
    DeclaracionObservacionDB,
    DeclaracionPictogramaDB,
    DeclaracionResiduoDB,
    DependenciaDB,
    LaboratorioDB,
    MovimientoKardexDB,
    PersonaAliasDB,
    PersonaDB,
    RegistroDB,
    ReglaIncompatibilidadDB,
    TipoEnvaseDB,
    ahora_utc,
)
from core.models import (
    MOVIMIENTO_POR_TRANSICION,
    TRANSICIONES_PERMITIDAS,
    CambioEstadoRequest,
    ConfirmacionCategoriaRequest,
    DecisionClasificacion,
    EntradaResiduoRequest,
    EstadoResiduo,
    MotivoMovimiento,
    NivelConfianza,
    ResultadoClasificacion,
    RolPadron,
    TipoMovimiento,
    requiere_escalamiento,
)
from core.seeder_3fn import par_canonico


class DatoMaestroFaltante(RuntimeError):
    """La ontología en memoria referencia una categoría que no está sembrada."""


class TransicionInvalida(ValueError):
    """Se intentó un cambio de estado que el ciclo de vida no contempla."""


def _normalizar(texto: str) -> str:
    """Clave de comparación insensible a mayúsculas y espacios sobrantes.

    Se normaliza en Python y no con `lower()` de SQL porque el plegado de
    acentos depende de la colación con la que se creó la base: 'Química' y
    'QUÍMICA' coinciden bajo `es_ES.UTF-8` y no bajo `C`. Hacerlo aquí es lo que
    garantiza que dos instalaciones distintas resuelvan el mismo laboratorio.
    """
    return " ".join(texto.split()).casefold()


def _codigo_secuencial(db: Session, modelo, prefijo: str) -> str:
    """Código legible y estable para una entidad recién registrada."""
    total = db.query(modelo).count()
    return f"{prefijo}-{total + 1:04d}"


def resolver_dependencia(db: Session, nombre: str) -> DependenciaDB:
    """Busca una dependencia por nombre exacto normalizado, o la registra.

    Antes se buscaba con `ILIKE %nombre%`: escribir "Química" podía resolver a
    "Química Analítica" y asignar la declaración a otra dependencia.
    """
    objetivo = _normalizar(nombre)
    for dependencia in db.query(DependenciaDB).all():
        if _normalizar(dependencia.nombre) == objetivo:
            return dependencia

    dependencia = DependenciaDB(
        codigo=_codigo_secuencial(db, DependenciaDB, "DEP"),
        nombre=nombre.strip(),
    )
    db.add(dependencia)
    db.flush()
    return dependencia


def resolver_laboratorio(
    db: Session,
    nombre: str,
    dependencia: DependenciaDB,
    responsable_defecto: Optional[str] = None,
) -> LaboratorioDB:
    """Busca el laboratorio dentro de su dependencia, o lo registra allí.

    La búsqueda se acota a `dependencia`: un laboratorio homónimo de otra
    facultad no debe absorber declaraciones que no le corresponden.
    """
    objetivo = _normalizar(nombre)
    candidatos = db.query(LaboratorioDB).filter_by(dependencia_id=dependencia.id).all()
    for laboratorio in candidatos:
        if _normalizar(laboratorio.nombre) == objetivo:
            return laboratorio

    laboratorio = LaboratorioDB(
        codigo=_codigo_secuencial(db, LaboratorioDB, "LAB"),
        nombre=nombre.strip(),
        dependencia_id=dependencia.id,
        responsable_defecto=responsable_defecto,
    )
    db.add(laboratorio)
    db.flush()
    return laboratorio


def resolver_tipo_envase(db: Session, texto: Optional[str]) -> Optional[TipoEnvaseDB]:
    """Lleva una descripción de envase al tipo del catálogo, o devuelve None.

    Acepta tanto el nombre canónico que envía el móvil como una descripción
    libre, que es lo que trae el histórico con sus 50 variantes del mismo
    concepto. Si el texto no permite decidir, no se fuerza una coincidencia:
    un envase mal clasificado es peor que uno sin clasificar.
    """
    if not texto or not texto.strip():
        return None

    objetivo = _normalizar(texto)
    for tipo in db.query(TipoEnvaseDB).all():
        if _normalizar(tipo.nombre) == objetivo:
            return tipo

    canonico = normalizar_tipo_envase(texto)
    if canonico is None:
        return None
    objetivo = _normalizar(canonico)
    for tipo in db.query(TipoEnvaseDB).all():
        if _normalizar(tipo.nombre) == objetivo:
            return tipo
    return None


def buscar_persona(db: Session, nombre: str) -> Optional[PersonaDB]:
    """Encuentra a una persona del padrón por su nombre o por cualquier alias.

    Es lo que hace que "Javier Quino" y "Javier Quino Favero" resuelvan a la
    misma persona en lugar de a dos.
    """
    clave = clave_persona(nombre)
    if not clave:
        return None

    persona = db.query(PersonaDB).filter(PersonaDB.nombre_clave == clave).first()
    if persona:
        return persona

    alias = db.query(PersonaAliasDB).filter(PersonaAliasDB.alias_clave == clave).first()
    return alias.persona if alias else None


def registrar_persona(
    db: Session,
    nombre: str,
    dependencia: Optional[str] = None,
    correo: Optional[str] = None,
    telefono: Optional[str] = None,
    es_encargado: bool = False,
    es_csbqr: bool = False,
    es_generador: bool = True,
) -> PersonaDB:
    """Da de alta a alguien que no estaba en el padrón, o devuelve al existente.

    El catálogo no es cerrado: quien no esté sembrado se registra sobre la
    marcha y queda con `en_catalogo_oficial` en falso, visible para el CSBQR.
    """
    try:
        existente = buscar_persona(db, nombre)
        if existente:
            # Los papeles se acumulan: quien ya estaba como generador y ahora
            # firma como encargado es la misma persona con un papel más.
            existente.es_encargado = existente.es_encargado or es_encargado
            existente.es_csbqr = existente.es_csbqr or es_csbqr
            existente.es_generador = existente.es_generador or es_generador
            db.commit()
            db.refresh(existente)
            return existente

        limpio = " ".join(nombre.split())
        dependencia_db = resolver_dependencia(db, dependencia) if dependencia else None
        persona = PersonaDB(
            codigo=_codigo_secuencial(db, PersonaDB, "PER"),
            nombre=limpio,
            nombre_clave=clave_persona(limpio),
            correo=(correo or "").strip() or None,
            telefono=(telefono or "").strip() or None,
            dependencia_id=dependencia_db.id if dependencia_db else None,
            es_encargado=es_encargado,
            es_csbqr=es_csbqr,
            es_generador=es_generador,
            en_catalogo_oficial=False,
        )
        db.add(persona)
        db.commit()
        db.refresh(persona)
        return persona
    except Exception:
        db.rollback()
        raise


def filtrar_personal(
    db: Session,
    rol: Optional[RolPadron] = None,
    dependencia: Optional[str] = None,
    busqueda: Optional[str] = None,
    solo_activos: bool = True,
) -> List[PersonaDB]:
    """Padrón para los desplegables del móvil, en orden alfabético."""
    consulta = db.query(PersonaDB).options(joinedload(PersonaDB.dependencia))

    if solo_activos:
        consulta = consulta.filter(PersonaDB.activo.is_(True))
    if rol is RolPadron.ENCARGADO:
        consulta = consulta.filter(PersonaDB.es_encargado.is_(True))
    elif rol is RolPadron.CSBQR:
        consulta = consulta.filter(PersonaDB.es_csbqr.is_(True))
    elif rol is RolPadron.GENERADOR:
        consulta = consulta.filter(PersonaDB.es_generador.is_(True))

    personas = consulta.all()

    if dependencia:
        objetivo = _normalizar(dependencia)
        # Quien no tiene dependencia asignada es personal del CSBQR, que
        # atiende todos los laboratorios: filtrarlo fuera dejaría al móvil sin
        # nadie a quien atribuir la elaboración de la declaración.
        personas = [
            p for p in personas
            if p.dependencia is None or _normalizar(p.dependencia.nombre) == objetivo
        ]
    if busqueda:
        clave = clave_persona(busqueda)
        personas = [
            p for p in personas
            if clave in p.nombre_clave
            or any(clave in a.alias_clave for a in p.alias)
        ]

    return sorted(personas, key=lambda p: p.nombre_clave)


def _secuencia_libre(db: Session, columna, momento: date) -> int:
    """Primer correlativo libre para una fecha, mirando los códigos ya emitidos."""
    prefijo = token_fecha(momento)
    usados = {
        valor for (valor,) in db.query(columna).filter(columna.like(f"{prefijo}%")).all()
    }
    return siguiente_secuencia(usados, momento)


def crear_registro(
    db: Session,
    dependencia: str,
    laboratorio: str,
    responsable_encargado: str,
    fecha: date,
    elaborado_por: Optional[str] = None,
    telefono_contacto: Optional[str] = None,
    comentarios_generales: Optional[str] = None,
) -> RegistroDB:
    """Abre la cabecera de una visita. Los residuos se declaran contra ella."""
    try:
        dependencia_db = resolver_dependencia(db, dependencia)
        laboratorio_db = resolver_laboratorio(
            db, laboratorio, dependencia_db, responsable_encargado
        )

        registro = RegistroDB(
            codigo=codigo_identificador(
                fecha, _secuencia_libre(db, RegistroDB.codigo, fecha), responsable_encargado
            ),
            laboratorio_id=laboratorio_db.id,
            responsable_encargado=responsable_encargado.strip(),
            elaborado_por=(elaborado_por or "").strip() or None,
            fecha=fecha,
            telefono_contacto=(telefono_contacto or "").strip() or None,
            comentarios_generales=(comentarios_generales or "").strip() or None,
        )
        db.add(registro)
        db.commit()
        db.refresh(registro)
        return registro
    except Exception:
        db.rollback()
        raise


def buscar_registro(db: Session, codigo: str) -> Optional[RegistroDB]:
    return (
        db.query(RegistroDB)
        .options(joinedload(RegistroDB.laboratorio).joinedload(LaboratorioDB.dependencia))
        .filter(RegistroDB.codigo == codigo)
        .first()
    )


def resolver_registro_para_entrada(
    db: Session, entrada: EntradaResiduoRequest
) -> RegistroDB:
    """Encuentra o abre el registro que corresponde a una captura suelta.

    Sostiene el endpoint `/clasificar` heredado, que recibe la cabecera repetida
    en cada residuo. Agrupa por laboratorio, responsable y fecha, que es el
    criterio con el que el proceso real separa una visita de otra.
    """
    dependencia = resolver_dependencia(db, entrada.dependencia)
    laboratorio = resolver_laboratorio(
        db, entrada.laboratorio, dependencia, entrada.responsable
    )
    objetivo = _normalizar(entrada.responsable)

    candidatos = (
        db.query(RegistroDB)
        .filter(RegistroDB.laboratorio_id == laboratorio.id, RegistroDB.fecha == entrada.fecha)
        .all()
    )
    for registro in candidatos:
        if _normalizar(registro.responsable_encargado) == objetivo:
            return registro

    registro = RegistroDB(
        codigo=codigo_identificador(
            entrada.fecha,
            _secuencia_libre(db, RegistroDB.codigo, entrada.fecha),
            entrada.responsable,
        ),
        laboratorio_id=laboratorio.id,
        responsable_encargado=entrada.responsable,
        elaborado_por=entrada.elaborado_por,
        fecha=entrada.fecha,
    )
    db.add(registro)
    db.flush()
    return registro


def registrar_movimiento(
    db: Session,
    declaracion: DeclaracionResiduoDB,
    tipo: TipoMovimiento,
    motivo: MotivoMovimiento,
    registrado_por: str,
    cantidad_g: float = 0.0,
    laboratorio_origen_id: Optional[int] = None,
    laboratorio_destino_id: Optional[int] = None,
    observacion: Optional[str] = None,
) -> MovimientoKardexDB:
    """Añade un movimiento de kardex a la sesión activa (sin confirmarla)."""
    movimiento = MovimientoKardexDB(
        declaracion_id=declaracion.id,
        tipo_movimiento=tipo.value,
        motivo=motivo.value,
        cantidad_g=cantidad_g,
        laboratorio_origen_id=laboratorio_origen_id,
        laboratorio_destino_id=laboratorio_destino_id,
        registrado_por=registrado_por,
        observacion=observacion,
    )
    db.add(movimiento)
    return movimiento


def crear_declaracion(
    db: Session,
    entrada: EntradaResiduoRequest,
    resultado: ResultadoClasificacion,
    registro: Optional[RegistroDB] = None,
) -> DeclaracionResiduoDB:
    """Persiste una declaración completa en una única transacción.

    Si no se indica registro, se resuelve o se abre uno a partir de la propia
    entrada, que es como sigue funcionando el endpoint heredado.

    Si cualquier paso falla, la transacción se revierte entera: nunca queda una
    cabecera de declaración sin sus insumos, pictogramas y movimiento inicial.
    """
    try:
        if registro is None:
            registro = resolver_registro_para_entrada(db, entrada)
        laboratorio = registro.laboratorio

        # La categoría debe existir por siembra de datos maestros. Crearla aquí
        # enmascararía una ontología desincronizada con la base.
        categoria = db.get(CategoriaULimaDB, resultado.categoria_id)
        if categoria is None:
            raise DatoMaestroFaltante(
                f"La categoría '{resultado.categoria_id}' no está sembrada. "
                "Ejecute la siembra de datos maestros antes de clasificar."
            )

        # Los códigos definitivos los asigna la base, que es quien conoce los
        # correlativos. El identificador que trae el resultado del clasificador
        # se reemplaza y se devuelve al cliente ya definitivo.
        codigo_residuo = codigo_identificador(
            entrada.fecha,
            _secuencia_libre(db, DeclaracionResiduoDB.codigo_residuo, entrada.fecha),
            entrada.responsable,
        )
        correlativo = (
            db.query(func.count(DeclaracionResiduoDB.id))
            .filter(DeclaracionResiduoDB.registro_id == registro.id)
            .scalar()
        ) + 1
        resultado.id_residuo = codigo_residuo
        envase = resolver_tipo_envase(db, entrada.tipo_envase)

        declaracion = DeclaracionResiduoDB(
            codigo_residuo=codigo_residuo,
            codigo_formato=codigo_formato(
                entrada.fecha, entrada.estado_fisico.value, correlativo
            ),
            registro_id=registro.id,
            categoria_id=categoria.id,
            actividad=entrada.actividad,
            origen=entrada.origen.value,
            responsable=entrada.responsable,
            fecha=entrada.fecha,
            descripcion=entrada.descripcion,
            nombre_normalizado=resultado.nombre_normalizado,
            estado_fisico=entrada.estado_fisico.value,
            foto_url=entrada.foto_url,
            tipo_envase_id=envase.id if envase else None,
            ancho_cm=entrada.ancho_cm,
            alto_cm=entrada.alto_cm,
            profundidad_cm=entrada.profundidad_cm,
            cantidad=resultado.cantidad,
            unidad=resultado.unidad.value,
            modo_medicion=resultado.modo_medicion.value,
            peso_bruto_g=resultado.peso_bruto_g,
            tara_g=resultado.tara_g,
            peso_neto_g=resultado.peso_neto_g,
            ph=entrada.ph,
            es_punzocortante=entrada.es_punzocortante,
            es_biologico=entrada.es_biologico,
            es_aerosol=entrada.es_aerosol,
            es_envase_vacio=entrada.es_envase_vacio,
            desconocido=entrada.desconocido,
            confianza=resultado.confianza.value,
            estado=(
                EstadoResiduo.EN_EVALUACION.value if resultado.escalar_csbqr
                else EstadoResiduo.GENERADO.value
            ),
            escalar_csbqr=resultado.escalar_csbqr,
            narrativa=resultado.narrativa,
            # Nace como propuesta sin confirmar: la categoría vigente y la
            # propuesta son la misma hasta que alguien la revise.
            categoria_propuesta_id=categoria.id,
            clasificacion_confirmada=False,
        )
        db.add(declaracion)
        db.flush()

        for nombre_quimico in entrada.insumos:
            db.add(DeclaracionInsumoDB(
                declaracion_id=declaracion.id, nombre_quimico=nombre_quimico
            ))

        for codigo in dict.fromkeys(resultado.pictogramas_ghs):
            db.add(DeclaracionPictogramaDB(
                declaracion_id=declaracion.id, codigo_pictograma=codigo
            ))

        for texto in dict.fromkeys(resultado.observaciones):
            db.add(DeclaracionObservacionDB(declaracion_id=declaracion.id, texto=texto))

        # Toda declaración nace con su movimiento de entrada: el kardex arranca
        # en el mismo instante que el residuo.
        registrar_movimiento(
            db,
            declaracion,
            tipo=TipoMovimiento.ENTRADA,
            motivo=MotivoMovimiento.GENERACION_LAB,
            registrado_por=entrada.responsable,
            cantidad_g=resultado.peso_neto_g,
            laboratorio_destino_id=laboratorio.id,
            observacion=f"Generación declarada en {laboratorio.nombre}",
        )

        db.commit()
        db.refresh(declaracion)
        return declaracion

    except Exception:
        db.rollback()
        raise


def cambiar_estado(
    db: Session,
    declaracion: DeclaracionResiduoDB,
    peticion: CambioEstadoRequest,
) -> MovimientoKardexDB:
    """Avanza el ciclo de vida del residuo y deja constancia en el kardex.

    El cambio de estado y su movimiento se confirman juntos: un residuo no puede
    aparecer como trasladado sin que exista el movimiento que lo respalda.
    """
    estado_actual = EstadoResiduo(declaracion.estado)
    destino = peticion.estado_destino

    if destino == estado_actual:
        raise TransicionInvalida(f"La declaración ya está en estado {destino.value}")

    permitidos = TRANSICIONES_PERMITIDAS[estado_actual]
    if destino not in permitidos:
        opciones = ", ".join(sorted(e.value for e in permitidos)) or "ninguno"
        raise TransicionInvalida(
            f"No se permite pasar de {estado_actual.value} a {destino.value}. "
            f"Destinos válidos: {opciones}."
        )

    try:
        laboratorio_origen = declaracion.registro.laboratorio
        laboratorio_destino_id = None
        if peticion.laboratorio_destino:
            destino_lab = resolver_laboratorio(
                db, peticion.laboratorio_destino, laboratorio_origen.dependencia
            )
            laboratorio_destino_id = destino_lab.id

        tipo, motivo = MOVIMIENTO_POR_TRANSICION[destino]
        movimiento = registrar_movimiento(
            db,
            declaracion,
            tipo=tipo,
            motivo=motivo,
            registrado_por=peticion.registrado_por,
            cantidad_g=declaracion.peso_neto_g,
            laboratorio_origen_id=laboratorio_origen.id,
            laboratorio_destino_id=laboratorio_destino_id,
            observacion=(
                peticion.observacion
                or f"Cambio de estado {estado_actual.value} → {destino.value}"
            ),
        )
        declaracion.estado = destino.value
        db.commit()
        db.refresh(movimiento)
        return movimiento

    except Exception:
        db.rollback()
        raise


def confirmar_clasificacion(
    db: Session,
    declaracion: DeclaracionResiduoDB,
    peticion: ConfirmacionCategoriaRequest,
) -> DeclaracionResiduoDB:
    """Registra que un humano aceptó o corrigió la categoría propuesta.

    La propuesta original nunca se pierde: `categoria_propuesta_id` conserva lo
    que dedujo el sistema y `categoria_id` pasa a ser lo que decidió la persona.
    Comparar ambas columnas es lo que permite medir el acierto del clasificador
    con residuos reales, en vez de suponerlo.

    Una corrección puede además sacar al residuo de evaluación: si el sistema
    lo escaló al CSBQR por no identificarlo y alguien reconoce la categoría, el
    motivo del escalamiento deja de existir.
    """
    if declaracion.estado == EstadoResiduo.DISPUESTO.value:
        raise TransicionInvalida(
            "El residuo ya fue entregado al operador: su clasificación no puede "
            "cambiarse, porque es la que salió declarada."
        )

    try:
        categoria_previa = declaracion.categoria

        if peticion.decision is DecisionClasificacion.CORREGIDA:
            categoria = db.get(CategoriaULimaDB, peticion.categoria_id)
            if categoria is None:
                raise DatoMaestroFaltante(
                    f"La categoría '{peticion.categoria_id}' no existe en la ontología"
                )
            if categoria.id == declaracion.categoria_id:
                raise ValueError(
                    "La categoría indicada es la que ya tiene la declaración: "
                    "para dejarla como está, la decisión es 'aceptada'"
                )

            declaracion.categoria_id = categoria.id
            # Una categoría elegida por una persona no es una deducción: es la
            # decisión de quien tiene el residuo delante.
            declaracion.confianza = NivelConfianza.ALTO.value
            declaracion.escalar_csbqr = requiere_escalamiento(
                categoria.id, declaracion.desconocido
            )
            # El estado solo se toca si el residuo sigue en el laboratorio. Uno
            # ya trasladado o almacenado no vuelve atrás porque se corrija su
            # etiqueta: el kardex dice dónde está y esto no lo mueve.
            if declaracion.estado in (
                EstadoResiduo.GENERADO.value,
                EstadoResiduo.EN_EVALUACION.value,
            ):
                declaracion.estado = (
                    EstadoResiduo.EN_EVALUACION.value if declaracion.escalar_csbqr
                    else EstadoResiduo.GENERADO.value
                )

            detalle = (
                f"Clasificación corregida: {categoria_previa.nombre} → {categoria.nombre}"
            )
        else:
            detalle = f"Clasificación confirmada: {categoria_previa.nombre}"

        declaracion.clasificacion_confirmada = True
        declaracion.confirmada_por = peticion.confirmada_por
        declaracion.confirmada_en = ahora_utc()

        if peticion.motivo:
            detalle = f"{detalle}. {peticion.motivo}"

        # La revisión queda en el kardex, que es donde se lee la historia del
        # residuo. Un ajuste sin movimiento sería un cambio sin rastro.
        registrar_movimiento(
            db,
            declaracion,
            tipo=TipoMovimiento.AJUSTE,
            motivo=MotivoMovimiento.CORRECCION,
            registrado_por=peticion.confirmada_por,
            cantidad_g=None,
            laboratorio_origen_id=declaracion.registro.laboratorio_id,
            observacion=detalle,
        )

        db.commit()
        db.refresh(declaracion)
        return declaracion

    except Exception:
        db.rollback()
        raise


def kardex_de(db: Session, declaracion: DeclaracionResiduoDB) -> List[MovimientoKardexDB]:
    """Traza de custodia completa de un residuo, en orden cronológico."""
    return (
        db.query(MovimientoKardexDB)
        .options(
            joinedload(MovimientoKardexDB.laboratorio_origen),
            joinedload(MovimientoKardexDB.laboratorio_destino),
        )
        .filter(MovimientoKardexDB.declaracion_id == declaracion.id)
        .order_by(MovimientoKardexDB.registrado_en.asc(), MovimientoKardexDB.id.asc())
        .all()
    )


def buscar_declaracion(db: Session, codigo_residuo: str) -> Optional[DeclaracionResiduoDB]:
    """Recupera una declaración por su código de residuo."""
    return (
        db.query(DeclaracionResiduoDB)
        .filter(DeclaracionResiduoDB.codigo_residuo == codigo_residuo)
        .first()
    )


def consulta_declaraciones(db: Session, codigos: Optional[Sequence[str]] = None):
    """Consulta base con las relaciones precargadas para evitar N+1."""
    consulta = (
        db.query(DeclaracionResiduoDB)
        .options(
            joinedload(DeclaracionResiduoDB.registro)
            .joinedload(RegistroDB.laboratorio)
            .joinedload(LaboratorioDB.dependencia),
            joinedload(DeclaracionResiduoDB.categoria),
            joinedload(DeclaracionResiduoDB.insumos),
            joinedload(DeclaracionResiduoDB.pictogramas),
            joinedload(DeclaracionResiduoDB.observaciones),
        )
        .order_by(DeclaracionResiduoDB.fecha.asc(), DeclaracionResiduoDB.creado_en.asc())
    )
    if codigos:
        consulta = consulta.filter(DeclaracionResiduoDB.codigo_residuo.in_(list(codigos)))
    return consulta


def _rango_del_mes(mes: int, anio: int) -> Tuple[date, date]:
    """Primer día del mes y primer día del mes siguiente (fin exclusivo)."""
    inicio = date(anio, mes, 1)
    fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return inicio, fin


def filtrar_declaraciones(
    db: Session,
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    laboratorio: Optional[str] = None,
    categoria_id: Optional[str] = None,
    estado: Optional[str] = None,
    escalar_csbqr: Optional[bool] = None,
    limite: int = 100,
    desplazamiento: int = 0,
) -> Tuple[List[DeclaracionResiduoDB], int]:
    """Historial filtrado de la RF-08. Devuelve la página y el total sin paginar.

    `mes` requiere `anio`; un mes suelto no identifica un período y se ignora
    en vez de filtrar por un año arbitrario.
    """
    # El historial se lee de lo más reciente a lo más antiguo (RF-01 muestra las
    # declaraciones recientes); la consulta base ordena ascendente porque sirve a
    # las exportaciones, donde el orden cronológico es el esperado.
    consulta = consulta_declaraciones(db).order_by(None).order_by(
        DeclaracionResiduoDB.fecha.desc(), DeclaracionResiduoDB.creado_en.desc()
    )

    if anio is not None:
        if mes is not None:
            inicio, fin = _rango_del_mes(mes, anio)
        else:
            inicio, fin = date(anio, 1, 1), date(anio + 1, 1, 1)
        consulta = consulta.filter(
            DeclaracionResiduoDB.fecha >= inicio, DeclaracionResiduoDB.fecha < fin
        )

    if laboratorio:
        # Se resuelve por identidad del laboratorio, no por coincidencia parcial
        # de texto, para no arrastrar declaraciones de un laboratorio homónimo.
        # El laboratorio vive ahora en la cabecera del registro.
        objetivo = _normalizar(laboratorio)
        ids = [
            fila.id for fila in db.query(LaboratorioDB).all()
            if _normalizar(fila.nombre) == objetivo
        ]
        registros = [
            fila.id for fila in
            db.query(RegistroDB).filter(RegistroDB.laboratorio_id.in_(ids or [-1])).all()
        ]
        # Sin coincidencias el filtro no debe degradarse a "todos".
        consulta = consulta.filter(DeclaracionResiduoDB.registro_id.in_(registros or [-1]))

    if categoria_id:
        consulta = consulta.filter(DeclaracionResiduoDB.categoria_id == categoria_id)

    if estado:
        consulta = consulta.filter(DeclaracionResiduoDB.estado == estado)

    if escalar_csbqr is not None:
        consulta = consulta.filter(DeclaracionResiduoDB.escalar_csbqr.is_(escalar_csbqr))

    total = consulta.order_by(None).count()
    pagina = consulta.limit(limite).offset(desplazamiento).all()
    return pagina, total


def filtrar_registros(
    db: Session,
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    laboratorio: Optional[str] = None,
    limite: int = 100,
    desplazamiento: int = 0,
) -> Tuple[List[RegistroDB], int]:
    """Historial de visitas, de la más reciente a la más antigua."""
    consulta = (
        db.query(RegistroDB)
        .options(
            joinedload(RegistroDB.laboratorio).joinedload(LaboratorioDB.dependencia),
            joinedload(RegistroDB.declaraciones),
        )
        .order_by(RegistroDB.fecha.desc(), RegistroDB.creado_en.desc())
    )

    if anio is not None:
        if mes is not None:
            inicio, fin = _rango_del_mes(mes, anio)
        else:
            inicio, fin = date(anio, 1, 1), date(anio + 1, 1, 1)
        consulta = consulta.filter(RegistroDB.fecha >= inicio, RegistroDB.fecha < fin)

    if laboratorio:
        objetivo = _normalizar(laboratorio)
        ids = [
            fila.id for fila in db.query(LaboratorioDB).all()
            if _normalizar(fila.nombre) == objetivo
        ]
        consulta = consulta.filter(RegistroDB.laboratorio_id.in_(ids or [-1]))

    total = consulta.order_by(None).count()
    return consulta.limit(limite).offset(desplazamiento).all(), total


def declaraciones_del_periodo(db: Session, mes: int, anio: int) -> List[DeclaracionResiduoDB]:
    """Declaraciones de un mes calendario, filtradas por rango de fechas real.

    Sustituye al filtro `fecha LIKE 'AAAA-MM%'`, que dependía de que todos los
    clientes escribieran la fecha con el mismo formato de texto.
    """
    inicio, fin = _rango_del_mes(mes, anio)
    return (
        consulta_declaraciones(db)
        .filter(DeclaracionResiduoDB.fecha >= inicio)
        .filter(DeclaracionResiduoDB.fecha < fin)
        .all()
    )


def matriz_incompatibilidad(db: Session) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """Lee la matriz completa desde la base, no desde memoria.

    La tabla es la fuente de verdad en tiempo de ejecución; el módulo del
    clasificador solo aporta los valores con los que se siembra.
    """
    return {
        par_canonico(regla.grupo_a, regla.grupo_b): (regla.veredicto, regla.explicacion_riesgo)
        for regla in db.query(ReglaIncompatibilidadDB).all()
    }


def pares_prohibidos(db: Session) -> List[Tuple[str, str, str]]:
    """Solo los pares con veredicto NUNCA, para reportes y pruebas."""
    return [
        (par[0], par[1], razon)
        for par, (veredicto, razon) in matriz_incompatibilidad(db).items()
        if veredicto == "NUNCA"
    ]


# Severidad de los veredictos: en un conjunto de residuos manda el peor.
_ORDEN_VEREDICTO = {"COMPATIBLE": 0, "SEGREGAR": 1, "NUNCA": 2}


def evaluar_compatibilidad(db: Session, grupos: Iterable[str]) -> dict:
    """Evalúa un conjunto de grupos contra la matriz CSBQR persistida.

    Cada pareja se resuelve con el veredicto almacenado. Un par ausente de la
    matriz se resuelve como SEGREGAR si los grupos son distintos, aplicando la
    regla por defecto del CSBQR: *"cuando no encuentre el par exacto o haya
    cualquier incertidumbre, debe recomendar segregar"*.
    """
    normalizados = [grupo.strip().upper() for grupo in grupos if grupo and grupo.strip()]
    if not normalizados:
        return {"veredicto": "SEGREGAR", "razon": "No se recibió ningún grupo de compatibilidad."}

    matriz = matriz_incompatibilidad(db)
    conflictos = []
    segregaciones = []

    for indice, grupo_a in enumerate(normalizados):
        for grupo_b in normalizados[indice + 1:]:
            par = par_canonico(grupo_a, grupo_b)
            if par in matriz:
                veredicto, razon = matriz[par]
            elif grupo_a == grupo_b:
                continue
            else:
                veredicto = "SEGREGAR"
                razon = "Par no contemplado en la matriz: segregar por precaución"

            detalle = {"a": grupo_a, "b": grupo_b, "veredicto": veredicto, "razon": razon}
            if veredicto == "NUNCA":
                conflictos.append(detalle)
            elif veredicto == "SEGREGAR":
                segregaciones.append(detalle)

    if conflictos:
        return {"veredicto": "NUNCA", "conflictos": conflictos}
    if segregaciones:
        return {
            "veredicto": "SEGREGAR",
            "razon": "Grupos químicos distintos: separar en bandejas o contenciones diferentes.",
            "conflictos": segregaciones,
        }
    return {"veredicto": "COMPATIBLE", "razon": "Mismo grupo de compatibilidad."}
