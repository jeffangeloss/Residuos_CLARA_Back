"""Pruebas de la Fase 9: padrón, envase, dimensiones y propuesta confirmable.

Lo que se verifica aquí es lo que hace que el móvil pueda sustituir a los dos
formularios de Google: que la identidad de las personas deje de ser texto
libre, que el envase y sus medidas se guarden, y que la clasificación sea una
propuesta que un humano confirma o corrige sin que se pierda lo que propuso el
sistema.
"""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from tests.test_persistencia import _entrada, _persistir


# ---------------------------------------------------------------------------
# Padrón de personal
# ---------------------------------------------------------------------------

def test_el_padron_se_siembra_con_los_nombres_del_historico(db):
    from core.db_models import PersonaDB

    personas = db.query(PersonaDB).all()
    assert len(personas) >= 50
    assert all(persona.en_catalogo_oficial for persona in personas)

    nombres = {persona.nombre for persona in personas}
    assert "Javier Quino Favero" in nombres
    assert "Christian Querevalú Borja" in nombres
    # La variante no es una persona: es un alias de la anterior.
    assert "Javier Quino" not in nombres


@pytest.mark.parametrize(
    "escritura, canonico",
    [
        ("Javier Quino", "Javier Quino Favero"),
        ("Milagros Alvarado", "Milagros Ariana Alvarado Apaza"),
        ("Milagros Alvarado Apaza", "Milagros Ariana Alvarado Apaza"),
        ("Juan Carlos Yacono", "Juan Carlos Yacono Llanos"),
        # Error de tipeo del histórico: falta una 's'.
        ("Nancy Chaquibol Silva", "Nancy Chasquibol Silva"),
        # Acentos: la misma persona escrita con y sin tilde.
        ("Miguel Angel Leguia Martinez", "Miguel Angel Leguía Martinez"),
        ("MIGUEL ANGEL LEGUÍA MARTINEZ", "Miguel Angel Leguía Martinez"),
        ("  Pamela   Barreto  ", "Pamela Barreto Méndez"),
    ],
)
def test_las_variantes_del_historico_resuelven_a_una_sola_persona(db, escritura, canonico):
    """El hallazgo del histórico: la misma persona escrita de varias maneras.

    Sin esto, las 856 filas producirían una persona por escritura y la
    atribución de un residuo no significaría nada.
    """
    from core.repositorio import buscar_persona

    persona = buscar_persona(db, escritura)
    assert persona is not None, f"'{escritura}' no resolvió a nadie"
    assert persona.nombre == canonico


def test_quien_no_esta_en_el_padron_no_se_inventa(db):
    from core.repositorio import buscar_persona

    assert buscar_persona(db, "Persona Que No Existe") is None


def test_el_padron_no_es_cerrado(db):
    """Igual que el de laboratorios: bloquear impediría declarar de verdad."""
    from core.repositorio import registrar_persona

    persona = registrar_persona(db, nombre="Tesista Nuevo Apellido", es_generador=True)

    assert persona.id is not None
    # Queda marcada como no oficial, para que el CSBQR vea qué entró sobre la
    # marcha y qué venía del catálogo.
    assert persona.en_catalogo_oficial is False


def test_dar_de_alta_a_alguien_que_ya_esta_no_lo_duplica(db):
    from core.db_models import PersonaDB
    from core.repositorio import registrar_persona

    antes = db.query(PersonaDB).count()
    # Llega por una variante, no por el nombre canónico.
    persona = registrar_persona(db, nombre="javier quino", es_encargado=True)

    assert db.query(PersonaDB).count() == antes
    assert persona.nombre == "Javier Quino Favero"


def test_los_papeles_se_acumulan(db):
    """Quien encarga un laboratorio también genera residuos en él."""
    from core.repositorio import registrar_persona

    persona = registrar_persona(db, nombre="Nancy Chasquibol Silva", es_csbqr=True)

    assert persona.es_encargado is True   # el que ya tenía
    assert persona.es_csbqr is True       # el que se le añade


def test_el_padron_se_filtra_por_papel(db):
    from core.models import RolPadron
    from core.repositorio import filtrar_personal

    encargados = filtrar_personal(db, rol=RolPadron.ENCARGADO)
    csbqr = filtrar_personal(db, rol=RolPadron.CSBQR)

    assert all(persona.es_encargado for persona in encargados)
    assert all(persona.es_csbqr for persona in csbqr)
    assert "Henrry Delgado Ortega" in {p.nombre for p in encargados}
    assert "Christian Querevalú Borja" in {p.nombre for p in csbqr}


