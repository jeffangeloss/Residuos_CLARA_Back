"""Migra declaraciones desde la base heredada (esquema pre-Fase 3) al esquema vigente.

La base de origen se lee y nunca se modifica. Por defecto el script solo informa
lo que haría; hay que pasar `--aplicar` para escribir.

    venv/bin/python migrar_heredada.py \\
        --origen postgresql+psycopg2://usuario@localhost:5432/residuos_clara \\
        --destino postgresql+psycopg2://usuario@localhost:5432/residuos_clara_dev

    venv/bin/python migrar_heredada.py --origen ... --destino ... --aplicar

El esquema antiguo no tenía `nombre_normalizado`, `estado`, los indicadores de
entrada ni movimientos de kardex. Esos valores se derivan y cada derivación se
informa explícitamente: son reconstrucciones, no datos originales.
"""

import argparse
import os
import sys
from datetime import date, datetime, timezone
from typing import Dict, List

from sqlalchemy import create_engine, text


def parsear_argumentos():
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--origen", required=True, help="URL de la base heredada (solo lectura)")
    analizador.add_argument("--destino", required=True, help="URL de la base con el esquema vigente")
    analizador.add_argument(
        "--aplicar", action="store_true",
        help="Escribe los cambios. Sin este indicador solo se informa qué se haría.",
    )
    return analizador.parse_args()


def leer_origen(url_origen: str) -> Dict:
    """Extrae declaraciones y sus hijos del esquema antiguo mediante SQL directo.

    Se usa SQL y no el ORM porque los modelos actuales ya no describen ese
    esquema: `fecha` era texto y no existían varias de las columnas obligatorias.
    """
    motor = create_engine(url_origen)
    with motor.connect() as conexion:
        declaraciones = [
            dict(fila._mapping) for fila in conexion.execute(text("""
                SELECT d.*, l.nombre AS laboratorio_nombre,
                       dep.nombre AS dependencia_nombre
                FROM declaraciones d
                JOIN laboratorios l ON l.id = d.laboratorio_id
                JOIN dependencias dep ON dep.id = l.dependencia_id
                ORDER BY d.id
            """))
        ]

        insumos: Dict[int, List[str]] = {}
        for fila in conexion.execute(text(
            "SELECT declaracion_id, nombre_quimico FROM declaracion_insumos ORDER BY id"
        )):
            insumos.setdefault(fila.declaracion_id, []).append(fila.nombre_quimico)

        pictogramas: Dict[int, List[str]] = {}
        for fila in conexion.execute(text(
            "SELECT declaracion_id, codigo_pictograma FROM declaracion_pictogramas ORDER BY id"
        )):
            pictogramas.setdefault(fila.declaracion_id, []).append(fila.codigo_pictograma)

        dependencias_sin_uso = [
            fila.nombre for fila in conexion.execute(text("""
                SELECT dep.nombre FROM dependencias dep
                LEFT JOIN laboratorios l ON l.dependencia_id = dep.id
                WHERE l.id IS NULL
            """))
        ]

    motor.dispose()
    return {
        "declaraciones": declaraciones,
        "insumos": insumos,
        "pictogramas": pictogramas,
        "dependencias_sin_uso": dependencias_sin_uso,
    }


def _verificar_pesos(registro: Dict) -> List[str]:
    """Detecta incoherencias de peso antes de trasladar el registro."""
    problemas = []
    esperado = max(0.0, registro["peso_bruto_g"] - registro["tara_g"])
    if abs(registro["peso_neto_g"] - esperado) > 0.5:
        problemas.append(
            f"peso neto {registro['peso_neto_g']} g no coincide con bruto − tara ({esperado} g)"
        )
    if abs(registro["peso_neto_kg"] * 1000 - registro["peso_neto_g"]) > 1:
        problemas.append(
            f"peso en kg {registro['peso_neto_kg']} no coincide con {registro['peso_neto_g']} g"
        )
    return problemas


