"""Descriptores de persistencia espaciotemporal por celda de rejilla.

Fundamento. Una fuente térmica antrópica fija y un incendio de vegetación
difieren en cuatro dimensiones observables sin datos auxiliares:

  1. Recurrencia    - la fuente fija reaparece en la misma celda durante años.
  2. Estabilidad    - su FRP tiene baja dispersión relativa; el fuego es errático.
  3. Estacionalidad - el fuego se concentra en temporada seca; la fuente no.
  4. Régimen horario- la fuente opera de continuo; el fuego tiene sesgo diurno.

Advertencias sobre definición y sesgo.

Los descriptores de dispersión no están definidos en celdas con una única
detección o con intervalo observado corto. En esos casos degeneran a un valor
constante por construcción, no por propiedad del fenómeno, y se asignan como
faltantes de forma explícita.

Con mayor gravedad, la concentración circular presenta sesgo positivo en
muestras pequeñas: bajo distribución uniforme su valor esperado decrece
aproximadamente como el inverso de la raíz del número de observaciones. Dado
que el conjunto positivo tiene soporte muestral sistemáticamente mayor, toda
comparación directa de este descriptor entre clases confunde el efecto del
fenómeno con el del tamaño de muestra. La calibración debe realizarse
estratificando por `n_det`; véase `firewatch.analysis.validation`.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from firewatch.config import CFG, Config

log = logging.getLogger(__name__)

#: Lado de celda. Excede la resolución nominal (375 m) para absorber el error
#: de geolocalización y evitar que un foco fijo se reparta entre celdas
#: contiguas, lo que subestimaría la recurrencia medida.
CELL_M = 500.0

#: Mínimo de detecciones para que un descriptor de dispersión sea informativo.
MIN_DET_DISPERSION = 3

#: Mínimo de meses calendario abarcados para que la cobertura sea informativa.
MIN_MESES_TRANSCURRIDOS = 3

#: Descriptores definidos en toda celda.
DESCRIPTORES_BASE = ["n_det", "n_dias", "n_meses", "n_anios",
                     "tasa_recurrencia", "frac_noche"]

#: Descriptores que requieren celda analizable.
DESCRIPTORES_DISPERSION = ["cobertura_mensual", "R_estacional",
                           "frp_estabilidad", "hora_sd"]

DESCRIPTORES = DESCRIPTORES_BASE + DESCRIPTORES_DISPERSION


def build_grid_features(
    gdf: pd.DataFrame, cfg: Config = CFG, cell_m: float = CELL_M
) -> pd.DataFrame:
    """Agrega detecciones a rejilla regular y calcula descriptores por celda."""
    g = pd.DataFrame(gdf).copy()
    g["col"] = np.floor(g["x"] / cell_m).astype(np.int64)
    g["row"] = np.floor(g["y"] / cell_m).astype(np.int64)
    g["frp_log"] = np.log10(g["frp"])

    # `type` como entero nativo: las agregaciones sobre Int8 anulable son
    # órdenes de magnitud más lentas.
    g["type_i"] = g["type"].astype("int64")

    # Indicador de detección etiquetada por FIRMS como fuente térmica no
    # vegetal (volcán activo o fuente estática terrestre).
    g["_es_termica"] = g["type_i"].isin([1, 2]).astype("int8")

    # Componentes cartesianas del día del año, para concentración circular.
    ang = 2 * np.pi * g["doy"].to_numpy() / 365.25
    g["_cos"] = np.cos(ang)
    g["_sin"] = np.sin(ang)

    grp = g.groupby(["col", "row"], sort=False)

    # Todas las agregaciones son operaciones nativas de pandas. Se evitan
    # las funciones lambda (en particular `mode`), que fuerzan evaluación
    # en Python grupo por grupo sobre cientos de miles de celdas.
    feats = grp.agg(
        n_det=("frp", "size"),
        n_dias=("fecha_local", "nunique"),
        n_meses=("mes_id", "nunique"),
        n_anios=("anio", "nunique"),
        mes_min=("mes_id", "min"),
        mes_max=("mes_id", "max"),
        primera=("ts_local", "min"),
        ultima=("ts_local", "max"),
        frp_mediana=("frp", "median"),
        frp_max=("frp", "max"),
        frp_log_sd=("frp_log", "std"),
        frac_noche=("es_noche", "mean"),
        hora_sd=("hora_local", "std"),
        cos_m=("_cos", "mean"),
        sin_m=("_sin", "mean"),
        n_termica=("_es_termica", "sum"),
        type_min=("type_i", "min"),
        type_max=("type_i", "max"),
        type_sum=("type_i", "sum"),
    ).reset_index()

    # ------------------------------------------------------------------
    # Clase de la celda
    # ------------------------------------------------------------------
    # Una celda es pura cuando mínimo y máximo de `type` coinciden. En ese
    # caso la clase es exacta. En celdas mixtas se asigna la clase dominante
    # aproximada por el promedio redondeado.
    feats["type_pura"] = feats["type_min"] == feats["type_max"]
    feats["type_moda"] = np.where(
        feats["type_pura"],
        feats["type_min"],
        np.round(feats["type_sum"] / feats["n_det"]),
    ).astype("int8")
    feats = feats.drop(columns=["type_min", "type_max", "type_sum"])

    #: Positivo por presencia: la celda contiene al menos una detección
    #: etiquetada como volcán o fuente estática. Esta definición aprovecha
    #: las celdas mixtas, que constituyen la mayoría de las asociadas a
    #: fuentes térmicas y que la restricción a celdas puras descartaría.
    feats["ref_positiva"] = feats["n_termica"] > 0

    #: Proporción de detecciones de la celda etiquetadas como térmicas.
    #: Valores intermedios evidencian inconsistencia de la máscara global
    #: dentro de una misma celda.
    feats["frac_termica"] = feats["n_termica"] / feats["n_det"]

    # ------------------------------------------------------------------
    # Descriptores de recurrencia, definidos en toda celda
    # ------------------------------------------------------------------
    feats["span_dias"] = (feats["ultima"] - feats["primera"]).dt.days + 1

    #: Meses calendario abarcados entre la primera y la última detección.
    #: Se calcula sobre identificadores de mes y no dividiendo días, para
    #: que el cociente con `n_meses` quede acotado en la unidad por
    #: construcción y no exceda 1 por efecto de bordes de mes.
    feats["meses_transcurridos"] = feats["mes_max"] - feats["mes_min"] + 1
    feats = feats.drop(columns=["mes_min", "mes_max"])

    #: Días con actividad sobre días del intervalo observado.
    feats["tasa_recurrencia"] = feats["n_dias"] / feats["span_dias"].clip(lower=1)

    # ------------------------------------------------------------------
    # Descriptores de dispersión, definidos condicionalmente
    # ------------------------------------------------------------------
    disp_ok = feats["n_det"] >= MIN_DET_DISPERSION
    span_ok = feats["meses_transcurridos"] >= MIN_MESES_TRANSCURRIDOS

    #: Meses con actividad sobre meses abarcados. En celdas de evento único
    #: degenera a la unidad por construcción, de ahí la restricción.
    feats["cobertura_mensual"] = np.where(
        span_ok, feats["n_meses"] / feats["meses_transcurridos"], np.nan
    )

    #: Longitud del vector resultante medio sobre el ciclo anual.
    #: R -> 1: actividad concentrada en una época (estacional).
    #: R -> 0: distribuida de forma uniforme a lo largo del año.
    #: El régimen bimodal de precipitación en Colombia concentra los incendios
    #: de vegetación en dos temporadas secas; una fuente industrial no exhibe
    #: esa estructura, lo que da al descriptor motivación física.
    #: Advertencia: presenta sesgo positivo en muestras pequeñas. No debe
    #: compararse entre clases sin estratificar por `n_det`.
    feats["R_estacional"] = np.where(
        disp_ok, np.hypot(feats["cos_m"], feats["sin_m"]), np.nan
    )
    feats = feats.drop(columns=["cos_m", "sin_m"])

    #: Inversa de la dispersión del FRP en escala logarítmica. Alta = estable.
    feats["frp_estabilidad"] = np.where(
        disp_ok, 1 / (1 + feats["frp_log_sd"]), np.nan
    )

    feats["hora_sd"] = np.where(disp_ok, feats["hora_sd"], np.nan)

    #: Celda con soporte suficiente para todos los descriptores.
    feats["analizable"] = disp_ok & span_ok

    # ------------------------------------------------------------------
    # Geometría del centroide
    # ------------------------------------------------------------------
    feats["cx"] = (feats["col"] + 0.5) * cell_m
    feats["cy"] = (feats["row"] + 0.5) * cell_m

    salida = cfg.gold / f"celdas_{int(cell_m)}m.parquet"
    feats.to_parquet(salida, index=False)

    log.info("Celdas: %d -> %s", len(feats), salida.name)
    log.info("Celdas puras: %d (%.2f%%)",
             feats["type_pura"].sum(), 100 * feats["type_pura"].mean())
    log.info("Celdas analizables: %d (%.2f%%)",
             feats["analizable"].sum(), 100 * feats["analizable"].mean())
    log.info("Referencia positiva (presencia): %d celdas",
             feats["ref_positiva"].sum())
    log.info("Cobertura mensual, máximo observado: %.3f",
             np.nanmax(feats["cobertura_mensual"]))
    log.info("Distribución de type_moda:\n%s",
             feats["type_moda"].value_counts().to_string())
    return feats