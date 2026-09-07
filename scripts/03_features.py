"""Paso 3: descriptores de persistencia por celda.

Opera sobre la capa silver persistida, sin recalcular la ingesta ni la
deduplicación. Reporta tres bloques de resultados:

  1. Separación por recurrencia entre celdas con y sin detecciones
     etiquetadas por FIRMS como fuente térmica no vegetal.
  2. Coexistencia de etiquetas dentro de una misma celda, indicador de
     inconsistencia de la máscara global a nivel de píxel.
  3. Descriptores de dispersión sobre el subconjunto de celdas con
     soporte estadístico suficiente.
"""
import logging

import pandas as pd

from firewatch.config import CFG
from firewatch.features.persistence import build_grid_features

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")

gdf = pd.read_parquet(CFG.silver / "detecciones.parquet")
print(f"Capa silver cargada: {len(gdf):,} detecciones\n")

feats = build_grid_features(gdf)

# ----------------------------------------------------------------------
# 1. Recurrencia sobre el total de celdas
# ----------------------------------------------------------------------
print("\n" + "=" * 68)
print("RECURRENCIA POR CLASE DE REFERENCIA (todas las celdas)")
print("=" * 68)
print("\nMeses con actividad (n_meses):")
print(feats.groupby("ref_positiva")["n_meses"]
           .describe(percentiles=[0.5, 0.9, 0.99]).round(2).to_string())

print("\nAños con actividad (n_anios):")
print(feats.groupby("ref_positiva")["n_anios"]
           .describe(percentiles=[0.5, 0.9, 0.99]).round(2).to_string())

print("\nDetecciones por celda (n_det):")
print(feats.groupby("ref_positiva")["n_det"]
           .describe(percentiles=[0.5, 0.9, 0.99]).round(2).to_string())

# ----------------------------------------------------------------------
# 2. Coexistencia de etiquetas en una misma celda
# ----------------------------------------------------------------------
print("\n" + "=" * 68)
print("COEXISTENCIA DE ETIQUETAS EN UNA MISMA CELDA")
print("=" * 68)
mixtas = feats[~feats["type_pura"]]
print(f"\nCeldas mixtas: {len(mixtas):,} de {len(feats):,} "
      f"({100 * len(mixtas) / len(feats):.4f}%)")
print(f"De ellas, con al menos una detección térmica: "
      f"{mixtas['ref_positiva'].sum():,}")

pos = feats[feats["ref_positiva"]]
if len(pos):
    print(f"\nCeldas con referencia positiva: {len(pos):,}")
    print(f"  puras   : {pos['type_pura'].sum():,} "
          f"({100 * pos['type_pura'].mean():.1f}%)")
    print(f"  mixtas  : {(~pos['type_pura']).sum():,} "
          f"({100 * (~pos['type_pura']).mean():.1f}%)")
    print("\nFracción de detecciones térmicas dentro de celdas positivas:")
    print(pos["frac_termica"].describe(
        percentiles=[0.25, 0.5, 0.75]).round(3).to_string())

# ----------------------------------------------------------------------
# 3. Descriptores de dispersión sobre celdas analizables
# ----------------------------------------------------------------------
print("\n" + "=" * 68)
print("DESCRIPTORES SOBRE CELDAS ANALIZABLES")
print("=" * 68)
ana = feats[feats["analizable"]]
print(f"\nn = {len(ana):,} celdas analizables "
      f"({100 * len(ana) / len(feats):.2f}% del total)")
print(f"    de ellas positivas: {ana['ref_positiva'].sum():,}")

cols = ["n_meses", "n_anios", "tasa_recurrencia", "cobertura_mensual",
        "R_estacional", "frp_estabilidad", "frac_noche", "hora_sd"]

print("\nMedianas por clase:")
print(ana.groupby("ref_positiva")[cols].median().round(3).to_string())

print("\nCuartiles del conjunto positivo:")
print(ana[ana["ref_positiva"]][cols]
      .describe(percentiles=[0.25, 0.5, 0.75]).round(3).to_string())

print("\nCuartiles del conjunto negativo:")
print(ana[~ana["ref_positiva"]][cols]
      .describe(percentiles=[0.25, 0.5, 0.75]).round(3).to_string())