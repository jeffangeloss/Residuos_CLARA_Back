"""Generación de los códigos del sistema, con los formatos del proceso real.

El circuito anterior manejaba tres identificadores distintos, y conviene
mantener esa separación porque cumplen funciones diferentes:

    Id_Registro   DDMMAAAAnnnnnn-XXXX   único, identifica la visita
    Id_Residuo    DDMMAAAAnnnnnn-XXXX   único, identifica el envase
    Código        DDMMAAAA-ESTADO-NNN   legible, va en el formato oficial

El tercero **no es único a nivel global**: en el histórico hay 856 residuos con
solo 779 códigos distintos, porque se numera dentro de cada registro. Por eso no
sirve como clave y existe el Id_Residuo por separado.
"""

import unicodedata
from datetime import date
from typing import Optional

LONGITUD_SUFIJO = 4
LONGITUD_SECUENCIA = 6
LONGITUD_ESTADO = 6


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def sufijo_persona(nombre: str) -> str:
    """Cuatro letras derivadas del nombre, como en los códigos históricos.

    Ejemplos del histórico: "Silvia Ponce" → SPON, "Javier Quino" → JQUI.
    Se toma la inicial de cada palabra y se completa con las letras siguientes
    del último apellido hasta llegar a cuatro.
    """
    palabras = [p for p in _sin_acentos(nombre).upper().split() if p.isalpha()]
    if not palabras:
        return "XXXX"

    iniciales = "".join(p[0] for p in palabras)[:LONGITUD_SUFIJO]
    if len(iniciales) == LONGITUD_SUFIJO:
        return iniciales

    # Faltan letras: se completan con el resto del último apellido.
    relleno = palabras[-1][1:]
    codigo = iniciales[:-1] + palabras[-1][0] + relleno
    return (codigo + "XXXX")[:LONGITUD_SUFIJO]


def token_fecha(momento: date) -> str:
    return momento.strftime("%d%m%Y")


def codigo_identificador(momento: date, secuencia: int, nombre: str) -> str:
    """Construye un Id_Registro o un Id_Residuo.

    La secuencia se lleva por fecha, no por persona: así la unicidad queda
    garantizada por la propia fecha y el correlativo, sin depender de que dos
    nombres distintos produzcan sufijos distintos.
    """
    return f"{token_fecha(momento)}{secuencia:0{LONGITUD_SECUENCIA}d}-{sufijo_persona(nombre)}"


def token_estado(estado_fisico: str) -> str:
    """Token de seis letras del estado físico: 'Líquido' → LIQUID."""
    limpio = _sin_acentos(estado_fisico or "").upper()
    solo_letras = "".join(c for c in limpio if c.isalpha())
    return (solo_letras or "OTRO")[:LONGITUD_ESTADO]


def codigo_formato(momento: date, estado_fisico: str, correlativo: int) -> str:
    """Construye el 'Código' legible que se imprime en el formato oficial.

    El correlativo se numera dentro del registro, empezando en 1.
    """
    return f"{token_fecha(momento)}-{token_estado(estado_fisico)}-{correlativo:03d}"


def siguiente_secuencia(usados: Optional[set], momento: date) -> int:
    """Primer correlativo libre para una fecha, dado el conjunto ya usado."""
    prefijo = token_fecha(momento)
    ocupados = {
        int(codigo[len(prefijo):len(prefijo) + LONGITUD_SECUENCIA])
        for codigo in (usados or set())
        if codigo.startswith(prefijo)
        and codigo[len(prefijo):len(prefijo) + LONGITUD_SECUENCIA].isdigit()
    }
    secuencia = 0
    while secuencia in ocupados:
        secuencia += 1
    return secuencia
