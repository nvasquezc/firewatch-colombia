"""Aisla que parametro rechaza la API de FIRMS."""
import requests

from firewatch.config import CFG, get_map_key

KEY = get_map_key()
BASE = "https://firms.modaps.eosdis.nasa.gov/api"


def probar(etiqueta, source, bbox, days, fecha):
    url = f"{BASE}/area/csv/{KEY}/{source}/{bbox}/{days}"
    if fecha:
        url += f"/{fecha}"
    r = requests.get(url, timeout=60)
    cuerpo = r.text.strip()[:220].replace("\n", " | ")
    print(f"\n{etiqueta}")
    print(f"  days={days} bbox={bbox} fecha={fecha or '(omitida)'}")
    print(f"  HTTP {r.status_code}  ->  {cuerpo}")
    return r.status_code == 200


S = "VIIRS_SNPP_SP"
COL = CFG.bbox
CHICO = "-74.5,4.0,-73.5,5.0"

probar("A. Referencia: 1 dia, area chica", S, CHICO, 1, "2022-01-01")
probar("B. 1 dia, Colombia completa",      S, COL,   1, "2022-01-01")
probar("C. 5 dias, Colombia completa",     S, COL,   5, "2022-01-01")
probar("D. 10 dias, Colombia completa",    S, COL,   10, "2022-01-01")
probar("E. Sin fecha (ultimos N dias)",    S, COL,   1, "")
probar("F. Producto NRT en vez de SP",     "VIIRS_SNPP_NRT", COL, 1, "")
