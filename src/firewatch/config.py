"""Configuración central del proyecto FireWatch Colombia."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

#: Clasificación de tipo en productos de procesamiento estándar (SP).
FIRE_TYPE = {
    0: "vegetacion_presunta",
    1: "volcan_activo",
    2: "fuente_estatica_terrestre",
    3: "deteccion_marina",
}


@dataclass(frozen=True)
class Config:
    """Parámetros del estudio. Inmutable: todo cambio queda en el historial."""

    #: Bounding box en grados: oeste,sur,este,norte. Colombia continental.
    bbox: str = "-79.1,-4.3,-66.8,13.5"

    crs_geo: str = "EPSG:4326"
    #: MAGNA-SIRGAS / Origen Nacional. CRS proyectado oficial del IGAC.
    crs_metric: str = "EPSG:9377"

    #: Tres años completos. Suficiente para estimar recurrencia interanual
    #: y compatible con el rezago de los productos SP.
    date_start: date = date(2022, 1, 1)
    date_end: date = date(2025, 12, 31)

    #: Productos SP: validados e incluyen el campo `type`, a diferencia de NRT.
    sources: tuple[str, ...] = ("VIIRS_SNPP_SP", "VIIRS_NOAA20_SP")

    day_chunk: int = 5
    request_pause_s: float = 0.5
    timeout_s: int = 120

    data_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("FIREWATCH_DATA", "./data")
        ).expanduser().resolve()
    )

    @property
    def bronze(self) -> Path:
        return self.data_root / "bronze"

    @property
    def silver(self) -> Path:
        return self.data_root / "silver"

    @property
    def gold(self) -> Path:
        return self.data_root / "gold"

    def ensure_dirs(self) -> None:
        for d in (self.bronze, self.silver, self.gold):
            d.mkdir(parents=True, exist_ok=True)


def get_map_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key or key.startswith("pegue"):
        raise RuntimeError(
            "FIRMS_MAP_KEY no configurada. Edite el archivo .env en la raíz. "
            "Solicítela en https://firms.modaps.eosdis.nasa.gov/api/map_key/"
        )
    return key


CFG = Config()