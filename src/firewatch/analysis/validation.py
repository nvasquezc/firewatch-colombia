"""Calibración de descriptores contra la referencia de FIRMS.

Los descriptores basados en dispersión están sesgados por el número de
detecciones disponibles en la celda. Dado que el conjunto positivo tiene
un soporte muestral sistemáticamente mayor que el negativo, una comparación
directa confunde el efecto del fenómeno con el del tamaño muestral. Este
módulo implementa el control por estratificación.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

DESCRIPTORES = [
    "n_meses", "n_anios", "tasa_recurrencia", "cobertura_mensual",
    "R_estacional", "frp_estabilidad", "frac_noche", "hora_sd",
]

#: Estratos de soporte muestral. Dentro de cada uno, el sesgo por n es
#: aproximadamente constante y la comparación resulta interpretable.
ESTRATOS = [(3, 5), (6, 10), (11, 25), (26, 60), (61, 10_000)]


def auc_global(df: pd.DataFrame, descriptores=DESCRIPTORES) -> pd.DataFrame:
    """AUC univariado sin control por soporte muestral.

    Se reporta como referencia, no como resultado: para los descriptores
    de dispersión está confundido con el número de detecciones.
    """
    filas = []
    for c in descriptores:
        m = df[c].notna()
        if m.sum() < 50 or df.loc[m, "ref_positiva"].nunique() < 2:
            continue
        auc = roc_auc_score(df.loc[m, "ref_positiva"], df.loc[m, c])
        filas.append({"descriptor": c, "auc": round(max(auc, 1 - auc), 4),
                      "direccion": "+" if auc >= 0.5 else "-",
                      "n": int(m.sum())})
    return pd.DataFrame(filas).sort_values("auc", ascending=False)


def auc_estratificado(df: pd.DataFrame,
                      descriptores=DESCRIPTORES) -> pd.DataFrame:
    """AUC dentro de estratos homogéneos de número de detecciones.

    Un descriptor cuyo poder discriminante se desvanece al estratificar
    estaba midiendo soporte muestral, no el fenómeno de interés.
    """
    filas = []
    for lo, hi in ESTRATOS:
        sub = df[(df["n_det"] >= lo) & (df["n_det"] <= hi)]
        n_pos = int(sub["ref_positiva"].sum())
        if n_pos < 15 or len(sub) - n_pos < 15:
            continue
        for c in descriptores:
            m = sub[c].notna()
            if m.sum() < 50 or sub.loc[m, "ref_positiva"].nunique() < 2:
                continue
            auc = roc_auc_score(sub.loc[m, "ref_positiva"], sub.loc[m, c])
            filas.append({
                "estrato": f"{lo}-{hi if hi < 10_000 else '+'}",
                "descriptor": c,
                "auc": round(max(auc, 1 - auc), 4),
                "direccion": "+" if auc >= 0.5 else "-",
                "n_pos": n_pos, "n_neg": len(sub) - n_pos,
            })
    return pd.DataFrame(filas)


def emparejar_por_soporte(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Submuestra negativos con la misma distribución de n_det que los positivos.

    Produce un conjunto balanceado en soporte muestral, sobre el cual toda
    diferencia observada es atribuible al fenómeno y no al número de
    observaciones disponibles.
    """
    rng = np.random.default_rng(seed)
    pos = df[df["ref_positiva"]]
    neg = df[~df["ref_positiva"]]

    elegidos = []
    for n_det, grupo_pos in pos.groupby("n_det"):
        cand = neg[neg["n_det"] == n_det]
        if len(cand) == 0:
            continue
        k = min(len(grupo_pos), len(cand))
        elegidos.append(cand.iloc[
            rng.choice(len(cand), size=k, replace=False)
        ])

    if not elegidos:
        raise ValueError("No hay negativos con soporte comparable.")
    return pd.concat([pos] + elegidos, ignore_index=True)