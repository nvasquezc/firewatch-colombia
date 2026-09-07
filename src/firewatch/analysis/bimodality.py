"""Contraste formal de H0: unimodalidad de la distribución de recurrencia.

H0. La distribución de los descriptores de persistencia sobre las celdas
    es unimodal y no admite separación en subpoblaciones.

H1. Dicha distribución presenta al menos dos modos, el de alta recurrencia
    correspondiente a fuentes térmicas antrópicas persistentes.

Se emplean dos procedimientos complementarios. El test de inmersión de
Hartigan y Hartigan contrasta la unimodalidad sin suponer forma paramétrica.
La selección del número de componentes de una mezcla gaussiana por criterio
de información aporta evidencia sobre la existencia de subpoblaciones
diferenciadas, no solo sobre la ausencia de unimodalidad.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

#: Límite de validez de los valores críticos tabulados en la implementación
#: de referencia del test de inmersión.
DIP_N_MAX_TABULADO = 72_000


def dip_test(x: np.ndarray, n_max: int = 50_000, n_rep: int = 200,
             seed: int = 42) -> dict:
    """Test de inmersión de Hartigan y Hartigan (1985).

    H0: la distribución es unimodal. Un valor p inferior a 0.05 permite
    rechazarla en favor de al menos dos modos.

    Los valores críticos tabulados solo son válidos hasta unas 72.000
    observaciones. Por encima de ese tamaño el estadístico se estima sobre
    submuestras aleatorias repetidas y se reporta la distribución de los
    valores p resultantes, en lugar de un único valor situado fuera del
    rango de validez de las tablas. Reportar p = 0 exacto sobre 856.625
    observaciones sería un resultado no interpretable.
    """
    import diptest

    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]

    if len(x) < 4:
        return {"n": int(len(x)), "modo": "muestra insuficiente",
                "rechaza_H0": False}

    if len(x) <= n_max:
        d, p = diptest.diptest(x)
        return {
            "n": int(len(x)),
            "modo": "directo",
            "dip": round(float(d), 6),
            "p_valor": float(p),
            "rechaza_H0": bool(p < 0.05),
        }

    dips, ps = [], []
    for _ in range(n_rep):
        sub = x[rng.choice(len(x), size=n_max, replace=False)]
        d, p = diptest.diptest(sub)
        dips.append(d)
        ps.append(p)

    dips = np.asarray(dips)
    ps = np.asarray(ps)

    return {
        "n": int(len(x)),
        "modo": f"submuestreo ({n_rep} x {n_max:,})",
        "dip_mediano": round(float(np.median(dips)), 6),
        "dip_ic95": (round(float(np.percentile(dips, 2.5)), 6),
                     round(float(np.percentile(dips, 97.5)), 6)),
        "p_mediano": float(np.median(ps)),
        "frac_p_menor_05": round(float((ps < 0.05).mean()), 4),
        #: Se considera rechazo cuando H0 se rechaza en más del 95% de las
        #: submuestras, criterio más exigente que un contraste puntual.
        "rechaza_H0": bool((ps < 0.05).mean() > 0.95),
    }


def gmm_bic(x: np.ndarray, k_max: int = 4, seed: int = 42,
            n_max: int = 100_000) -> pd.DataFrame:
    """Selección del número de componentes por criterio de información.

    Complementa el test de inmersión: si el criterio prefiere k >= 2, hay
    evidencia de subpoblaciones y no solo de no unimodalidad.

    Advertencia de interpretación. Con cientos de miles de observaciones el
    BIC penaliza la complejidad de forma insuficiente y tiende a favorecer
    el mayor número de componentes admitido. El resultado debe leerse como
    evidencia de estructura multimodal, no como estimación del número real
    de subpoblaciones. Se submuestrea para acotar el efecto y el coste.
    """
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]

    if len(x) > n_max:
        x = x[rng.choice(len(x), size=n_max, replace=False)]

    X = x.reshape(-1, 1)
    filas = []
    for k in range(1, k_max + 1):
        gm = GaussianMixture(k, covariance_type="full",
                             random_state=seed, n_init=5).fit(X)
        filas.append({
            "k": k,
            "bic": round(float(gm.bic(X)), 1),
            "aic": round(float(gm.aic(X)), 1),
            "log_lik": round(float(gm.score(X) * len(X)), 1),
        })

    out = pd.DataFrame(filas)
    out["delta_bic"] = (out["bic"] - out["bic"].min()).round(1)
    out["n_usado"] = len(x)
    return out


def componentes_gmm(x: np.ndarray, k: int = 2, seed: int = 42,
                    n_max: int = 100_000) -> pd.DataFrame:
    """Parámetros de las componentes ajustadas, en la escala de entrada.

    Permite reportar dónde se sitúa cada modo y qué peso tiene, que es la
    información sustantiva para interpretar la separación de poblaciones.
    """
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]

    if len(x) > n_max:
        x = x[rng.choice(len(x), size=n_max, replace=False)]

    gm = GaussianMixture(k, covariance_type="full",
                         random_state=seed, n_init=5).fit(x.reshape(-1, 1))

    orden = np.argsort(gm.means_.ravel())
    return pd.DataFrame({
        "componente": np.arange(1, k + 1),
        "media": gm.means_.ravel()[orden].round(4),
        "sd": np.sqrt(gm.covariances_.ravel())[orden].round(4),
        "peso": gm.weights_[orden].round(4),
    })