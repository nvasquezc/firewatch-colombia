"""Paso 1: descarga de detecciones VIIRS a la capa bronze."""
import logging

from firewatch.ingest.firms import FirmsClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")

cli = FirmsClient()

print("\n=== Disponibilidad de los sensores ===")
da = cli.availability()
print(da[da["data_id"].isin(cli.cfg.sources)].to_string(index=False))

print(f"\nVentana solicitada: {cli.cfg.date_start} a {cli.cfg.date_end}")
print(f"Bloques de {cli.cfg.day_chunk} días | bbox {cli.cfg.bbox}\n")

print("=== Descarga ===")
rutas = cli.download_all()

print("\n=== Resultado ===")
for s, p in rutas.items():
    print(f"  {s}: {p}")