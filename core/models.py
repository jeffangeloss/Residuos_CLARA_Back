"""
CORE V3 Database Models - FastAPI / SQLAlchemy (PostgreSQL)
Alineado a las buenas prácticas de desarrollo de CORE V3
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr

class TipoMovimiento(str, Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    TRANSFERENCIA = "TRANSFERENCIA"
    AJUSTE = "AJUSTE"

class MotivoMovimiento(str, Enum):
    GENERACION_LAB = "generacion_laboratorio"
    CONSUMO_LAB = "consumo_laboratorio"
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

class UsuarioBase(BaseModel):
    email: EmailStr
    nombre: str
    rol: str

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(UsuarioBase):
    id_usuario: int
    estado: str = "ACTIVO"

    class Config:
        from_attributes = True

class EntradaResiduoRequest(BaseModel):
    dependencia: str
    laboratorio: str
    actividad: str
    origen: str = "Académico"
    responsable: str
    elaborado_por: Optional[str] = None
    fecha: str
    descripcion: str
    insumos: List[str]
    estado_fisico: str = "Líquido"
    peso_bruto_g: float = Field(..., description="Peso medido en balanza en GRAMOS (Unidad Canónica)")
    tara_g: float = Field(0.0, description="Tara del envase en GRAMOS")
    ph: Optional[float] = None
    foto_url: Optional[str] = None
    es_punzocortante: bool = False
    es_biologico: bool = False
    es_aerosol: bool = False
    es_envase_vacio: bool = False
    desconocido: bool = False

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
    envase_recomendado: string
    peso_neto_g: float = Field(..., description="Peso en GRAMOS almacenado en BD")
    peso_neto_kg: float = Field(..., description="Conversión oficial ÷1000 a KG para la declaración")
    confianza: str
    observaciones: List[str]
    pictogramas_ghs: List[str]
    escalar_csbqr: bool
    narrativa: str

class MovimientoKardexRequest(BaseModel):
    id_residuo: str
    tipo_movimiento: TipoMovimiento
    motivo: MotivoMovimiento
    cantidad_g: float = Field(0.0, description="Cantidad en gramos. Para transferencias de custodia es 0")
    laboratorio_origen: Optional[str] = None
    laboratorio_destino: Optional[str] = None
    registrado_por: str
