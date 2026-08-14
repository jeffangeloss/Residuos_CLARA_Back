"""Integración de la API de captura móvil, extremo a extremo.

Recorre el flujo real de una visita tal como lo hará la app: pedir catálogos y
padrón, abrir el registro, subir la foto, declarar dos residuos contra la misma
cabecera, revisar la propuesta y verificar el acopio.

Las pruebas de `test_captura_movil.py` verifican el dominio; estas verifican que
el contrato HTTP que consume Flutter es el que se espera.
"""

import os
import sys

import pytest

RAIZ_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def cliente(db, tmp_path, monkeypatch):
    """Cliente HTTP contra la base migrada y sembrada de la prueba."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ALMACENAMIENTO_FOTOS", str(tmp_path / "fotos"))
    for modulo in list(sys.modules):
        if modulo == "main" or modulo.startswith("api."):
            sys.modules.pop(modulo, None)

    from core.database import get_db
    import main

    main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


def _datos(respuesta):
    assert respuesta.status_code < 400, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True, cuerpo
    return cuerpo["data"]


# ---------------------------------------------------------------------------
# Catálogos y padrón
# ---------------------------------------------------------------------------

def test_los_catalogos_traen_todo_lo_que_pide_la_captura(cliente):
    catalogos = _datos(cliente.get("/api/v1/catalogos"))

    assert len(catalogos["dependencias"]) == 7
    assert len(catalogos["tipos_envase"]) == 14
    assert len(catalogos["categorias"]) == 15
    assert catalogos["origenes"] == ["Académico", "Proyecto", "Otros"]
    assert catalogos["estados_fisicos"] == ["Líquido", "Sólido"]
    # La política de pesaje vive en el backend; el móvil la consulta.
    assert catalogos["exigir_pesaje_en_kg"] is True


def test_los_laboratorios_cuelgan_de_su_dependencia(cliente):
    catalogos = _datos(cliente.get("/api/v1/catalogos"))
    por_nombre = {d["nombre"]: d for d in catalogos["dependencias"]}

    industrial = por_nombre["Ingeniería Industrial"]
    assert len(industrial["laboratorios"]) == 14
    assert "Química General" in {lab["nombre"] for lab in industrial["laboratorios"]}
    # Homónimo en otra dependencia: no debe absorber sus declaraciones.
    ambiental = por_nombre["Ingeniería Ambiental"]
    assert "Docimasia" in {lab["nombre"] for lab in ambiental["laboratorios"]}


def test_el_padron_se_consulta_por_papel(cliente):
    encargados = _datos(cliente.get("/api/v1/personal", params={"rol": "encargado"}))
    assert all(persona["es_encargado"] for persona in encargados)
    assert "Henrry Delgado Ortega" in {p["nombre"] for p in encargados}


def test_el_padron_expone_las_variantes_de_cada_nombre(cliente):
    resultados = _datos(cliente.get("/api/v1/personal", params={"buscar": "quino"}))

    assert len(resultados) == 1
    assert resultados[0]["nombre"] == "Javier Quino Favero"
    assert "Javier Quino" in resultados[0]["alias"]


def test_dar_de_alta_a_alguien_nuevo_desde_la_app(cliente):
    persona = _datos(cliente.post("/api/v1/personal", json={
        "nombre": "Tesista Recién Llegado",
        "dependencia": "Ingeniería Industrial",
    }))

    assert persona["en_catalogo_oficial"] is False
    assert persona["dependencia"] == "Ingeniería Industrial"


# ---------------------------------------------------------------------------
# Fotografías
# ---------------------------------------------------------------------------

# PNG mínimo válido de 1x1 px.
PNG_MINIMO = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def test_subir_una_foto_devuelve_la_url_para_referenciarla(cliente):
    datos = _datos(cliente.post(
        "/api/v1/fotos",
        files={"archivo": ("envase.png", PNG_MINIMO, "image/png")},
    ))

    assert datos["foto_url"].startswith("/api/v1/fotos/")
    assert datos["bytes"] == len(PNG_MINIMO)

    # Y se puede leer de vuelta.
    assert cliente.get(datos["foto_url"]).status_code == 200


def test_un_archivo_que_no_es_imagen_se_rechaza(cliente):
    respuesta = cliente.post(
        "/api/v1/fotos",
        files={"archivo": ("credenciales.json", b"{}", "application/json")},
    )
    assert respuesta.status_code == 422


def test_no_se_puede_leer_un_archivo_fuera_del_almacen(cliente):
    """Un nombre con `../` serviría cualquier archivo del servidor."""
    respuesta = cliente.get("/api/v1/fotos/..%2F..%2F.env")
    assert respuesta.status_code in (400, 404)


# ---------------------------------------------------------------------------
# El flujo completo de una visita
# ---------------------------------------------------------------------------

def _abrir_visita(cliente):
    return _datos(cliente.post("/api/v1/registros", json={
        "dependencia": "Ingeniería Industrial",
        "laboratorio": "Química General",
        "responsable_encargado": "Javier Quino Favero",
        "elaborado_por": "Christian Querevalú Borja",
        "fecha": "2026-08-13",
        "telefono_contacto": "987654321",
    }))


def _declarar(cliente, id_registro, **cambios):
    cuerpo = {
        "actividad": "Titulación ácido-base",
        "origen": "Académico",
        "responsable": "Silvia Ponce",
        "descripcion": "Solución residual de ácido sulfúrico 98%",
        "insumos": ["ácido sulfúrico 98%", "agua destilada"],
        "estado_fisico": "Líquido",
        "peso_bruto_g": 3100.0,
        "tara_g": 600.0,
        "ph": 1.0,
        "tipo_envase": "Bidón de plástico",
        "ancho_cm": 18.0,
        "alto_cm": 28.0,
        "profundidad_cm": 18.0,
    }
    cuerpo.update(cambios)
    return _datos(cliente.post(f"/api/v1/registros/{id_registro}/residuos", json=cuerpo))


def test_una_visita_con_varios_residuos_en_una_sola_sesion(cliente):
    """La ganancia central del proyecto sobre los dos formularios de Google."""
    visita = _abrir_visita(cliente)

    _declarar(cliente, visita["id_registro"])
    _declarar(
        cliente, visita["id_registro"],
        descripcion="Acetona residual de extracción",
        insumos=["acetona"],
        responsable="Fiama Norabuena",
    )

    completo = _datos(cliente.get(f"/api/v1/registros/{visita['id_registro']}"))

    assert completo["total_residuos"] == 2
    # La cabecera se llenó una vez y no se repite en cada envase.
    assert completo["responsable_encargado"] == "Javier Quino Favero"
    assert completo["telefono_contacto"] == "987654321"
    # Cada residuo conserva su propio responsable de generación.
    assert {r["responsable"] for r in completo["residuos"]} == {
        "Silvia Ponce", "Fiama Norabuena",
    }


def test_el_envase_las_dimensiones_y_la_foto_viajan_en_la_declaracion(cliente):
    foto = _datos(cliente.post(
        "/api/v1/fotos", files={"archivo": ("envase.png", PNG_MINIMO, "image/png")}
    ))
    visita = _abrir_visita(cliente)
    _declarar(cliente, visita["id_registro"], foto_url=foto["foto_url"])

    residuo = _datos(cliente.get(f"/api/v1/registros/{visita['id_registro']}"))["residuos"][0]

    assert residuo["tipo_envase"] == "Bidón de plástico"
    assert (residuo["ancho_cm"], residuo["alto_cm"], residuo["profundidad_cm"]) == (
        18.0, 28.0, 18.0
    )
    assert residuo["foto_url"] == foto["foto_url"]


def test_la_declaracion_devuelve_las_observaciones_de_manejo(cliente):
    """La app tiene que mostrarlas: son instrucciones, no adorno."""
    visita = _abrir_visita(cliente)
    _declarar(cliente, visita["id_registro"])

    residuo = _datos(cliente.get(f"/api/v1/registros/{visita['id_registro']}"))["residuos"][0]

    assert residuo["observaciones"]
    assert residuo["no_mezclar_con"]
    assert residuo["envase_recomendado"]


def test_revisar_la_propuesta_desde_la_app(cliente):
    visita = _abrir_visita(cliente)
    resultado = _declarar(cliente, visita["id_registro"])
    id_residuo = resultado["id_residuo"]

    revisado = _datos(cliente.post(
        f"/api/v1/declaraciones/{id_residuo}/categoria",
        json={"decision": "aceptada", "confirmada_por": "Christian Querevalú Borja"},
    ))

    assert revisado["clasificacion_confirmada"] is True
    assert revisado["clasificacion_corregida"] is False
    assert revisado["confirmada_por"] == "Christian Querevalú Borja"


def test_corregir_la_propuesta_desde_la_app(cliente):
    visita = _abrir_visita(cliente)
    resultado = _declarar(cliente, visita["id_registro"])

    corregido = _datos(cliente.post(
        f"/api/v1/declaraciones/{resultado['id_residuo']}/categoria",
        json={
            "decision": "corregida",
            "categoria_id": "metales-pesados",
            "confirmada_por": "Christian Querevalú Borja",
            "motivo": "Contiene sulfato de cobre residual",
        },
    ))

    assert corregido["categoria_id"] == "metales-pesados"
    assert corregido["categoria_propuesta_id"] == "acidos-corrosivos"
    assert corregido["clasificacion_corregida"] is True
    assert corregido["confianza"] == "Alto"


def test_corregir_hacia_una_categoria_inexistente_responde_422(cliente):
    visita = _abrir_visita(cliente)
    resultado = _declarar(cliente, visita["id_registro"])

    respuesta = cliente.post(
        f"/api/v1/declaraciones/{resultado['id_residuo']}/categoria",
        json={
            "decision": "corregida",
            "categoria_id": "no-existe",
            "confirmada_por": "Alguien",
        },
    )
    assert respuesta.status_code == 422


def test_el_acopio_se_verifica_contra_la_matriz_persistida(cliente):
    veredicto = _datos(cliente.post(
        "/api/v1/acopio/verificar", json=["ÁCIDO", "OXIDANTE"],
    ))
    assert veredicto["veredicto"] == "NUNCA"

    solo = _datos(cliente.post("/api/v1/acopio/verificar", json=["ÁCIDO"]))
    assert solo["veredicto"] == "COMPATIBLE"


def test_el_kardex_recoge_la_generacion_y_la_revision(cliente):
    visita = _abrir_visita(cliente)
    resultado = _declarar(cliente, visita["id_registro"])
    id_residuo = resultado["id_residuo"]

    cliente.post(
        f"/api/v1/declaraciones/{id_residuo}/categoria",
        json={
            "decision": "corregida",
            "categoria_id": "metales-pesados",
            "confirmada_por": "Christian Querevalú Borja",
        },
    )

    kardex = _datos(cliente.get(f"/api/v1/declaraciones/{id_residuo}/kardex"))
    tipos = [m["tipo_movimiento"] for m in kardex["movimientos"]]

    assert tipos == ["ENTRADA", "AJUSTE"]
    assert kardex["movimientos"][-1]["registrado_por"] == "Christian Querevalú Borja"


def test_la_etiqueta_se_genera_para_un_residuo_declarado(cliente):
    visita = _abrir_visita(cliente)
    resultado = _declarar(cliente, visita["id_registro"])

    respuesta = cliente.get(f"/api/v1/etiqueta/{resultado['id_residuo']}/pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")


def test_declarar_sin_pesar_se_rechaza(cliente):
    """Decisión del 2026-08-13: toda declaración nueva se pesa en balanza."""
    visita = _abrir_visita(cliente)

    respuesta = cliente.post(f"/api/v1/registros/{visita['id_registro']}/residuos", json={
        "actividad": "Práctica",
        "responsable": "Silvia Ponce",
        "descripcion": "Residuo líquido",
        "estado_fisico": "Líquido",
    })
    assert respuesta.status_code == 422


def test_declarar_contra_un_registro_inexistente_responde_404(cliente):
    respuesta = cliente.post("/api/v1/registros/00000000000000-XXXX/residuos", json={
        "actividad": "Práctica",
        "responsable": "Silvia Ponce",
        "descripcion": "Residuo",
        "peso_bruto_g": 1000.0,
    })
    assert respuesta.status_code == 404
