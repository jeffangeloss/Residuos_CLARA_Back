"""
Script de pruebas unitarias para el motor de clasificación determinista
y verificador de acopio de CLARA+ (ULima)
"""

import sys
from core.models import EntradaResiduoRequest
from core.classifier import clasificar_residuo, MATRIZ_CSBQR

def test_clasificador():
    print("=" * 70)
    print("🧪 INICIANDO PRUEBAS DEL MOTOR DE CLASIFICACIÓN CLARA+ (ULima)")
    print("=" * 70)

    # Caso 1: Metales Pesados (Sulfato de cobre + Hierro)
    req1 = EntradaResiduoRequest(
        dependencia="Ingeniería Industrial",
        laboratorio="Química General",
        actividad="Recuperación redox de cobre metálico",
        responsable="Lic. Álvarez",
        fecha="2026-08-12",
        descripcion="Solución residual de sulfato de hierro con trazas de cobre",
        insumos=["sulfato de cobre(II) 1.0 mol/L", "hierro en polvo"],
        peso_bruto_g=2600.0,
        tara_g=200.0,
        ph=3.5
    )
    res1 = clasificar_residuo(req1)
    print("\n▶ [CASO 1] Residuo con Metales Pesados:")
    print(f"  • ID Residuo:         {res1.id_residuo}")
    print(f"  • Nombre Normalizado: {res1.nombre_normalizado}")
    print(f"  • Categoría:          {res1.categoria_nombre} ({res1.categoria_id})")
    print(f"  • Clase SUNAT:        {res1.clase_declaracion_sunat}")
    print(f"  • Clase Basilea:      {res1.clase_basilea}")
    print(f"  • Peso Neto:          {res1.peso_neto_g} g")
    print(f"  • Cantidad declarada: {res1.cantidad} {res1.unidad.value} ({res1.modo_medicion.value})")
    print(f"  • Confianza:          {res1.confianza}")
    print(f"  • Pictogramas GHS:    {res1.pictogramas_ghs}")
    print(f"  • No mezclar con:     {', '.join(res1.no_mezclar_con)}")
    assert res1.categoria_id == "metales-pesados", "Falló la clasificación del caso 1"
    assert res1.cantidad == 2.4, "Falló el cálculo de la cantidad declarada"
    assert res1.unidad.value == "Kg"

    # Caso 2: Ácidos Corrosivos (Ácido Sulfúrico)
    req2 = EntradaResiduoRequest(
        dependencia="Ingeniería Industrial",
        laboratorio="Química Analítica",
        actividad="Titulación ácido-base",
        responsable="Dra. Mendoza",
        fecha="2026-08-12",
        descripcion="Solución de ácido sulfúrico concentrado",
        insumos=["ácido sulfúrico 98%"],
        peso_bruto_g=1500.0,
        tara_g=150.0,
        ph=1.0
    )
    res2 = clasificar_residuo(req2)
    print("\n▶ [CASO 2] Ácido Corrosivo:")
    print(f"  • Categoría:       {res2.categoria_nombre}")
    print(f"  • Clase SUNAT:     {res2.clase_declaracion_sunat}")
    print(f"  • Pictogramas:     {res2.pictogramas_ghs}")
    assert res2.categoria_id == "acidos-corrosivos"
    assert "corrosion" in res2.pictogramas_ghs

    # Caso 3: Residuo No Identificado (Contingencia / Escalamiento CSBQR)
    req3 = EntradaResiduoRequest(
        dependencia="Ingeniería Industrial",
        laboratorio="Operaciones Unitarias",
        actividad="Muestra sin rotular encontrada en reactores",
        responsable="Ing. Ramírez",
        fecha="2026-08-12",
        descripcion="Líquido amarillento sin etiqueta",
        insumos=[],
        peso_bruto_g=1200.0,
        tara_g=100.0,
        desconocido=True
    )
    res3 = clasificar_residuo(req3)
    print("\n▶ [CASO 3] Residuo No Identificado (Escalamiento):")
    print(f"  • Categoría:       {res3.categoria_nombre}")
    print(f"  • Confianza:       {res3.confianza}")
    print(f"  • Escalar CSBQR:   {res3.escalar_csbqr}")
    print(f"  • Clase Basilea:   {res3.clase_basilea}")
    assert res3.categoria_id == "no-identificados"
    assert res3.confianza == "Bajo"
    assert res3.escalar_csbqr is True

    # Caso 4: Matriz de Incompatibilidad CSBQR (11x11 completa)
    nunca = sorted(p for p, (v, _) in MATRIZ_CSBQR.items() if v == "NUNCA")
    segregar = [p for p, (v, _) in MATRIZ_CSBQR.items() if v == "SEGREGAR"]
    print(f"\n▶ [CASO 4] Matriz de Incompatibilidad CSBQR: "
          f"{len(nunca)} pares NUNCA, {len(segregar)} SEGREGAR")
    for p1, p2 in nunca:
        print(f"  • 🚫 NUNCA JUNTOS: [{p1}] + [{p2}] ➔ {MATRIZ_CSBQR[(p1, p2)][1]}")
    # 27 pares entre grupos distintos más la diagonal AISLAR+AISLAR: dos
    # residuos sin identificar tampoco pueden juntarse entre sí.
    entre_distintos = [p for p in nunca if p[0] != p[1]]
    assert len(entre_distintos) == 27, f"Se esperaban 27 pares NUNCA, hay {len(entre_distintos)}"
    assert ("AISLAR", "AISLAR") in nunca
    assert len(MATRIZ_CSBQR) == 66, "La matriz 11x11 tiene 66 pares únicos con su diagonal"

    print("\n" + "=" * 70)
    print("✅ ¡TODAS LAS PRUEBAS DEL MOTOR PASARON SATISFACTORIAMENTE!")
    print("=" * 70)

if __name__ == "__main__":
    test_clasificador()
