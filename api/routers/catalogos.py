"""Catálogos institucionales: los desplegables que necesita la captura."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from core.db_models import CategoriaULimaDB, DependenciaDB, TipoEnvaseDB
from core.models import EXIGIR_PESAJE_EN_KG, EstadoFisico, Origen, Unidad
from core.response import success_response

router = APIRouter(prefix="/api/v1", tags=["catalogos"])


@router.get("/catalogos")
def obtener_catalogos(db: Session = Depends(get_db)):
    """Todos los desplegables de la captura, en una sola llamada.

    El móvil los pide una vez al abrir la visita y ya no vuelve a escribir un
    nombre a mano. Los formularios de Google permitían texto libre y el
    resultado son 50 escrituras de "envase de plástico" y la misma persona
    contada tres veces.
    """
    dependencias = db.query(DependenciaDB).order_by(DependenciaDB.nombre.asc()).all()
    categorias = db.query(CategoriaULimaDB).order_by(CategoriaULimaDB.nombre.asc()).all()
    envases = db.query(TipoEnvaseDB).order_by(TipoEnvaseDB.nombre.asc()).all()

    return success_response(
        message="Catálogos institucionales vigentes",
        data={
            "dependencias": [
                {
                    "id": dependencia.id,
                    "codigo": dependencia.codigo,
                    "nombre": dependencia.nombre,
                    "token_formato": dependencia.token_formato,
                    "en_catalogo_oficial": dependencia.en_catalogo_oficial,
                    "laboratorios": [
                        {
                            "id": laboratorio.id,
                            "codigo": laboratorio.codigo,
                            "nombre": laboratorio.nombre,
                            "en_catalogo_oficial": laboratorio.en_catalogo_oficial,
                        }
                        for laboratorio in sorted(
                            dependencia.laboratorios, key=lambda lab: lab.nombre
                        )
                    ],
                }
                for dependencia in dependencias
            ],
            "tipos_envase": [
                {"id": envase.id, "codigo": envase.codigo, "nombre": envase.nombre}
                for envase in envases
            ],
            "categorias": [
                {
                    "id": categoria.id,
                    "nombre": categoria.nombre,
                    "caracteristica_principal": categoria.caracteristica_principal,
                    "caracteristica_declaracion": categoria.caracteristica_declaracion,
                    "clase_sunat": categoria.clase_sunat,
                    "clase_basilea": categoria.clase_basilea,
                    "grupo_compatibilidad": categoria.grupo_compatibilidad,
                    "envase_recomendado": categoria.envase_recomendado,
                    "no_mezclar_con": categoria.no_mezclar_con,
                }
                for categoria in categorias
            ],
            "origenes": [origen.value for origen in Origen],
            "estados_fisicos": [estado.value for estado in EstadoFisico],
            "unidades": [unidad.value for unidad in Unidad],
            # La captura móvil consulta esta bandera para decidir si el pesaje
            # es obligatorio, en vez de repetir la política en el cliente.
            "exigir_pesaje_en_kg": EXIGIR_PESAJE_EN_KG,
        },
    )