def test_filtrar_por_dependencia_conserva_al_personal_del_csbqr(db):
    """El CSBQR atiende todos los laboratorios: no tiene dependencia propia.

    Filtrarlo fuera dejaría al móvil sin nadie a quien atribuir la elaboración
    de la declaración.
    """
    from core.repositorio import filtrar_personal

    personas = filtrar_personal(db, dependencia="Ingeniería Civil")
    nombres = {persona.nombre for persona in personas}

    assert "Henrry Delgado Ortega" in nombres          # encargado de Civil
    assert "Javier Quino Favero" not in nombres        # encargado de Industrial
    assert "Christian Querevalú Borja" in nombres      # CSBQR, sin dependencia


def test_buscar_en_el_padron_encuentra_por_alias(db):
    from core.repositorio import filtrar_personal

    resultados = filtrar_personal(db, busqueda="quino")
    assert {p.nombre for p in resultados} == {"Javier Quino Favero"}


# ---------------------------------------------------------------------------
# Envase y dimensiones
# ---------------------------------------------------------------------------

def test_el_envase_y_las_dimensiones_se_persisten(db):
    """La página 2 del formato es una tabla de fotos de envase con medidas."""
    declaracion = _persistir(
        db,
        tipo_envase="Bidón de plástico",
        ancho_cm=18.0,
        alto_cm=28.0,
        profundidad_cm=18.0,
    )

    assert declaracion.tipo_envase is not None
    assert declaracion.tipo_envase.nombre == "Bidón de plástico"
    assert (declaracion.ancho_cm, declaracion.alto_cm, declaracion.profundidad_cm) == (
        18.0, 28.0, 18.0
    )


def test_una_descripcion_libre_de_envase_cae_en_su_tipo_canonico(db):
    """El histórico trae 50 escrituras de unos pocos conceptos."""
    declaracion = _persistir(db, tipo_envase="Frasco de Vidrio Oscuro")

    assert declaracion.tipo_envase.nombre == "Envase de vidrio ámbar"


def test_un_envase_indescifrable_queda_sin_tipo_y_no_mal_clasificado(db):
    """Un envase mal clasificado es peor que uno sin clasificar."""
    declaracion = _persistir(db, tipo_envase="Recipiente")

    assert declaracion.tipo_envase_id is None


def test_el_envase_es_opcional(db):
    declaracion = _persistir(db)

    assert declaracion.tipo_envase_id is None
    assert declaracion.ancho_cm is None


