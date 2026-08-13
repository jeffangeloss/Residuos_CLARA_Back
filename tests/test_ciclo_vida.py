"""Pruebas del ciclo de vida del residuo, el kardex y los filtros de historial."""

import pytest

from tests.test_persistencia import _persistir


def _cambio(estado_destino, **cambios):
    from core.models import CambioEstadoRequest

    datos = {"estado_destino": estado_destino, "registrado_por": "Lic. Álvarez"}
    datos.update(cambios)
    return CambioEstadoRequest(**datos)


# --------------------------------------------------------------------------
# Transiciones de estado
# --------------------------------------------------------------------------

def test_recorrido_completo_hasta_disposicion(db):
    from core.repositorio import cambiar_estado

    declaracion = _persistir(db)
    assert declaracion.estado == "GENERADO"

    for destino in ("EN_TRASLADO", "ALMACENADO", "DISPUESTO"):
        cambiar_estado(db, declaracion, _cambio(destino))
        assert declaracion.estado == destino

    # Un movimiento de entrada al crear más uno por cada transición.
    assert len(declaracion.movimientos) == 4


def test_cada_transicion_registra_su_movimiento(db):
    from core.repositorio import cambiar_estado

    declaracion = _persistir(db)

    movimiento = cambiar_estado(db, declaracion, _cambio("EN_TRASLADO"))
    assert movimiento.tipo_movimiento == "TRANSFERENCIA"
    assert movimiento.motivo == "traslado_acopio"
    assert movimiento.cantidad_g == declaracion.peso_neto_g
    assert movimiento.registrado_por == "Lic. Álvarez"

    movimiento = cambiar_estado(db, declaracion, _cambio("ALMACENADO"))
    assert movimiento.tipo_movimiento == "ENTRADA"

    movimiento = cambiar_estado(db, declaracion, _cambio("DISPUESTO"))
    assert movimiento.tipo_movimiento == "SALIDA"
    assert movimiento.motivo == "entrega_eors"


def test_salto_de_estado_no_permitido_es_rechazado(db):
    from core.repositorio import TransicionInvalida, cambiar_estado

    declaracion = _persistir(db)

    with pytest.raises(TransicionInvalida):
        cambiar_estado(db, declaracion, _cambio("DISPUESTO"))

    assert declaracion.estado == "GENERADO"


def test_residuo_dispuesto_es_estado_terminal(db):
    from core.repositorio import TransicionInvalida, cambiar_estado

    declaracion = _persistir(db)
    for destino in ("EN_TRASLADO", "ALMACENADO", "DISPUESTO"):
        cambiar_estado(db, declaracion, _cambio(destino))

    with pytest.raises(TransicionInvalida):
        cambiar_estado(db, declaracion, _cambio("EN_TRASLADO"))


def test_repetir_el_estado_actual_es_rechazado(db):
    from core.repositorio import TransicionInvalida, cambiar_estado

    declaracion = _persistir(db)

    with pytest.raises(TransicionInvalida):
        cambiar_estado(db, declaracion, _cambio("GENERADO"))


def test_transicion_invalida_no_deja_movimiento_suelto(db):
    from core.db_models import MovimientoKardexDB
    from core.repositorio import TransicionInvalida, cambiar_estado

    declaracion = _persistir(db)
    movimientos_previos = db.query(MovimientoKardexDB).count()

    with pytest.raises(TransicionInvalida):
        cambiar_estado(db, declaracion, _cambio("DISPUESTO"))

    assert db.query(MovimientoKardexDB).count() == movimientos_previos


def test_residuo_en_evaluacion_vuelve_a_generado_al_resolverse(db):
    from core.repositorio import cambiar_estado

    declaracion = _persistir(db, desconocido=True, insumos=[])
    assert declaracion.estado == "EN_EVALUACION"

    cambiar_estado(db, declaracion, _cambio("GENERADO", observacion="CSBQR identificó el residuo"))

    assert declaracion.estado == "GENERADO"
    assert declaracion.movimientos[-1].motivo == "correccion"
    assert declaracion.movimientos[-1].observacion == "CSBQR identificó el residuo"


def test_traslado_registra_el_laboratorio_destino(db):
    from core.repositorio import cambiar_estado

    declaracion = _persistir(db)

    movimiento = cambiar_estado(
        db, declaracion, _cambio("EN_TRASLADO", laboratorio_destino="Acopio Central")
    )

    assert movimiento.laboratorio_origen_id == declaracion.registro.laboratorio_id
    assert movimiento.laboratorio_destino.nombre == "Acopio Central"
    # El destino se crea dentro de la dependencia del laboratorio de origen.
    assert movimiento.laboratorio_destino.dependencia_id == declaracion.laboratorio.dependencia_id


