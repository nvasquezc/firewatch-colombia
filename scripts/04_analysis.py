"""Paso 4: contraste de hipótesis y calibración de descriptores.

Ejecuta cuatro bloques:

  1. Contraste de unimodalidad sobre la distribución de recurrencia.
  2. Poder discriminante univariado sin control, reportado como referencia.
  3. Poder discriminante estratificado por soporte muestral, que constituye
     el resultado válido.
  4. Verificación sobre un conjunto emparejado por número de detecciones.

El contraste entre los bloques 2 y 3 es el hallazgo metodológico central:
los descriptores basados en dispersión exhiben un poder discriminante
aparente que se desvanece al controlar por el número de observaciones
disponibles en cada celda.
"""
import numpy as np
import pandas as pd

from firewatch.analysis.bimodality import componentes_gmm, dip_test, gmm_bic
from firewatch.analysis.validation import (auc_estratificado, auc_global,
                                           emparejar_por_soporte)
from firewatch.config import CFG

pd.set_option("display.width", 140)

feats = pd.read_parquet(CFG.gold / "celdas_500m.parquet")
ana = feats[feats["analizable"]].copy()

print(f"Celdas totales     : {len(feats):,}")
print(f"Celdas analizables : {len(ana):,} ({100 * len(ana) / len(feats):.2f}%)")
print(f"Referencia positiva: {ana['ref_positiva'].sum():,} en el "
      f"subconjunto analizable")

# ----------------------------------------------------------------------
# 1. Contraste de unimodalidad
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("1. CONTRASTE DE UNIMODALIDAD (H0)")
print("=" * 72)

for var in ["n_meses", "n_det"]:
    x = np.log10(feats[var].to_numpy(dtype=float))
    print(f"\n--- log10({var}) sobre {len(feats):,} celdas ---\n")

    print("  Test de inmersión de Hartigan:")
    for k, v in dip_test(x).items():
        print(f"    {k:<18}: {v}")

    print("\n  Selección de componentes por criterio de información:")
    print(gmm_bic(x).to_string(index=False))

    print("\n  Componentes ajustadas con k = 2:")
    print(componentes_gmm(x, k=2).to_string(index=False))

# ----------------------------------------------------------------------
# 2. Poder discriminante sin control
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("2. PODER DISCRIMINANTE SIN CONTROL")
print("   Reportado como referencia. Para los descriptores de dispersión")
print("   está confundido con el número de detecciones por celda.")
print("=" * 72 + "\n")
g = auc_global(ana)
print(g.to_string(index=False))

# ----------------------------------------------------------------------
# 3. Poder discriminante estratificado
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("3. PODER DISCRIMINANTE ESTRATIFICADO POR SOPORTE MUESTRAL")
print("   Dentro de cada estrato el sesgo por tamaño de muestra es")
print("   aproximadamente constante. Este es el resultado válido.")
print("=" * 72 + "\n")

est = auc_estratificado(ana)
if len(est):
    tabla = est.pivot(index="descriptor", columns="estrato", values="auc")
    # Orden natural de los estratos, no alfabético.
    orden = [c for c in ["3-5", "6-10", "11-25", "26-60", "61-+"]
             if c in tabla.columns]
    tabla = tabla[orden]

    # Degradación: diferencia entre el AUC sin control y el del estrato
    # de mayor soporte, donde el sesgo por tamaño de muestra es menor.
    ref = g.set_index("descriptor")["auc"]
    tabla.insert(0, "sin_control", ref)
    tabla["caida"] = (tabla["sin_control"] - tabla[orden[-1]]).round(3)

    print(tabla.round(3).sort_values("caida", ascending=False).to_string())

    print("\n  Tamaños por estrato:")
    print(est[["estrato", "n_pos", "n_neg"]].drop_duplicates()
             .set_index("estrato").loc[orden].to_string())
else:
    print("  Sin estratos con soporte suficiente.")

# ----------------------------------------------------------------------
# 4. Conjunto emparejado por soporte
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("4. CONJUNTO EMPAREJADO POR NÚMERO DE DETECCIONES")
print("=" * 72 + "\n")

emp = emparejar_por_soporte(ana)
med_pos = emp[emp["ref_positiva"]]["n_det"].median()
med_neg = emp[~emp["ref_positiva"]]["n_det"].median()

print(f"n = {len(emp):,} ({emp['ref_positiva'].sum()} positivas)")
print(f"n_det mediano: positivos {med_pos:.0f}, negativos {med_neg:.0f}")

if med_pos > 1.5 * med_neg:
    print("\n  ADVERTENCIA. El emparejamiento es incompleto: no existen")
    print("  suficientes celdas negativas con soporte alto para igualar la")
    print("  distribución de los positivos. Los valores siguientes deben")
    print("  interpretarse como cota superior del poder discriminante.")

print()
print(auc_global(emp).to_string(index=False))

# ----------------------------------------------------------------------
# Síntesis
# ----------------------------------------------------------------------
print("\n" + "=" * 72)
print("SÍNTESIS")
print("=" * 72)

if len(est):
    ultimo = orden[-1]
    robustos = tabla[tabla[ultimo] >= 0.65].index.tolist()
    descartados = tabla[tabla[ultimo] < 0.60].index.tolist()
    print(f"\nDescriptores que conservan poder en el estrato {ultimo}:")
    print(f"  {', '.join(robustos) if robustos else 'ninguno'}")
    print(f"\nDescriptores sin poder discriminante bajo control:")
    print(f"  {', '.join(descartados) if descartados else 'ninguno'}")

print(f"\nInconsistencia de la máscara: de {feats['ref_positiva'].sum()} "
      f"celdas con referencia positiva,")
print(f"{(feats['ref_positiva'] & ~feats['type_pura']).sum()} contienen "
      f"simultáneamente detecciones etiquetadas")
print("como fuente térmica y como vegetación presunta.")