@pytest.mark.parametrize("dimension", ["ancho_cm", "alto_cm", "profundidad_cm"])
def test_una_dimension_en_cero_se_rechaza(db, dimension):
    """Cero no es una medida: es el campo sin llenar disfrazado de dato."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _entrada(**{dimension: 0})


@pytest.mark.parametrize("columna", ["ancho_cm", "alto_cm", "profundidad_cm"])
def test_la_base_tambien_rechaza_una_dimension_en_cero(db, columna):
    """La restricción vive en la base, no solo en la validación de entrada."""
    from tests.test_persistencia import _fila_declaracion

    declaracion = _fila_declaracion(db, **{columna: 0.0})
    db.add(declaracion)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ---------------------------------------------------------------------------
# La clasificación es una propuesta
# ---------------------------------------------------------------------------

def test_una_declaracion_nace_como_propuesta_sin_confirmar(db):
    declaracion = _persistir(db)

    assert declaracion.categoria_propuesta_id == declaracion.categoria_id
    assert declaracion.clasificacion_confirmada is False
    assert declaracion.confirmada_por is None


def test_aceptar_la_propuesta_deja_constancia_sin_cambiar_la_categoria(db):
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion

    declaracion = _persistir(db)
    categoria_antes = declaracion.categoria_id

    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.ACEPTADA,
        confirmada_por="Lic. Álvarez",
    ))

    assert declaracion.categoria_id == categoria_antes
    assert declaracion.clasificacion_confirmada is True
    assert declaracion.confirmada_por == "Lic. Álvarez"
    assert declaracion.confirmada_en is not None


def test_corregir_conserva_lo_que_propuso_el_sistema(db):
    """Es lo que permite medir después cuánto acierta el clasificador."""
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion

    declaracion = _persistir(db, insumos=["ácido sulfúrico 98%"])
    propuesta = declaracion.categoria_id
    assert propuesta == "acidos-corrosivos"

    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.CORREGIDA,
        categoria_id="metales-pesados",
        confirmada_por="Ing. Ramírez",
        motivo="Contiene sulfato de cobre residual",
    ))

    assert declaracion.categoria_id == "metales-pesados"
    # La propuesta original no se pierde al sobrescribirla.
    assert declaracion.categoria_propuesta_id == propuesta
    assert declaracion.clasificacion_confirmada is True


def test_una_categoria_elegida_por_una_persona_tiene_confianza_alta(db):
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion

    # Sin insumos reconocibles, el sistema deduce con confianza baja.
    declaracion = _persistir(db, insumos=[], descripcion="Residuo de práctica")
    assert declaracion.confianza == "Bajo"

    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.CORREGIDA,
        categoria_id="acidos-corrosivos",
        confirmada_por="Ing. Ramírez",
    ))

    assert declaracion.confianza == "Alto"


def test_identificar_un_residuo_lo_saca_de_evaluacion(db):
    """Si alguien reconoce la categoría, el motivo del escalamiento desaparece."""
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion

    declaracion = _persistir(db, insumos=[], descripcion="Frasco sin etiquetar")
    assert declaracion.escalar_csbqr is True
    assert declaracion.estado == "EN_EVALUACION"

    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.CORREGIDA,
        categoria_id="acidos-corrosivos",
        confirmada_por="Ing. Ramírez",
    ))

    assert declaracion.escalar_csbqr is False
    assert declaracion.estado == "GENERADO"


def test_corregir_hacia_una_categoria_que_escala_vuelve_a_evaluacion(db):
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion

    declaracion = _persistir(db, insumos=["ácido sulfúrico 98%"])
    assert declaracion.escalar_csbqr is False

    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.CORREGIDA,
        categoria_id="radiactivos",
        confirmada_por="Ing. Ramírez",
    ))

    assert declaracion.escalar_csbqr is True
    assert declaracion.estado == "EN_EVALUACION"


def test_corregir_un_residuo_ya_trasladado_no_lo_devuelve_al_laboratorio(db):
    """El kardex dice dónde está el residuo; corregir su etiqueta no lo mueve."""
    from core.models import (
        CambioEstadoRequest, ConfirmacionCategoriaRequest, DecisionClasificacion,
        EstadoResiduo,
    )
    from core.repositorio import cambiar_estado, confirmar_clasificacion

    declaracion = _persistir(db, insumos=["ácido sulfúrico 98%"])
    cambiar_estado(db, declaracion, CambioEstadoRequest(
        estado_destino=EstadoResiduo.EN_TRASLADO, registrado_por="Operador",
    ))

    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.CORREGIDA,
        categoria_id="metales-pesados",
        confirmada_por="Ing. Ramírez",
    ))

    assert declaracion.categoria_id == "metales-pesados"
    assert declaracion.estado == "EN_TRASLADO"


def test_no_se_reclasifica_un_residuo_ya_entregado(db):
    """Un residuo DISPUESTO salió con la clasificación que se declaró."""
    from core.models import (
        CambioEstadoRequest, ConfirmacionCategoriaRequest, DecisionClasificacion,
        EstadoResiduo,
    )
    from core.repositorio import TransicionInvalida, cambiar_estado, confirmar_clasificacion

    declaracion = _persistir(db, insumos=["ácido sulfúrico 98%"])
    for destino in (
        EstadoResiduo.EN_TRASLADO, EstadoResiduo.ALMACENADO, EstadoResiduo.DISPUESTO,
    ):
        cambiar_estado(db, declaracion, CambioEstadoRequest(
            estado_destino=destino, registrado_por="Operador",
        ))

    with pytest.raises(TransicionInvalida):
        confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
            decision=DecisionClasificacion.CORREGIDA,
            categoria_id="metales-pesados",
            confirmada_por="Ing. Ramírez",
        ))


def test_la_revision_queda_en_el_kardex(db):
    """Un cambio sin movimiento sería un cambio sin rastro."""
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion, kardex_de

    declaracion = _persistir(db, insumos=["ácido sulfúrico 98%"])
    confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
        decision=DecisionClasificacion.CORREGIDA,
        categoria_id="metales-pesados",
        confirmada_por="Ing. Ramírez",
    ))

    movimientos = kardex_de(db, declaracion)
    ajuste = movimientos[-1]

    assert ajuste.tipo_movimiento == "AJUSTE"
    assert ajuste.motivo == "correccion"
    assert ajuste.registrado_por == "Ing. Ramírez"
    assert "Ácidos" in ajuste.observacion and "metales" in ajuste.observacion.lower()
    # Corregir la etiqueta no mueve masa.
    assert ajuste.cantidad_g is None


def test_corregir_exige_indicar_la_categoria(db):
    from pydantic import ValidationError

    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion

    with pytest.raises(ValidationError):
        ConfirmacionCategoriaRequest(
            decision=DecisionClasificacion.CORREGIDA, confirmada_por="Alguien",
        )


def test_aceptar_no_admite_otra_categoria(db):
    """Cambiar la categoría es corregir, no aceptar: el nombre importa."""
    from pydantic import ValidationError

    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion

    with pytest.raises(ValidationError):
        ConfirmacionCategoriaRequest(
            decision=DecisionClasificacion.ACEPTADA,
            categoria_id="acidos-corrosivos",
            confirmada_por="Alguien",
        )


def test_corregir_hacia_la_misma_categoria_se_rechaza(db):
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import confirmar_clasificacion

    declaracion = _persistir(db, insumos=["ácido sulfúrico 98%"])

    with pytest.raises(ValueError):
        confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
            decision=DecisionClasificacion.CORREGIDA,
            categoria_id=declaracion.categoria_id,
            confirmada_por="Ing. Ramírez",
        ))


def test_corregir_hacia_una_categoria_inexistente_se_rechaza(db):
    from core.models import ConfirmacionCategoriaRequest, DecisionClasificacion
    from core.repositorio import DatoMaestroFaltante, confirmar_clasificacion

    declaracion = _persistir(db)

    with pytest.raises(DatoMaestroFaltante):
        confirmar_clasificacion(db, declaracion, ConfirmacionCategoriaRequest(
            decision=DecisionClasificacion.CORREGIDA,
            categoria_id="categoria-inventada",
            confirmada_por="Ing. Ramírez",
        ))


# ---------------------------------------------------------------------------
# Regla de escalamiento, en un solo lugar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "insumo, categoria",
    [
        # Con tilde, como se escribe en un teclado de ordenador.
        ("ácido sulfúrico 98%", "acidos-corrosivos"),
        ("hidróxido de sodio", "bases-corrosivas"),
        ("peróxido de hidrógeno", "oxidantes"),
        # Sin tilde, como se escribe en un teléfono: poner la tilde exige
        # mantener pulsada la tecla, y en un laboratorio con guantes no se hace.
        ("acido sulfurico 98%", "acidos-corrosivos"),
        ("hidroxido de sodio", "bases-corrosivas"),
        ("peroxido de hidrogeno", "oxidantes"),
        ("ACIDO CLORHIDRICO", "acidos-corrosivos"),
        ("Acido Nitrico", "acidos-corrosivos"),
    ],
)
def test_la_escritura_con_o_sin_tilde_da_la_misma_categoria(db, insumo, categoria):
    """La tilde no puede decidir la clasificación de un residuo peligroso.

    Antes cada lista de palabras clave decidía por su cuenta si incluir las dos
    escrituras: "peroxido" y "bateria" estaban, pero "acido", "sulfurico" e
    "hidroxido" no. Declarar "acido sulfurico" desde un teléfono devolvía "no
    identificado" y escalaba al CSBQR sin motivo.
    """
    declaracion = _persistir(db, insumos=[insumo])

    assert declaracion.categoria_id == categoria
    assert declaracion.escalar_csbqr is False


def test_la_regla_de_escalamiento_es_la_misma_al_clasificar_y_al_corregir(db):
    """Con la regla escrita dos veces, corregir podía desescalar indebidamente."""
    from core.models import requiere_escalamiento

    assert requiere_escalamiento("no-identificados") is True
    assert requiere_escalamiento("radiactivos") is True
    assert requiere_escalamiento("acidos-corrosivos") is False
    # Marcar "composición desconocida" escala aunque la categoría no lo haga.
    assert requiere_escalamiento("acidos-corrosivos", desconocido=True) is True