def migrar(datos: Dict, aplicar: bool) -> int:
    from core.classifier import ONTOLOGIA
    from core.database import SessionLocal
    from core.db_models import (
        CategoriaULimaDB, DeclaracionInsumoDB, DeclaracionObservacionDB,
        DeclaracionPictogramaDB, DeclaracionResiduoDB,
    )
    from core.models import EstadoResiduo, MotivoMovimiento, TipoMovimiento
    from core.repositorio import buscar_declaracion, registrar_movimiento, resolver_dependencia, resolver_laboratorio

    # Observaciones de manejo que el clasificador emite para todo residuo. Se
    # reconstruyen porque son salida determinista, no dato capturado.
    OBSERVACIONES_ESTANDAR = ["Llenar como máximo al 75%", "No verter al desagüe"]

    sesion = SessionLocal()
    migradas, omitidas, bloqueadas = 0, 0, 0

    try:
        for registro in datos["declaraciones"]:
            codigo = registro["codigo_residuo"]
            print(f"\n▶ {codigo}")

            if buscar_declaracion(sesion, codigo):
                print("  · ya existe en el destino, se omite")
                omitidas += 1
                continue

            problemas = _verificar_pesos(registro)
            if problemas:
                for problema in problemas:
                    print(f"  ✗ {problema}")
                print("  ✗ NO se migra: corrija el origen o decida el valor correcto")
                bloqueadas += 1
                continue

            categoria = sesion.get(CategoriaULimaDB, registro["categoria_id"])
            if categoria is None:
                print(
                    f"  ✗ la categoría '{registro['categoria_id']}' no existe en la ontología "
                    "vigente; requiere decisión del responsable de dominio"
                )
                bloqueadas += 1
                continue

            insumos = datos["insumos"].get(registro["id"], [])
            pictogramas = datos["pictogramas"].get(registro["id"], [])

            # Campos obligatorios del esquema nuevo que el antiguo no guardaba.
            nombre_normalizado = (
                f"Solución residual de {', '.join(insumos)}" if insumos
                else registro["descripcion"]
            )[:300]
            estado = (
                EstadoResiduo.EN_EVALUACION.value if registro["escalar_csbqr"]
                else EstadoResiduo.GENERADO.value
            )
            creado_en = registro["creado_en"] or datetime.now(timezone.utc)
            if creado_en.tzinfo is None:
                creado_en = creado_en.replace(tzinfo=timezone.utc)

            print(f"  · laboratorio: {registro['dependencia_nombre']} / {registro['laboratorio_nombre']}")
            print(f"  · categoría:   {categoria.nombre} ({categoria.grupo_compatibilidad})")
            print(f"  · peso:        {registro['peso_neto_g']} g = {registro['peso_neto_kg']} kg")
            print(f"  · insumos:     {insumos}")
            print(f"  ~ derivado: nombre_normalizado = '{nombre_normalizado}'")
            print(f"  ~ derivado: estado = {estado}")
            print("  ~ derivado: indicadores de entrada = todos falsos "
                  f"(la categoría '{registro['categoria_id']}' no los usa)")
            print(f"  ~ derivado: observaciones = {OBSERVACIONES_ESTANDAR}")
            print("  ~ derivado: movimiento de kardex ENTRADA reconstruido")

            if not aplicar:
                migradas += 1
                continue

            dependencia = resolver_dependencia(sesion, registro["dependencia_nombre"])
            laboratorio = resolver_laboratorio(
                sesion, registro["laboratorio_nombre"], dependencia, registro["responsable"]
            )

            declaracion = DeclaracionResiduoDB(
                codigo_residuo=codigo,
                laboratorio_id=laboratorio.id,
                categoria_id=categoria.id,
                actividad=registro["actividad"],
                origen=registro["origen"],
                responsable=registro["responsable"],
                fecha=date.fromisoformat(registro["fecha"]),
                descripcion=registro["descripcion"],
                nombre_normalizado=nombre_normalizado,
                estado_fisico=registro["estado_fisico"],
                peso_bruto_g=registro["peso_bruto_g"],
                tara_g=registro["tara_g"],
                peso_neto_g=registro["peso_neto_g"],
                peso_neto_kg=registro["peso_neto_kg"],
                ph=registro["ph"],
                confianza=registro["confianza"],
                estado=estado,
                escalar_csbqr=registro["escalar_csbqr"],
                narrativa=registro["narrativa"],
                creado_en=creado_en,
                actualizado_en=creado_en,
            )
            sesion.add(declaracion)
            sesion.flush()

            for nombre_quimico in dict.fromkeys(insumos):
                sesion.add(DeclaracionInsumoDB(
                    declaracion_id=declaracion.id, nombre_quimico=nombre_quimico
                ))
            for pictograma in dict.fromkeys(pictogramas):
                sesion.add(DeclaracionPictogramaDB(
                    declaracion_id=declaracion.id, codigo_pictograma=pictograma
                ))
            for texto in OBSERVACIONES_ESTANDAR:
                sesion.add(DeclaracionObservacionDB(declaracion_id=declaracion.id, texto=texto))

            movimiento = registrar_movimiento(
                sesion,
                declaracion,
                tipo=TipoMovimiento.ENTRADA,
                motivo=MotivoMovimiento.CENSO_INICIAL,
                registrado_por=registro["responsable"],
                cantidad_g=registro["peso_neto_g"],
                laboratorio_destino_id=laboratorio.id,
                observacion="Movimiento reconstruido al migrar desde la base heredada",
            )
            movimiento.registrado_en = creado_en

            sesion.commit()
            migradas += 1
            print("  ✓ migrada")

    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()

    return migradas, omitidas, bloqueadas


def main() -> int:
    argumentos = parsear_argumentos()

    # `core.database` resuelve la URL al importarse, así que el destino debe
    # quedar fijado antes de tocar cualquier módulo del proyecto.
    os.environ["DATABASE_URL"] = argumentos.destino
    os.environ.setdefault("APP_ENV", "development")

    print("=" * 70)
    print("MIGRACIÓN DESDE LA BASE HEREDADA")
    print("=" * 70)
    print(f"Origen  (solo lectura): {argumentos.origen}")
    print(f"Destino:                {argumentos.destino}")
    if not argumentos.aplicar:
        print("\nMODO SIMULACIÓN. Use --aplicar para escribir.")

    datos = leer_origen(argumentos.origen)
    print(f"\nDeclaraciones encontradas en el origen: {len(datos['declaraciones'])}")

    if datos["dependencias_sin_uso"]:
        print(
            "\n⚠️ Dependencias sin laboratorios ni declaraciones, NO se migran "
            "(son artefactos de la resolución por coincidencia parcial corregida "
            f"en la Fase 3): {datos['dependencias_sin_uso']}"
        )

    migradas, omitidas, bloqueadas = migrar(datos, argumentos.aplicar)

    print("\n" + "=" * 70)
    verbo = "migradas" if argumentos.aplicar else "listas para migrar"
    print(f"{verbo}: {migradas} · omitidas por existir: {omitidas} · bloqueadas: {bloqueadas}")
    print("La base de origen no fue modificada.")
    print("=" * 70)

    return 1 if bloqueadas else 0


if __name__ == "__main__":
    sys.exit(main())
