"""Paso 2: bronze -> silver.

Validación de calidad, proyección al CRS métrico nacional y deduplicación
multisensor. La construcción de descriptores por celda se realiza en el
paso 3, sobre la capa silver ya persistida.
"""
import logging

from firewatch.layers.silver import build_silver

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")

gdf = build_silver()
print(f"\nCapa silver construida: {len(gdf):,} detecciones")