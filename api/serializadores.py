"""Traducción de las entidades de la base a los diccionarios que ve el cliente.

Está aparte de los routers a propósito: una declaración se serializa en cuatro
sitios —el listado, el registro con sus residuos, la confirmación de categoría y
el panel—, y con la traducción repetida en cada uno, añadir un campo obligaba a
acordarse de los cuatro. Es lo que hizo que `estado_fisico` y la foto llegaran a
unos clientes y a otros no.
"""

from core.db_models import DeclaracionResiduoDB, MovimientoKardexDB, PersonaDB, RegistroDB


def serializar_declaracion(declaracion: DeclaracionResiduoDB) -> dict:
    registro = declaracion.registro
    laboratorio = declaracion.laboratorio
    categoria = declaracion.categoria
    return {
        "id_residuo": declaracion.codigo_residuo,
        "codigo_formato": declaracion.codigo_formato,
        "id_registro": registro.codigo if registro else None,
        "responsable_encargado": registro.responsable_encargado if registro else None,
        "elaborado_por": registro.elaborado_por if registro else None,
        "dependencia": (
            laboratorio.dependencia.nombre
            if laboratorio and laboratorio.dependencia else None
        ),
        "laboratorio": laboratorio.nombre if laboratorio else None,
        "actividad": declaracion.actividad,
        "fecha": declaracion.fecha.isoformat(),
        "descripcion": declaracion.descripcion,
        "insumos": [insumo.nombre_quimico for insumo in declaracion.insumos],
        "pictogramas_ghs": [p.codigo_pictograma for p in declaracion.pictogramas],
        "observaciones": [o.texto for o in declaracion.observaciones],
        "estado_fisico": declaracion.estado_fisico,
        "origen": declaracion.origen,
        "responsable": declaracion.responsable,
        "ph": declaracion.ph,
        "foto_url": declaracion.foto_url,
        "tipo_envase": declaracion.tipo_envase.nombre if declaracion.tipo_envase else None,
        "ancho_cm": declaracion.ancho_cm,
        "alto_cm": declaracion.alto_cm,
        "profundidad_cm": declaracion.profundidad_cm,
        "envase_recomendado": categoria.envase_recomendado if categoria else None,
        "no_mezclar_con": categoria.no_mezclar_con if categoria else None,
        "narrativa": declaracion.narrativa,
        # La propuesta del sistema y lo que quedó vigente. Si difieren, alguien
        # corrigió; si `clasificacion_confirmada` es falso, nadie la ha visto.
        "categoria_id": declaracion.categoria_id,
        "categoria_propuesta_id": declaracion.categoria_propuesta_id,
        "categoria_propuesta_nombre": (
            declaracion.categoria_propuesta.nombre
            if declaracion.categoria_propuesta else None
        ),
        "clasificacion_confirmada": declaracion.clasificacion_confirmada,
        "clasificacion_corregida": (
            declaracion.categoria_propuesta_id is not None
            and declaracion.categoria_propuesta_id != declaracion.categoria_id
        ),
        "confirmada_por": declaracion.confirmada_por,
        "confirmada_en": (
            declaracion.confirmada_en.isoformat() if declaracion.confirmada_en else None
        ),
        "cantidad": declaracion.cantidad,
        "unidad": declaracion.unidad,
        "modo_medicion": declaracion.modo_medicion,
        "peso_bruto_g": declaracion.peso_bruto_g,
        "tara_g": declaracion.tara_g,
        "peso_neto_g": declaracion.peso_neto_g,
        # Solo tiene valor cuando la cantidad es una masa en kilogramos. En un
        # residuo declarado por volumen no existe tal cifra.
        "peso_neto_kg": declaracion.cantidad if declaracion.unidad == "Kg" else None,
        "categoria_nombre": categoria.nombre if categoria else None,
        "nombre_normalizado": declaracion.nombre_normalizado,
        "clase_sunat": categoria.clase_sunat if categoria else None,
        "clase_basilea": categoria.clase_basilea if categoria else None,
        "grupo_compatibilidad": categoria.grupo_compatibilidad if categoria else "AISLAR",
        "confianza": declaracion.confianza,
        "estado": declaracion.estado,
        "escalar_csbqr": declaracion.escalar_csbqr,
        "creado_en": declaracion.creado_en.isoformat() if declaracion.creado_en else None,
    }


def serializar_registro(registro: RegistroDB, incluir_residuos: bool = False) -> dict:
    laboratorio = registro.laboratorio
    datos = {
        "id_registro": registro.codigo,
        "dependencia": (
            laboratorio.dependencia.nombre
            if laboratorio and laboratorio.dependencia else None
        ),
        "laboratorio": laboratorio.nombre if laboratorio else None,
        "responsable_encargado": registro.responsable_encargado,
        "elaborado_por": registro.elaborado_por,
        "fecha": registro.fecha.isoformat(),
        "telefono_contacto": registro.telefono_contacto,
        "comentarios_generales": registro.comentarios_generales,
        "total_residuos": len(registro.declaraciones),
        "creado_en": registro.creado_en.isoformat() if registro.creado_en else None,
    }
    if incluir_residuos:
        datos["residuos"] = [
            serializar_declaracion(d)
            for d in sorted(registro.declaraciones, key=lambda d: d.id)
        ]
    return datos


def serializar_movimiento(movimiento: MovimientoKardexDB) -> dict:
    return {
        "id": movimiento.id,
        "tipo_movimiento": movimiento.tipo_movimiento,
        "motivo": movimiento.motivo,
        "cantidad_g": movimiento.cantidad_g,
        "laboratorio_origen": (
            movimiento.laboratorio_origen.nombre if movimiento.laboratorio_origen else None
        ),
        "laboratorio_destino": (
            movimiento.laboratorio_destino.nombre if movimiento.laboratorio_destino else None
        ),
        "registrado_por": movimiento.registrado_por,
        "registrado_en": movimiento.registrado_en.isoformat(),
        "observacion": movimiento.observacion,
    }


def serializar_persona(persona: PersonaDB) -> dict:
    return {
        "id": persona.id,
        "codigo": persona.codigo,
        "nombre": persona.nombre,
        "dependencia": persona.dependencia.nombre if persona.dependencia else None,
        "correo": persona.correo,
        "telefono": persona.telefono,
        "es_encargado": persona.es_encargado,
        "es_csbqr": persona.es_csbqr,
        "es_generador": persona.es_generador,
        "en_catalogo_oficial": persona.en_catalogo_oficial,
        "alias": [variante.alias_texto for variante in persona.alias],
    }
