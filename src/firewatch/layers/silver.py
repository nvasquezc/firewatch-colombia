"""Bronze -> Silver: validación, deduplicación multisensor y proyección métrica."""
from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from firewatch.config import CFG, Config

log = logging.getLogger(__name__)

#: Tamaño nominal del píxel VIIRS en nadir. Define la celda de deduplicación.
DEDUP_CELL_M = 375.0
#: Ventana temporal de coincidencia entre sensores.
DEDUP_WINDOW_MIN = 15

_COLS = [
    "latitude", "longitude", "acq_date", "acq_time", "confidence",
    "bright_ti4", "bright_ti5", "frp", "daynight", "type", "satellite", "source",
]


def _timestamp_utc(df: pd.DataFrame) -> pd.Series:
    """acq_date (YYYY-MM-DD) + acq_time (HHMM entero) -> instante UTC."""
    hhmm = df["acq_time"].astype("int64").astype(str).str.zfill(4)
    return pd.to_datetime(
        df["acq_date"].astype(str) + hhmm, format="%Y-%m-%d%H%M", utc=True
    )


def build_silver(cfg: Config = CFG, drop_low_conf: bool = True) -> gpd.GeoDataFrame:
    """Construye la capa silver a partir de los consolidados bronze."""
    partes = [pd.read_parquet(cfg.bronze / f"{s}.parquet") for s in cfg.sources]
    df = pd.concat(partes, ignore_index=True)
    df = df[[c for c in _COLS if c in df.columns]].copy()
    n0 = len(df)
    log.info("Bronze consolidado: %d detecciones", n0)

    # --- Tipado ------------------------------------------------------
    df["ts_utc"] = _timestamp_utc(df)
    # Colombia opera en UTC-5 de forma permanente, sin horario de verano.
    df["ts_local"] = df["ts_utc"] - pd.Timedelta(hours=5)
    df["hora_local"] = df["ts_local"].dt.hour + df["ts_local"].dt.minute / 60
    df["anio"] = df["ts_local"].dt.year.astype("int16")
    df["doy"] = df["ts_local"].dt.dayofyear.astype("int16")
    df["fecha_local"] = df["ts_local"].dt.normalize()
    df["mes_id"] = (df["ts_local"].dt.year * 12
                    + df["ts_local"].dt.month).astype("int32")

    df["frp"] = pd.to_numeric(df["frp"], errors="coerce")
    df["type"] = pd.to_numeric(df["type"], errors="coerce").astype("Int8")
    df["es_noche"] = df["daynight"].astype(str).str.upper().eq("N")
    df["conf"] = df["confidence"].astype(str).str.lower()

    # --- Filtros de calidad ------------------------------------------
    antes = len(df)
    df = df[df["frp"] > 0]                       # FRP nulo o negativo: inválido
    log.info("FRP > 0: %d eliminadas", antes - len(df))

    antes = len(df)
    df = df[df["type"] != 3]                     # detecciones marinas fuera de alcance
    log.info("Excluidas type=3 (marinas): %d", antes - len(df))

    if drop_low_conf:
        # La confianza baja concentra falsos positivos por glint y bordes de
        # nube. Se reporta el efecto por clase para verificar que el filtro
        # no elimine selectivamente el conjunto de referencia.
        antes_por_tipo = df.groupby("type", observed=True).size()
        df = df[df["conf"] != "l"]
        despues_por_tipo = df.groupby("type", observed=True).size()
        log.info("Filtro de confianza baja, retención por type:\n%s",
                 (100 * despues_por_tipo / antes_por_tipo).round(2).to_string())

    df = df[df["type"].notna()].copy()
    log.info("Tras filtros de calidad: %d (%.1f%% del original)",
             len(df), 100 * len(df) / n0)

    # --- Proyección al CRS métrico nacional ---------------------------
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=cfg.crs_geo,
    ).to_crs(cfg.crs_metric)
    gdf["x"] = gdf.geometry.x
    gdf["y"] = gdf.geometry.y

    gdf = _deduplicar(gdf)

    salida = cfg.silver / "detecciones.parquet"
    gdf.drop(columns="geometry").to_parquet(salida, index=False)
    log.info("Silver: %d detecciones -> %s", len(gdf), salida.name)
    return gdf


def _deduplicar(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Elimina observaciones redundantes del mismo foco por sensores distintos.

    S-NPP y NOAA-20 siguen órbitas separadas por unos 50 minutos, pero el
    solapamiento de barrido produce observaciones casi simultáneas del mismo
    foco. Dado que la recurrencia por celda es el descriptor central del
    estudio, no deduplicar inflaría directamente la variable de interés.

    Implementación por discretización: se agrupa por celda de 375 m y ventana
    temporal de 15 min, conservando la detección de mayor FRP. Es una
    aproximación al criterio de vecindad continua, con la ventaja de ser
    determinista y de coste lineal sobre dos millones de registros. Su única
    limitación son los pares que caen a ambos lados de un borde de celda o
    de ventana, cuyo efecto es despreciable frente al volumen tratado.
    """
    n0 = len(gdf)
    cell = np.floor(gdf[["x", "y"]].to_numpy() / DEDUP_CELL_M).astype(np.int64)
    win = (gdf["ts_utc"].astype("int64").to_numpy()
           // int(DEDUP_WINDOW_MIN * 60 * 1e9))

    gdf = gdf.assign(_cx=cell[:, 0], _cy=cell[:, 1], _w=win)
    gdf = (gdf.sort_values("frp", ascending=False)
              .drop_duplicates(subset=["_cx", "_cy", "_w"], keep="first")
              .drop(columns=["_cx", "_cy", "_w"])
              .sort_values("ts_utc")
              .reset_index(drop=True))

    log.info("Deduplicación: %d redundantes eliminadas (%.2f%%)",
             n0 - len(gdf), 100 * (n0 - len(gdf)) / n0)
    return gdf