# --------------------------------------------------------------------------
# Kardex
# --------------------------------------------------------------------------

def test_kardex_devuelve_la_traza_en_orden(db):
    from core.repositorio import cambiar_estado, kardex_de

    declaracion = _persistir(db)
    cambiar_estado(db, declaracion, _cambio("EN_TRASLADO"))
    cambiar_estado(db, declaracion, _cambio("ALMACENADO"))

    movimientos = kardex_de(db, declaracion)

    assert [m.tipo_movimiento for m in movimientos] == ["ENTRADA", "TRANSFERENCIA", "ENTRADA"]
    assert [m.motivo for m in movimientos] == [
        "generacion_laboratorio", "traslado_acopio", "traslado_acopio",
    ]


def test_kardex_de_un_residuo_no_incluye_movimientos_de_otro(db):
    from core.repositorio import cambiar_estado, kardex_de

    primera = _persistir(db)
    segunda = _persistir(db)
    cambiar_estado(db, segunda, _cambio("EN_TRASLADO"))

    assert len(kardex_de(db, primera)) == 1
    assert len(kardex_de(db, segunda)) == 2


# --------------------------------------------------------------------------
# Filtros de historial (RF-08)
# --------------------------------------------------------------------------

def test_historial_sin_filtros_devuelve_todo_lo_reciente_primero(db):
    from core.repositorio import filtrar_declaraciones

    _persistir(db, fecha="2026-07-01")
    _persistir(db, fecha="2026-09-01")
    _persistir(db, fecha="2026-08-01")

    pagina, total = filtrar_declaraciones(db)

    assert total == 3
    assert [d.fecha.isoformat() for d in pagina] == ["2026-09-01", "2026-08-01", "2026-07-01"]


def test_historial_filtra_por_periodo_y_por_ano_completo(db):
    from core.repositorio import filtrar_declaraciones

    _persistir(db, fecha="2026-08-10")
    _persistir(db, fecha="2026-09-10")
    _persistir(db, fecha="2027-01-10")

    _, total_agosto = filtrar_declaraciones(db, mes=8, anio=2026)
    _, total_2026 = filtrar_declaraciones(db, anio=2026)

    assert total_agosto == 1
    assert total_2026 == 2


def test_historial_filtra_por_estado_y_escalamiento(db):
    from core.repositorio import cambiar_estado, filtrar_declaraciones

    normal = _persistir(db)
    _persistir(db, desconocido=True, insumos=[])
    cambiar_estado(db, normal, _cambio("EN_TRASLADO"))

    _, en_traslado = filtrar_declaraciones(db, estado="EN_TRASLADO")
    _, escalados = filtrar_declaraciones(db, escalar_csbqr=True)
    _, no_escalados = filtrar_declaraciones(db, escalar_csbqr=False)

    assert en_traslado == 1
    assert escalados == 1
    assert no_escalados == 1


def test_historial_filtra_por_categoria(db):
    from core.repositorio import filtrar_declaraciones

    _persistir(db)  # acidos-corrosivos
    _persistir(db, insumos=["acetona"])  # solventes-no-halogenados

    _, acidos = filtrar_declaraciones(db, categoria_id="acidos-corrosivos")

    assert acidos == 1


def test_historial_filtra_por_laboratorio_exacto(db):
    from core.repositorio import filtrar_declaraciones

    _persistir(db, laboratorio="Química General")
    _persistir(db, laboratorio="Química Analítica")

    _, general = filtrar_declaraciones(db, laboratorio="Química General")

    assert general == 1


def test_laboratorio_inexistente_no_devuelve_todo(db):
    """Un filtro sin coincidencias debe dar cero, no degradarse a 'todos'."""
    from core.repositorio import filtrar_declaraciones

    _persistir(db)

    pagina, total = filtrar_declaraciones(db, laboratorio="Laboratorio Fantasma")

    assert total == 0
    assert pagina == []


def test_paginacion_devuelve_el_total_sin_paginar(db):
    from core.repositorio import filtrar_declaraciones

    for dia in range(1, 6):
        _persistir(db, fecha=f"2026-08-{dia:02d}")

    pagina, total = filtrar_declaraciones(db, limite=2, desplazamiento=0)
    siguiente, _ = filtrar_declaraciones(db, limite=2, desplazamiento=2)

    assert total == 5
    assert len(pagina) == 2
    assert len(siguiente) == 2
    assert {d.id for d in pagina}.isdisjoint({d.id for d in siguiente})
