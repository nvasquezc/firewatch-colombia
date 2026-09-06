"""Ingesta de detecciones de incendios activos desde NASA FIRMS.

Fuente: Fire Information for Resource Management System (FIRMS), NASA EOSDIS.
Endpoint: https://firms.modaps.eosdis.nasa.gov/api/area/

Restricciones verificadas empíricamente contra la API (2026-09):
  - El parámetro day_range admite el intervalo [1..5]. Valores mayores
    devuelven HTTP 400 con el mensaje "Invalid day range. Expects [1..5]".
  - Solo los productos de procesamiento estándar (sufijo _SP) incluyen el
    campo `type`. Los productos NRT lo omiten, por lo que no permiten
    construir el conjunto de referencia que requiere este estudio.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from firewatch.config import CFG, Config, get_map_key

log = logging.getLogger(__name__)

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api"

#: Columnas mínimas que debe traer una respuesta válida del endpoint `area`.
_REQUIRED = {"latitude", "longitude", "acq_date", "acq_time", "frp"}

#: Máximo de días por petición admitido por la API.
MAX_DAY_RANGE = 5


class FirmsAPIError(RuntimeError):
    """Error de la API que no debe reintentarse.

    Cubre dos casos: respuestas HTTP 4xx, donde el cuerpo explica qué
    parámetro fue rechazado, y respuestas HTTP 200 cuyo cuerpo es texto
    plano en lugar de CSV.
    """


class FirmsClient:
    """Cliente con reintentos ante fallas de red, control de tasa y caché
    idempotente en disco."""

    def __init__(self, cfg: Config = CFG, map_key: str | None = None) -> None:
        self.cfg = cfg
        self.map_key = map_key or get_map_key()

        if self.cfg.day_chunk > MAX_DAY_RANGE:
            raise ValueError(
                f"day_chunk={self.cfg.day_chunk} excede el máximo admitido "
                f"por la API ({MAX_DAY_RANGE}). Ajuste config.py."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "FireWatch-Colombia/0.1 (investigacion academica)"}
        )
        self.cfg.ensure_dirs()

    # -- Diagnóstico ---------------------------------------------------

    def availability(self) -> pd.DataFrame:
        """Rango temporal disponible por producto. Fechas en GMT."""
        url = f"{BASE_URL}/data_availability/csv/{self.map_key}/all"
        r = self.session.get(url, timeout=self.cfg.timeout_s)
        r.raise_for_status()
        return pd.read_csv(StringIO(r.text))

    # -- Descarga ------------------------------------------------------

    @retry(
        # Solo se reintentan fallas de red y del servidor. Un error de
        # parámetros no mejora al repetirse: debe propagarse de inmediato.
        retry=retry_if_exception_type(requests.RequestException),
        wait=wait_exponential(multiplier=2, min=4, max=90),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _fetch_chunk(self, source: str, start: date, days: int) -> pd.DataFrame:
        """Una petición al endpoint `area`. Puede devolver un DataFrame vacío."""
        url = (f"{BASE_URL}/area/csv/{self.map_key}/{source}/"
               f"{self.cfg.bbox}/{days}/{start.isoformat()}")
        r = self.session.get(url, timeout=self.cfg.timeout_s)

        # El cuerpo de la respuesta contiene el motivo del rechazo.
        # Debe leerse antes de lanzar la excepción.
        if r.status_code >= 400:
            raise FirmsAPIError(
                f"HTTP {r.status_code} | source={source} "
                f"start={start.isoformat()} days={days}\n"
                f"Respuesta del servidor: {r.text[:500]}"
            )

        text = r.text.strip()
        if not text:
            return pd.DataFrame()

        primera = text.split("\n", 1)[0]
        if "," not in primera or "latitude" not in primera:
            raise FirmsAPIError(f"Respuesta no tabular: {text[:300]!r}")

        df = pd.read_csv(StringIO(text))
        if df.empty:
            return df

        faltantes = _REQUIRED - set(df.columns)
        if faltantes:
            raise FirmsAPIError(
                f"Columnas ausentes en {source}: {sorted(faltantes)}. "
                f"Recibidas: {sorted(df.columns)}"
            )
        return df

    # -- Orquestación --------------------------------------------------

    @staticmethod
    def _chunks(start: date, end: date, size: int):
        """Divide [start, end] en bloques de a lo sumo `size` días."""
        cur = start
        while cur <= end:
            fin = min(cur + timedelta(days=size - 1), end)
            yield cur, (fin - cur).days + 1
            cur = fin + timedelta(days=1)

    def download(self, source: str, force: bool = False) -> Path:
        """Descarga un sensor completo a la capa bronze.

        Idempotente: los bloques ya presentes en disco no se vuelven a
        solicitar. Si el proceso se interrumpe, basta con relanzarlo.
        """
        d = self.cfg.bronze / source
        d.mkdir(parents=True, exist_ok=True)

        bloques = list(self._chunks(self.cfg.date_start, self.cfg.date_end,
                                    self.cfg.day_chunk))
        pendientes = sum(
            1 for ini, _ in bloques
            if force or not (d / f"{source}_{ini.isoformat()}.parquet").exists()
        )
        log.info("%s: %d bloques totales, %d pendientes",
                 source, len(bloques), pendientes)

        hechos = 0
        for i, (ini, days) in enumerate(bloques, 1):
            destino = d / f"{source}_{ini.isoformat()}.parquet"
            if destino.exists() and not force:
                continue

            df = self._fetch_chunk(source, ini, days)
            n = len(df)
            if df.empty:
                # Se escribe un marcador vacío para no repetir la petición.
                df = pd.DataFrame(columns=sorted(_REQUIRED))
            df.to_parquet(destino, index=False)

            hechos += 1
            log.info("[%3d/%3d] %-16s %s  %6d filas",
                     i, len(bloques), source, ini.isoformat(), n)
            time.sleep(self.cfg.request_pause_s)

        log.info("%s: %d bloques descargados en esta ejecución", source, hechos)
        return self.consolidate(source)

    def consolidate(self, source: str) -> Path:
        """Une los bloques de un sensor en un único Parquet de capa bronze."""
        partes = sorted((self.cfg.bronze / source).glob(f"{source}_*.parquet"))
        if not partes:
            raise FileNotFoundError(f"Sin bloques descargados para {source}.")

        dfs = [pd.read_parquet(p) for p in partes]
        dfs = [x for x in dfs if not x.empty]
        if not dfs:
            raise ValueError(f"Todos los bloques de {source} están vacíos.")

        df = pd.concat(dfs, ignore_index=True)
        df["source"] = source

        salida = self.cfg.bronze / f"{source}.parquet"
        df.to_parquet(salida, index=False)
        log.info("%s consolidado: %d registros -> %s", source, len(df), salida.name)
        return salida

    def download_all(self, force: bool = False) -> dict[str, Path]:
        return {s: self.download(s, force=force) for s in self.cfg.sources}