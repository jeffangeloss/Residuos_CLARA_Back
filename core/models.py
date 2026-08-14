"""
Modelos de Datos Pydantic y Esquemas API - Residuos Peligrosos CLARA+ ULima

Este módulo también define el vocabulario de dominio (orígenes, estados físicos,
niveles de confianza, estados del residuo y veredictos). Ese vocabulario es la
única fuente de verdad: la API lo valida con Pydantic y la base de datos lo
restringe con los mismos valores importados en `core/db_models.py`.
"""

from datetime import date
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator, model_validator

class TipoMovimiento(str, Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    TRANSFERENCIA = "TRANSFERENCIA"
    AJUSTE = "AJUSTE"

class MotivoMovimiento(str, Enum):
    GENERACION_LAB = "generacion_laboratorio"
    TRASLADO_ACOPIO = "traslado_acopio"
    ENTREGA_EORS = "entrega_eors"
    CENSO_INICIAL = "censo_inicial"
    CORRECCION = "correccion"

class EstadoResiduo(str, Enum):
    GENERADO = "GENERADO"
    EN_TRASLADO = "EN_TRASLADO"
    ALMACENADO = "ALMACENADO"
    DISPUESTO = "DISPUESTO"
    EN_EVALUACION = "EN_EVALUACION"

class Origen(str, Enum):
    ACADEMICO = "Académico"
    PROYECTO = "Proyecto"
    # El formato oficial y el formulario contemplan "Otros"; 7 registros
    # históricos lo usan.
    OTROS = "Otros"

class EstadoFisico(str, Enum):
    """Solo dos estados.

    Ni el formulario, ni el desplegable del formato 2026, ni ninguno de los 856
    registros históricos contemplan un tercer estado. "Gel / Lodo" existía solo
    en la interfaz web.
    """

    LIQUIDO = "Líquido"
    SOLIDO = "Sólido"


class Unidad(str, Enum):
    """Unidades del formato oficial.

    El Gem fija el kilogramo como unidad oficial —*"peso neto = peso del envase
    lleno − tara. Medir siempre en balanza"*— pero tanto el formulario como el
    desplegable del formato aceptan litros, y 277 de los 856 registros
    históricos los usan. El modelo conserva la unidad tal como se declaró.
    """

    KG = "Kg"
    L = "L"


class ModoMedicion(str, Enum):
    """Cómo se obtuvo la cantidad declarada.

    Distinguirlo importa: un kilogramo debería salir de una balanza. Si la
    cantidad se escribió a mano, la declaración es una estimación y conviene
    que se note.
    """

    PESAJE = "pesaje"          # peso bruto menos tara, en balanza
    DECLARADA = "declarada"    # cantidad escrita directamente


# ---------------------------------------------------------------------------
# Política de medición
#
# Decisión del 2026-08-13: toda declaración nueva se pesa en balanza y se
# declara en kilogramos, siguiendo la regla del Gem —"peso neto = peso del
# envase lleno − tara. Medir siempre en balanza"—.
#
# Es una política de captura, no del modelo: la base sigue admitiendo litros
# porque el formato oficial los acepta y porque los 277 registros históricos en
# litros tienen que poder importarse. Para volver a permitirlos en la captura
# basta con poner esta constante en False.
# ---------------------------------------------------------------------------
EXIGIR_PESAJE_EN_KG = True


class CaracteristicaDeclaracion(str, Enum):
    """Los 13 valores del desplegable "Clasificación" del formato 2026.

    Se transcriben literalmente de la hoja `Listas`: el Excel valida contra
    ellos y cualquier variación hace fallar la validación de datos.
    """

    CORROSIVIDAD = "Corrosividad"
    INFLAMABILIDAD = "Inflamabilidad"
    TOXICIDAD_INFLAMABILIDAD = "Toxicidad (+ inflamabilidad en algunos)"
    REACTIVIDAD_EXPLOSIVIDAD = "Reactividad (+ explosividad en peróxidos)"
    TOXICIDAD_ECOTOXICIDAD = "Toxicidad (+ ecotoxicidad)"
    INFLAMABILIDAD_TOXICIDAD = "Inflamabilidad (+ toxicidad)"
    REACTIVIDAD_PRESION = "Reactividad / inflamabilidad (por presión)"
    PATOGENICIDAD = "Patogenicidad"
    PATOGENICIDAD_CONTAMINANTE = "Patogenicidad (o la del contaminante)"
    TOXICIDAD = "Toxicidad"
    HEREDADA_CONTAMINANTE = "Heredada del contaminante"
    RADIOACTIVIDAD = "Radioactividad"
    EN_EVALUACION = "En evaluación"

class NivelConfianza(str, Enum):
    ALTO = "Alto"
    MEDIO = "Medio"
    BAJO = "Bajo"


class DecisionClasificacion(str, Enum):
    """Qué hizo el humano con la propuesta del clasificador.

    Distinguir aceptar de corregir es lo que permite saber si el clasificador
    sirve: si la mayoría de las propuestas se corrigen, las reglas están mal.
    Con la propuesta sobrescrita en silencio esa cifra no existía.
    """

    ACEPTADA = "aceptada"
    CORREGIDA = "corregida"


class RolPadron(str, Enum):
    """Papel de una persona en el proceso, para filtrar el padrón.

    No son excluyentes: quien encarga un laboratorio también genera residuos
    en él, y buena parte del personal del CSBQR hace las dos cosas.
    """

    ENCARGADO = "encargado"
    CSBQR = "csbqr"
    GENERADOR = "generador"

class RolUsuario(str, Enum):
    INVESTIGADOR = "investigador"
    LABORATORISTA = "laboratorista"
    CSBQR_ADMIN = "csbqr_admin"

class EstadoUsuario(str, Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"

class Veredicto(str, Enum):
    NUNCA = "NUNCA"
    SEGREGAR = "SEGREGAR"
    COMPATIBLE = "COMPATIBLE"


def valores(enumeracion) -> tuple:
    """Devuelve los valores de un Enum para restringirlos también en la base."""
    return tuple(miembro.value for miembro in enumeracion)


# Categorías que el CSBQR tiene que ver sí o sí: lo que no se identificó y lo
# radiactivo, que no se gestiona con el resto.
CATEGORIAS_QUE_ESCALAN = frozenset({"no-identificados", "radiactivos"})


def requiere_escalamiento(categoria_id: str, desconocido: bool = False) -> bool:
    """Si una declaración debe subir al CSBQR.

    Vive aquí y no en el clasificador porque también decide la regla cuando un
    humano corrige la categoría: con la regla escrita dos veces, corregir un
    residuo podía dejarlo escalado sin motivo o desescalarlo indebidamente.
    """
    return desconocido or categoria_id in CATEGORIAS_QUE_ESCALAN


# Ciclo de vida del residuo. Un residuo DISPUESTO es terminal: ya salió con el
# operador de residuos sólidos y no puede volver a moverse dentro del campus.
TRANSICIONES_PERMITIDAS = {
    EstadoResiduo.GENERADO: {EstadoResiduo.EN_TRASLADO, EstadoResiduo.EN_EVALUACION},
    EstadoResiduo.EN_EVALUACION: {EstadoResiduo.GENERADO, EstadoResiduo.EN_TRASLADO},
    EstadoResiduo.EN_TRASLADO: {EstadoResiduo.ALMACENADO, EstadoResiduo.EN_EVALUACION},
    EstadoResiduo.ALMACENADO: {EstadoResiduo.EN_TRASLADO, EstadoResiduo.DISPUESTO},
    EstadoResiduo.DISPUESTO: set(),
}

# Movimiento de kardex que corresponde a cada transición.
MOVIMIENTO_POR_TRANSICION = {
    EstadoResiduo.EN_TRASLADO: (TipoMovimiento.TRANSFERENCIA, MotivoMovimiento.TRASLADO_ACOPIO),
    EstadoResiduo.ALMACENADO: (TipoMovimiento.ENTRADA, MotivoMovimiento.TRASLADO_ACOPIO),
    EstadoResiduo.DISPUESTO: (TipoMovimiento.SALIDA, MotivoMovimiento.ENTREGA_EORS),
    EstadoResiduo.GENERADO: (TipoMovimiento.AJUSTE, MotivoMovimiento.CORRECCION),
    EstadoResiduo.EN_EVALUACION: (TipoMovimiento.AJUSTE, MotivoMovimiento.CORRECCION),
}


class RegistroRequest(BaseModel):
    """Cabecera de una visita de declaración.

    Se abre una vez y contra ella se declaran todos los residuos encontrados,
    en lugar de repetir estos datos en cada envase.
    """

    dependencia: str = Field(..., min_length=1, max_length=100)
    laboratorio: str = Field(..., min_length=1, max_length=100)
    responsable_encargado: str = Field(
        ..., min_length=1, max_length=150,
        description="Responsable o Encargado del laboratorio",
    )
    elaborado_por: Optional[str] = Field(None, max_length=150)
    fecha: date = Field(..., description="Fecha de la visita, en formato ISO")
    telefono_contacto: Optional[str] = Field(None, max_length=30)
    comentarios_generales: Optional[str] = None

    @field_validator("dependencia", "laboratorio", "responsable_encargado")
    @classmethod
    def _sin_espacios_sobrantes(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El campo no puede quedar vacío")
        return limpio


class ResiduoDeRegistroRequest(BaseModel):
    """Un residuo declarado dentro de un registro ya abierto.

    Es `EntradaResiduoRequest` sin los campos de cabecera, que ya los aporta el
    registro: dependencia, laboratorio y elaborado por.
    """

    actividad: str = Field(..., min_length=1, max_length=200)
    origen: Origen = Origen.ACADEMICO
    responsable: str = Field(
        ..., min_length=1, max_length=150,
        description="Responsable de la generación de este residuo",
    )
    fecha: Optional[date] = Field(
        None, description="Fecha de generación. Si se omite, la del registro."
    )
    descripcion: str = Field(..., min_length=1)
    insumos: List[str] = Field(default_factory=list)
    estado_fisico: EstadoFisico = EstadoFisico.LIQUIDO
    peso_bruto_g: float = Field(..., ge=0)
    tara_g: float = Field(0.0, ge=0)
    ph: Optional[float] = Field(None, ge=0, le=14)
    foto_url: Optional[str] = Field(None, max_length=500)
    # Envase y dimensiones: la página 2 del formato oficial es una tabla de
    # fotos de envase con sus medidas, y sin estos campos no se puede llenar.
    tipo_envase: Optional[str] = Field(None, max_length=100)
    ancho_cm: Optional[float] = Field(None, gt=0, le=500)
    alto_cm: Optional[float] = Field(None, gt=0, le=500)
    profundidad_cm: Optional[float] = Field(None, gt=0, le=500)
    es_punzocortante: bool = False
    es_biologico: bool = False
    es_aerosol: bool = False
    es_envase_vacio: bool = False
    desconocido: bool = False


class ConfirmacionCategoriaRequest(BaseModel):
    """Aceptación o corrección humana de la categoría propuesta.

    `categoria_id` viaja solo cuando se corrige. Aceptar es confirmar que la
    propuesta del sistema queda como está, y también deja constancia: una
    propuesta confirmada por una persona no es lo mismo que una sin revisar.
    """

    decision: DecisionClasificacion
    confirmada_por: str = Field(..., min_length=1, max_length=150)
    categoria_id: Optional[str] = Field(None, max_length=50)
    motivo: Optional[str] = Field(None, max_length=300)

    @field_validator("confirmada_por")
    @classmethod
    def _quien_confirma(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("Indique quién confirma la clasificación")
        return limpio

    @model_validator(mode="after")
    def _corregir_exige_categoria(self):
        if self.decision is DecisionClasificacion.CORREGIDA and not self.categoria_id:
            raise ValueError(
                "Para corregir la clasificación indique la categoría correcta"
            )
        if self.decision is DecisionClasificacion.ACEPTADA and self.categoria_id:
            raise ValueError(
                "Aceptar la propuesta no admite otra categoría: para cambiarla, "
                "la decisión es 'corregida'"
            )
        return self


class PersonaRequest(BaseModel):
    """Alta de una persona en el padrón.

    El catálogo no es cerrado, por la misma razón que el de laboratorios: 29 de
    los 101 registros históricos usan laboratorios que el formato no lista, y
    bloquear lo que no esté sembrado impediría declaraciones legítimas.
    """

    nombre: str = Field(..., min_length=3, max_length=150)
    dependencia: Optional[str] = Field(None, max_length=100)
    correo: Optional[EmailStr] = None
    telefono: Optional[str] = Field(None, max_length=30)
    es_encargado: bool = False
    es_csbqr: bool = False
    es_generador: bool = True

    @field_validator("nombre")
    @classmethod
    def _nombre_utilizable(cls, valor: str) -> str:
        limpio = " ".join(valor.split())
        if len(limpio) < 3:
            raise ValueError("El nombre es demasiado corto para identificar a alguien")
        return limpio


class CambioEstadoRequest(BaseModel):
    estado_destino: EstadoResiduo
    registrado_por: str = Field(..., min_length=1, max_length=100)
    laboratorio_destino: Optional[str] = Field(None, max_length=100)
    observacion: Optional[str] = None

    @field_validator("registrado_por")
    @classmethod
    def _responsable_no_vacio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("Indique quién registra el movimiento")
        return limpio


class UsuarioBase(BaseModel):
    email: EmailStr
    nombre: str
    rol: RolUsuario = RolUsuario.INVESTIGADOR

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(UsuarioBase):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    estado: EstadoUsuario = EstadoUsuario.ACTIVO

class EntradaResiduoRequest(BaseModel):
    dependencia: str = Field(..., min_length=1, max_length=100)
    laboratorio: str = Field(..., min_length=1, max_length=100)
    actividad: str = Field(..., min_length=1, max_length=200)
    origen: Origen = Origen.ACADEMICO
    responsable: str = Field(..., min_length=1, max_length=100)
    elaborado_por: Optional[str] = Field(None, max_length=100)
    fecha: date = Field(..., description="Fecha de generación en formato ISO (YYYY-MM-DD)")
    descripcion: str = Field(..., min_length=1)
    insumos: List[str] = Field(default_factory=list)
    estado_fisico: EstadoFisico = EstadoFisico.LIQUIDO

    # Dos modos de captura, excluyentes.
    #
    # Pesaje: se indica el peso bruto y la tara, ambos en gramos, y la cantidad
    # declarada sale de restarlos. Es el modo que pide el Gem.
    #
    # Declaración directa: se indica la cantidad y su unidad. Es el modo que
    # necesitan los líquidos que se miden por volumen y el único con el que se
    # pueden representar los 277 registros históricos en litros.
    peso_bruto_g: Optional[float] = Field(
        None, ge=0, description="Peso bruto medido en balanza en GRAMOS"
    )
    tara_g: float = Field(0.0, ge=0, description="Tara del envase en GRAMOS")
    cantidad: Optional[float] = Field(
        None, gt=0, description="Cantidad declarada, en la unidad indicada"
    )
    unidad: Unidad = Unidad.KG
    ph: Optional[float] = Field(None, ge=0, le=14)
    foto_url: Optional[str] = Field(None, max_length=500)
    tipo_envase: Optional[str] = Field(None, max_length=100)
    ancho_cm: Optional[float] = Field(None, gt=0, le=500)
    alto_cm: Optional[float] = Field(None, gt=0, le=500)
    profundidad_cm: Optional[float] = Field(None, gt=0, le=500)
    es_punzocortante: bool = False
    es_biologico: bool = False
    es_aerosol: bool = False
    es_envase_vacio: bool = False
    desconocido: bool = False

    @field_validator("dependencia", "laboratorio", "actividad", "responsable", "descripcion")
    @classmethod
    def _sin_espacios_sobrantes(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El campo no puede quedar vacío")
        return limpio

    @field_validator("insumos")
    @classmethod
    def _insumos_normalizados(cls, valores_insumos: List[str]) -> List[str]:
        """Recorta, descarta vacíos y elimina duplicados conservando el orden.

        La tabla `declaracion_insumos` tiene unicidad por (declaración, insumo),
        de modo que un duplicado enviado por el cliente sería un error de
        integridad en vez de una entrada válida.
        """
        vistos = set()
        normalizados = []
        for insumo in valores_insumos:
            limpio = insumo.strip()
            if not limpio:
                continue
            clave = limpio.lower()
            if clave in vistos:
                continue
            vistos.add(clave)
            normalizados.append(limpio)
        return normalizados

    @model_validator(mode="after")
    def _un_solo_modo_de_medicion(self):
        """Exige exactamente una forma de indicar cuánto residuo hay."""
        if EXIGIR_PESAJE_EN_KG and self.peso_bruto_g is None:
            raise ValueError(
                "Toda declaración debe pesarse en balanza: indique el peso bruto "
                "en gramos. No se admite declarar la cantidad directamente."
            )
        if self.peso_bruto_g is None and self.cantidad is None:
            raise ValueError(
                "Indique el peso bruto medido en balanza, o bien la cantidad y su unidad"
            )
        if self.peso_bruto_g is not None and self.cantidad is not None:
            raise ValueError(
                "Indique el peso bruto o la cantidad, no ambos: la cantidad se "
                "calcula a partir del pesaje"
            )
        if self.peso_bruto_g is not None and self.unidad is not Unidad.KG:
            raise ValueError("Un pesaje en balanza se declara en Kg, no en litros")
        return self

    @property
    def modo_medicion(self) -> ModoMedicion:
        return ModoMedicion.PESAJE if self.peso_bruto_g is not None else ModoMedicion.DECLARADA

class ResultadoClasificacion(BaseModel):
    id_residuo: str
    nombre_normalizado: str
    categoria_id: str
    categoria_nombre: str
    caracteristica_principal: str
    clase_declaracion_sunat: str
    clase_basilea: str
    grupo_compatibilidad: str
    no_mezclar_con: List[str]
    envase_recomendado: str
    # Cifra que se imprime en el formato oficial, en la unidad declarada.
    cantidad: float
    unidad: Unidad
    modo_medicion: ModoMedicion
    # Solo cuando hubo balanza. Es la evidencia detrás de una cantidad en Kg.
    peso_bruto_g: Optional[float] = None
    tara_g: Optional[float] = None
    peso_neto_g: Optional[float] = Field(None, description="Peso neto en GRAMOS")
    confianza: NivelConfianza
    observaciones: List[str]
    pictogramas_ghs: List[str]
    escalar_csbqr: bool
    narrativa: str

class MovimientoKardexRequest(BaseModel):
    id_residuo: str
    tipo_movimiento: TipoMovimiento
    motivo: MotivoMovimiento
    cantidad_g: float = Field(0.0, ge=0, description="Cantidad en gramos. Para transferencias de custodia es 0")
    laboratorio_origen: Optional[str] = None
    laboratorio_destino: Optional[str] = None
    registrado_por: str = Field(..., min_length=1, max_length=100)
