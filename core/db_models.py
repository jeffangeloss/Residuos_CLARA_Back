"""
Modelos ORM de SQLAlchemy para PostgreSQL - Esquema 3FN (Tercera Forma Normal)
Plataforma CLARA+ - Universidad de Lima

El vocabulario de dominio (orígenes, estados físicos, confianza, estados del
residuo, roles y veredictos) se importa de `core/models.py` para que la API y la
base de datos restrinjan exactamente los mismos valores.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core.database import Base
from core.models import (
    EstadoFisico,
    EstadoResiduo,
    EstadoUsuario,
    ModoMedicion,
    MotivoMovimiento,
    NivelConfianza,
    Origen,
    RolUsuario,
    TipoMovimiento,
    Unidad,
    Veredicto,
    valores,
)


def ahora_utc() -> datetime:
    """Marca temporal consciente de zona horaria.

    Reemplaza a `datetime.utcnow`, que devuelve un valor ingenuo y quedó
    obsoleto: dos declaraciones creadas en husos distintos resultaban
    indistinguibles al ordenarlas.
    """
    return datetime.now(timezone.utc)


def _restringir(columna: str, enumeracion) -> str:
    """Genera la condición SQL que limita una columna al vocabulario del dominio."""
    permitidos = ", ".join(f"'{valor}'" for valor in valores(enumeracion))
    return f"{columna} IN ({permitidos})"


class DependenciaDB(Base):
    __tablename__ = "dependencias"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(20), unique=True, index=True, nullable=False)
    # El nombre es único porque es la clave con la que los clientes web y móvil
    # identifican la dependencia; sin unicidad la resolución es ambigua.
    nombre = Column(String(100), unique=True, nullable=False)
    # El formato oficial escribe las dependencias con guion bajo y sin la
    # preposición: "Ingeniería de Sistemas" se exporta como "Ingeniería_Sistemas".
    token_formato = Column(String(100), nullable=True)
    # El catálogo institucional no es cerrado: 29 de 101 registros históricos
    # usan laboratorios que el formato 2026 no lista. Esta marca distingue lo
    # sembrado desde el catálogo de lo creado sobre la marcha.
    en_catalogo_oficial = Column(Boolean, nullable=False, default=False, server_default="0")

    laboratorios = relationship("LaboratorioDB", back_populates="dependencia")


class LaboratorioDB(Base):
    __tablename__ = "laboratorios"
    __table_args__ = (
        # Dos dependencias pueden tener un laboratorio homónimo, pero dentro de
        # una misma dependencia el nombre debe resolver a un único laboratorio.
        UniqueConstraint("dependencia_id", "nombre"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(20), unique=True, index=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    dependencia_id = Column(Integer, ForeignKey("dependencias.id"), nullable=False, index=True)
    ubicacion = Column(String(100), nullable=True)
    responsable_defecto = Column(String(100), nullable=True)
    en_catalogo_oficial = Column(Boolean, nullable=False, default=False, server_default="0")

    dependencia = relationship("DependenciaDB", back_populates="laboratorios")
    registros = relationship("RegistroDB", back_populates="laboratorio")
    usuarios = relationship("UsuarioDB", back_populates="laboratorio")


class CategoriaULimaDB(Base):
    __tablename__ = "categorias_ulima"

    id = Column(String(50), primary_key=True, index=True) # e.g. 'metales-pesados'
    nombre = Column(String(100), nullable=False)
    caracteristica_principal = Column(String(50), nullable=False)
    # Valor exacto del desplegable "Clasificación" del formato 2026. El Excel
    # valida contra esa lista, así que la característica descriptiva del Gem
    # ("Corrosivo") no sirve para exportar: allí se escribe "Corrosividad".
    caracteristica_declaracion = Column(String(100), nullable=False, server_default="")
    clase_sunat = Column(String(150), nullable=False)
    clase_basilea = Column(String(50), nullable=False)
    grupo_compatibilidad = Column(String(50), nullable=False, index=True)
    envase_recomendado = Column(String(200), nullable=False)
    # Incompatibilidades en texto legible, para imprimirlas en la etiqueta. Se
    # guardan en la base y no se leen de la ontología en memoria, por la misma
    # razón que la matriz: la etiqueta debe reflejar el dato persistido.
    no_mezclar_con = Column(String(300), nullable=False, server_default="")

    declaraciones = relationship(
        "DeclaracionResiduoDB",
        back_populates="categoria",
        foreign_keys="DeclaracionResiduoDB.categoria_id",
    )


class TipoEnvaseDB(Base):
    """Catálogo de envases, normalizado.

    La base histórica trae 50 variantes para unos pocos conceptos: "Plástico",
    "Envase de plástico", "Envase De Plástico" y "Plastico" son lo mismo escrito
    de cuatro maneras, lo que impide agrupar o contar por tipo de envase.
    """

    __tablename__ = "tipos_envase"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(20), unique=True, index=True, nullable=False)
    nombre = Column(String(100), unique=True, nullable=False)


class PersonaDB(Base):
    """Padrón de personal: quién declara, quién elabora y quién es responsable.

    No es la tabla de autenticación —esa es `usuarios`, con su contraseña—.
    Aquí no hay credenciales: es el catálogo de nombres que sustituye al texto
    libre de los formularios, donde la misma persona se escribía de tres
    maneras y quedaban como tres personas distintas.

    Igual que el de laboratorios, **este catálogo no es cerrado**: una persona
    que no esté sembrada se registra sobre la marcha y queda marcada, en vez de
    bloquear una declaración legítima.
    """

    __tablename__ = "personal"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(20), unique=True, index=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    # Nombre plegado a minúsculas y sin acentos. Es la clave real de identidad:
    # el nombre visible conserva su escritura, pero dos escrituras del mismo
    # nombre no pueden convivir como dos personas.
    nombre_clave = Column(String(150), unique=True, index=True, nullable=False)
    correo = Column(String(120), nullable=True)
    telefono = Column(String(30), nullable=True)
    dependencia_id = Column(Integer, ForeignKey("dependencias.id"), nullable=True, index=True)
    # Los tres papeles del proceso real, y no son excluyentes: quien encarga un
    # laboratorio también genera residuos en él.
    es_encargado = Column(Boolean, nullable=False, default=False, server_default="0")
    es_csbqr = Column(Boolean, nullable=False, default=False, server_default="0")
    es_generador = Column(Boolean, nullable=False, default=True, server_default="1")
    activo = Column(Boolean, nullable=False, default=True, server_default="1")
    en_catalogo_oficial = Column(Boolean, nullable=False, default=False, server_default="0")

    dependencia = relationship("DependenciaDB")
    alias = relationship(
        "PersonaAliasDB", back_populates="persona", cascade="all, delete-orphan"
    )


class PersonaAliasDB(Base):
    """Cada forma en que el nombre de una persona se escribió en el histórico.

    Sostiene la importación de la Fase 11: las 856 filas traen el nombre a
    mano, y sin estas variantes cada escritura crearía una persona nueva.
    """

    __tablename__ = "personal_alias"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    persona_id = Column(
        Integer, ForeignKey("personal.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias_clave = Column(String(150), unique=True, index=True, nullable=False)
    alias_texto = Column(String(150), nullable=False)

    persona = relationship("PersonaDB", back_populates="alias")


class UsuarioDB(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(_restringir("rol", RolUsuario), name="rol_valido"),
        CheckConstraint(_restringir("estado", EstadoUsuario), name="estado_valido"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    rol = Column(String(50), nullable=False, default=RolUsuario.INVESTIGADOR.value)
    laboratorio_id = Column(Integer, ForeignKey("laboratorios.id"), nullable=True, index=True)
    password_hash = Column(String(200), nullable=False)
    estado = Column(String(20), nullable=False, default=EstadoUsuario.ACTIVO.value)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=ahora_utc)

    laboratorio = relationship("LaboratorioDB", back_populates="usuarios")
    declaraciones = relationship("DeclaracionResiduoDB", back_populates="usuario")


class RegistroDB(Base):
    """Cabecera de una visita de declaración: agrupa los residuos declarados juntos.

    Reproduce la estructura real del proceso: se visita un laboratorio una vez y
    se declaran allí varios envases. El formato oficial se emite por registro,
    con esta cabecera arriba y una fila por residuo debajo.

    Antes cada declaración repetía dependencia, laboratorio y responsable. Un
    registro del histórico llega a tener 132 residuos.
    """

    __tablename__ = "registros"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(String(40), unique=True, index=True, nullable=False)
    laboratorio_id = Column(Integer, ForeignKey("laboratorios.id"), nullable=False, index=True)
    # "Responsable o Encargado" del formato: la persona a cargo del laboratorio.
    # No confundir con `DeclaracionResiduoDB.responsable`, que es quien generó
    # ese residuo en concreto.
    responsable_encargado = Column(String(150), nullable=False)
    elaborado_por = Column(String(150), nullable=True)
    fecha = Column(Date, nullable=False, index=True)
    telefono_contacto = Column(String(30), nullable=True)
    comentarios_generales = Column(Text, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=ahora_utc)
    actualizado_en = Column(
        DateTime(timezone=True), nullable=False, default=ahora_utc, onupdate=ahora_utc
    )

    laboratorio = relationship("LaboratorioDB", back_populates="registros")
    usuario = relationship("UsuarioDB")
    declaraciones = relationship(
        "DeclaracionResiduoDB", back_populates="registro", cascade="all, delete-orphan"
    )


class DeclaracionResiduoDB(Base):
    __tablename__ = "declaraciones"
    __table_args__ = (
        CheckConstraint("peso_bruto_g IS NULL OR peso_bruto_g >= 0", name="peso_bruto_no_negativo"),
        CheckConstraint("tara_g IS NULL OR tara_g >= 0", name="tara_no_negativa"),
        CheckConstraint("peso_neto_g IS NULL OR peso_neto_g >= 0", name="peso_neto_no_negativo"),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint(_restringir("unidad", Unidad), name="unidad_valida"),
        CheckConstraint(_restringir("modo_medicion", ModoMedicion), name="modo_medicion_valido"),
        # Un pesaje tiene que traer su evidencia y declararse en kilogramos.
        CheckConstraint(
            "modo_medicion <> 'pesaje' OR "
            "(peso_bruto_g IS NOT NULL AND peso_neto_g IS NOT NULL AND unidad = 'Kg')",
            name="pesaje_con_evidencia",
        ),
        # Guarda de unidades: cuando hubo balanza, la cantidad en kg y el peso
        # neto en gramos deben describir la misma masa. La holgura de 1 g absorbe
        # el redondeo a 4 decimales sin dejar pasar una confusión de unidades,
        # que es el error caro en una declaración regulatoria.
        CheckConstraint(
            "peso_neto_g IS NULL OR "
            "cantidad * 1000 BETWEEN peso_neto_g - 1 AND peso_neto_g + 1",
            name="cantidad_coherente_con_pesaje",
        ),
        CheckConstraint("ph IS NULL OR (ph >= 0 AND ph <= 14)", name="ph_en_rango"),
        # Las dimensiones van a la página 2 del formato oficial, junto a la
        # foto. Cero no es una medida: un envase con 0 cm de ancho no existe,
        # y admitirlo dejaría pasar el campo sin llenar disfrazado de dato.
        CheckConstraint("ancho_cm IS NULL OR ancho_cm > 0", name="ancho_positivo"),
        CheckConstraint("alto_cm IS NULL OR alto_cm > 0", name="alto_positivo"),
        CheckConstraint(
            "profundidad_cm IS NULL OR profundidad_cm > 0", name="profundidad_positiva"
        ),
        CheckConstraint(_restringir("origen", Origen), name="origen_valido"),
        CheckConstraint(_restringir("estado_fisico", EstadoFisico), name="estado_fisico_valido"),
        CheckConstraint(_restringir("confianza", NivelConfianza), name="confianza_valida"),
        CheckConstraint(_restringir("estado", EstadoResiduo), name="estado_valido"),
        # El panel CSBQR filtra por período y por escalamiento.
        Index("ix_declaraciones_fecha_estado", "fecha", "estado"),
        Index("ix_declaraciones_escalar_csbqr", "escalar_csbqr"),
        # El "Código" legible del formato oficial se numera dentro de cada
        # registro. No es único a nivel global: en el histórico hay 856 residuos
        # con solo 779 códigos distintos.
        UniqueConstraint("registro_id", "codigo_formato"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo_residuo = Column(String(50), unique=True, index=True, nullable=False)
    codigo_formato = Column(String(40), nullable=True)
    registro_id = Column(
        Integer, ForeignKey("registros.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    categoria_id = Column(String(50), ForeignKey("categorias_ulima.id"), nullable=False, index=True)

    actividad = Column(String(200), nullable=False)
    origen = Column(String(50), nullable=False, default=Origen.ACADEMICO.value)
    # "Responsable de la generación del residuo": quien generó este envase.
    # El encargado del laboratorio vive en el registro.
    responsable = Column(String(150), nullable=False)
    # Fecha real, no texto: el filtro por período usaba LIKE sobre una cadena y
    # dependía de que todos los clientes escribieran el mismo formato.
    fecha = Column(Date, nullable=False, index=True)
    descripcion = Column(Text, nullable=False)
    # Nombre normalizado que produce el clasificador. Antes no se persistía y el
    # listado devolvía la descripción en su lugar.
    nombre_normalizado = Column(String(300), nullable=False)
    estado_fisico = Column(String(50), nullable=False, default=EstadoFisico.LIQUIDO.value)
    foto_url = Column(String(500), nullable=True)

    # Envase y dimensiones. El formulario los capturaba y CLARA+ los perdía:
    # sin ellos no se puede llenar la página 2 del formato de declaración, que
    # es una tabla de fotos de envase con sus medidas.
    tipo_envase_id = Column(Integer, ForeignKey("tipos_envase.id"), nullable=True, index=True)
    ancho_cm = Column(Float, nullable=True)
    alto_cm = Column(Float, nullable=True)
    profundidad_cm = Column(Float, nullable=True)

    # Cifra que se imprime en el formato oficial, en la unidad declarada. Es la
    # autoritativa: el formato acepta Kg y L, y 277 de los 856 registros
    # históricos están en litros.
    cantidad = Column(Float, nullable=False)
    unidad = Column(String(4), nullable=False, default=Unidad.KG.value)
    modo_medicion = Column(String(12), nullable=False, default=ModoMedicion.PESAJE.value)

    # Evidencia del pesaje. Nulos cuando la cantidad se declaró directamente,
    # que es como se miden los líquidos por volumen.
    peso_bruto_g = Column(Float, nullable=True)
    tara_g = Column(Float, nullable=True)
    peso_neto_g = Column(Float, nullable=True)
    ph = Column(Float, nullable=True)

    # Indicadores de entrada. Se persisten porque son parte de la evidencia que
    # hace reproducible la clasificación (RF-03); sin ellos no se puede
    # recalcular por qué un residuo cayó en su categoría.
    es_punzocortante = Column(Boolean, nullable=False, default=False)
    es_biologico = Column(Boolean, nullable=False, default=False)
    es_aerosol = Column(Boolean, nullable=False, default=False)
    es_envase_vacio = Column(Boolean, nullable=False, default=False)
    desconocido = Column(Boolean, nullable=False, default=False)

    confianza = Column(String(20), nullable=False, default=NivelConfianza.ALTO.value)
    estado = Column(String(20), nullable=False, default=EstadoResiduo.GENERADO.value)
    escalar_csbqr = Column(Boolean, nullable=False, default=False)
    narrativa = Column(Text, nullable=False)

    # La clasificación es una propuesta, no un veredicto.
    #
    # El Gem lo dice de su propia salida: "es una ayuda técnica interna; no
    # reemplaza la clasificación legal ni la decisión del CSBQR". Y el histórico
    # lo respalda: 548 nombres de residuo distintos, que ninguna coincidencia de
    # palabras clave clasifica sola.
    #
    # Por eso se guarda qué propuso el sistema aparte de qué quedó vigente:
    # `categoria_id` es la categoría en vigor y `categoria_propuesta_id` la que
    # se propuso. Si difieren, un humano corrigió. Conservar ambas es lo que
    # permite medir cuánto acierta el clasificador con datos reales, en vez de
    # perder la propuesta en el momento de sobrescribirla.
    categoria_propuesta_id = Column(
        String(50), ForeignKey("categorias_ulima.id"), nullable=True, index=True
    )
    clasificacion_confirmada = Column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    confirmada_por = Column(String(150), nullable=True)
    confirmada_en = Column(DateTime(timezone=True), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=ahora_utc)
    actualizado_en = Column(
        DateTime(timezone=True), nullable=False, default=ahora_utc, onupdate=ahora_utc
    )

    registro = relationship("RegistroDB", back_populates="declaraciones")
    usuario = relationship("UsuarioDB", back_populates="declaraciones")
    # Dos claves foráneas apuntan ahora a `categorias_ulima`, así que hay que
    # decir cuál sostiene cada relación.
    categoria = relationship(
        "CategoriaULimaDB", back_populates="declaraciones", foreign_keys=[categoria_id]
    )
    categoria_propuesta = relationship(
        "CategoriaULimaDB", foreign_keys=[categoria_propuesta_id]
    )
    tipo_envase = relationship("TipoEnvaseDB")

    @property
    def laboratorio(self):
        """Atajo al laboratorio, que ahora vive en la cabecera del registro."""
        return self.registro.laboratorio if self.registro else None

    insumos = relationship(
        "DeclaracionInsumoDB", back_populates="declaracion", cascade="all, delete-orphan"
    )
    pictogramas = relationship(
        "DeclaracionPictogramaDB", back_populates="declaracion", cascade="all, delete-orphan"
    )
    observaciones = relationship(
        "DeclaracionObservacionDB", back_populates="declaracion", cascade="all, delete-orphan"
    )
    movimientos = relationship(
        "MovimientoKardexDB",
        back_populates="declaracion",
        cascade="all, delete-orphan",
        order_by="MovimientoKardexDB.registrado_en",
    )


class DeclaracionInsumoDB(Base):
    __tablename__ = "declaracion_insumos"
    __table_args__ = (
        UniqueConstraint("declaracion_id", "nombre_quimico"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    declaracion_id = Column(
        Integer, ForeignKey("declaraciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre_quimico = Column(String(150), nullable=False)

    declaracion = relationship("DeclaracionResiduoDB", back_populates="insumos")


class DeclaracionPictogramaDB(Base):
    __tablename__ = "declaracion_pictogramas"
    __table_args__ = (
        UniqueConstraint("declaracion_id", "codigo_pictograma"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    declaracion_id = Column(
        Integer, ForeignKey("declaraciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    codigo_pictograma = Column(String(50), nullable=False) # e.g. 'calavera', 'corrosion'

    declaracion = relationship("DeclaracionResiduoDB", back_populates="pictogramas")


class DeclaracionObservacionDB(Base):
    """Observaciones de manejo que el clasificador emite junto al resultado."""

    __tablename__ = "declaracion_observaciones"
    __table_args__ = (
        UniqueConstraint("declaracion_id", "texto"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    declaracion_id = Column(
        Integer, ForeignKey("declaraciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    texto = Column(String(300), nullable=False)

    declaracion = relationship("DeclaracionResiduoDB", back_populates="observaciones")


class MovimientoKardexDB(Base):
    """Traza de custodia del residuo: generación, traslado, acopio y disposición.

    Los modelos Pydantic del kardex existían desde la primera versión, pero no
    había tabla donde registrarlos: el ciclo de vida del residuo quedaba sin
    evidencia una vez creada la declaración.
    """

    __tablename__ = "movimientos_kardex"
    __table_args__ = (
        CheckConstraint("cantidad_g IS NULL OR cantidad_g >= 0", name="cantidad_no_negativa"),
        CheckConstraint(_restringir("tipo_movimiento", TipoMovimiento), name="tipo_valido"),
        CheckConstraint(_restringir("motivo", MotivoMovimiento), name="motivo_valido"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    declaracion_id = Column(
        Integer, ForeignKey("declaraciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo_movimiento = Column(String(20), nullable=False)
    motivo = Column(String(50), nullable=False)
    # Masa movida, en gramos, cuando se conoce. Es nula en los residuos
    # declarados por volumen: sin balanza no hay masa que registrar.
    cantidad_g = Column(Float, nullable=True)
    laboratorio_origen_id = Column(Integer, ForeignKey("laboratorios.id"), nullable=True)
    laboratorio_destino_id = Column(Integer, ForeignKey("laboratorios.id"), nullable=True)
    registrado_por = Column(String(100), nullable=False)
    registrado_en = Column(DateTime(timezone=True), nullable=False, default=ahora_utc, index=True)
    observacion = Column(Text, nullable=True)

    declaracion = relationship("DeclaracionResiduoDB", back_populates="movimientos")
    laboratorio_origen = relationship("LaboratorioDB", foreign_keys=[laboratorio_origen_id])
    laboratorio_destino = relationship("LaboratorioDB", foreign_keys=[laboratorio_destino_id])


class ReglaIncompatibilidadDB(Base):
    __tablename__ = "reglas_incompatibilidad"
    __table_args__ = (
        UniqueConstraint("grupo_a", "grupo_b"),
        CheckConstraint(_restringir("veredicto", Veredicto), name="veredicto_valido"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    grupo_a = Column(String(50), nullable=False, index=True)
    grupo_b = Column(String(50), nullable=False, index=True)
    veredicto = Column(String(20), nullable=False) # NUNCA / SEGREGAR / COMPATIBLE
    explicacion_riesgo = Column(Text, nullable=False)
