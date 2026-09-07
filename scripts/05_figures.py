"""Paso 5: figuras del estudio.

Convención de composición: paneles etiquetados, incertidumbre representada
explícitamente, unidades declaradas y anotación de los estadísticos
relevantes sobre la geometría de datos.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats
from shapely.geometry import Point
from sklearn.metrics import roc_auc_score, roc_curve

from firewatch.analysis.validation import (DESCRIPTORES, auc_estratificado,
                                           auc_global)
from firewatch.config import CFG
from firewatch.viz.style import (PALETA, SERIES, anotar_valor, exportar,
                                 letra_panel, volcar_imagenes)

FIG = Path("docs/figures")
FIG.mkdir(parents=True, exist_ok=True)

feats = pd.read_parquet(CFG.gold / "celdas_500m.parquet")
ana = feats[feats["analizable"]].copy()
pos, neg = feats[feats["ref_positiva"]], feats[~feats["ref_positiva"]]
print(f"Celdas {len(feats):,} | analizables {len(ana):,} | positivas {len(pos):,}\n")


def auc_ic(y, s, n_boot=2000, seed=42):
    """AUC con intervalo de confianza del 95 % por bootstrap estratificado."""
    y, s = np.asarray(y), np.asarray(s)
    m = np.isfinite(s)
    y, s = y[m], s[m]
    base = roc_auc_score(y, s)
    if base < 0.5:
        s, base = -s, 1 - base
    ip, inn = np.where(y == 1)[0], np.where(y == 0)[0]
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.concatenate([rng.choice(ip, len(ip), True),
                              rng.choice(inn, len(inn), True)])
        boots[b] = roc_auc_score(y[idx], s[idx])
    boots = np.where(boots < 0.5, 1 - boots, boots)
    return base, np.percentile(boots, 2.5), np.percentile(boots, 97.5)


# ======================================================================
# Figura 1. Estructura de la distribución de recurrencia
# ======================================================================
print("Figura 1")
fig = make_subplots(rows=1, cols=3, horizontal_spacing=0.085)

bins = np.arange(0.5, 49.5, 1)
for nombre, sub, color, relleno in [
    ("Sin referencia térmica", neg, PALETA["vegetacion"], "rgba(27,120,55,0.15)"),
    ("Con referencia térmica", pos, PALETA["termica"], "rgba(178,24,43,0.18)"),
]:
    h, _ = np.histogram(sub["n_meses"], bins=bins)
    fig.add_trace(
        go.Scatter(
            x=bins[:-1], y=h / h.sum(), mode="lines", name=nombre,
            line=dict(color=color, width=2.3, shape="hv"),
            fill="tozeroy", fillcolor=relleno,
            hovertemplate="%{x:.0f} meses · %{y:.4f}<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_vline(x=sub["n_meses"].median(),
                  line=dict(color=color, width=1.3, dash="dash"),
                  row=1, col=1)

u = stats.mannwhitneyu(pos["n_meses"], neg["n_meses"], alternative="greater")
delta = u.statistic / (len(pos) * len(neg))
fig.add_annotation(
    text=(f"<i>U</i> de Mann-Whitney, <i>P</i> &lt; 10<sup>-300</sup><br>"
          f"prob. de superioridad = {delta:.3f}"),
    xref="x domain", yref="y domain", x=0.97, y=0.97, xanchor="right",
    showarrow=False, font=dict(size=9.5), bgcolor="rgba(255,255,255,0.9)",
    bordercolor="#BDBDBD", borderwidth=0.7, borderpad=3,
    row=1, col=1,
)

fig.update_xaxes(title_text="Meses con actividad", row=1, col=1)
fig.update_yaxes(title_text="Fracción de celdas", type="log", row=1, col=1)

for sub, color in [(neg, PALETA["vegetacion"]), (pos, PALETA["termica"])]:
    v = np.sort(sub["n_det"].to_numpy())
    fig.add_trace(
        go.Scatter(
            x=v, y=1 - np.arange(1, len(v) + 1) / len(v), mode="lines",
            line=dict(color=color, width=2.3), showlegend=False,
            hovertemplate="%{x} detecciones · P(X&gt;x)=%{y:.4f}<extra></extra>",
        ),
        row=1, col=2,
    )

fig.update_xaxes(title_text="Detecciones por celda, <i>n</i>", type="log",
                 row=1, col=2)
fig.update_yaxes(title_text="P(<i>N</i> &gt; <i>n</i>)", type="log",
                 row=1, col=2)

for nombre, sub, color in [("Sin ref.", neg, PALETA["vegetacion"]),
                           ("Con ref.", pos, PALETA["termica"])]:
    fig.add_trace(
        go.Box(
            y=np.log10(sub["n_det"]), name=nombre, marker_color=color,
            boxpoints=False, width=0.45, showlegend=False,
            hovertemplate="log₁₀(n) mediana %{median:.2f}<extra></extra>",
        ),
        row=1, col=3,
    )

fig.add_annotation(
    text=("El soporte muestral difiere en un orden de magnitud: "
          "confundidor de los descriptores de dispersión (véase Fig. 2)"),
    xref="x3 domain", yref="y3 domain", x=0.5, y=-0.22,
    xanchor="center", yanchor="top",
    showarrow=False, font=dict(size=9, color="#B2182B"),
    bgcolor="rgba(255,255,255,0.9)", bordercolor="#B2182B",
    borderwidth=0.8, borderpad=3,
    row=1, col=3,
)

fig.update_yaxes(title_text="log₁₀(detecciones por celda)", row=1, col=3)

fig.update_layout(
    height=470, width=1350,
    legend=dict(x=0.005, y=1.14, orientation="h"),
    margin=dict(b=110),
)
for letra, x in zip("abc", [-0.045, 0.315, 0.675]):
    letra_panel(fig, letra, x=x, y=1.10)
exportar(fig, FIG / "fig1_recurrencia", ancho=1350, alto=470)

# ======================================================================
# Figura 2. Confusión por soporte muestral
# ======================================================================
print("Figura 2 (bootstrap, ~1 min)")
g = auc_global(ana).set_index("descriptor")["auc"]
est = auc_estratificado(ana)
piv = est.pivot(index="descriptor", columns="estrato", values="auc")
orden = [c for c in ["3-5", "6-10", "11-25", "26-60", "61-+"] if c in piv.columns]
piv = piv[orden].assign(sin_control=g).sort_values(orden[-1], ascending=False)

fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.13,
                    column_widths=[0.55, 0.45])

fig.add_hrect(y0=0.44, y1=0.60, fillcolor="rgba(120,144,156,0.10)",
              line_width=0, layer="below", row=1, col=1)

ejex = ["Sin<br>control"] + orden
for i, d in enumerate(piv.index):
    ys = [piv.loc[d, "sin_control"]] + piv.loc[d, orden].tolist()
    c = SERIES[i % len(SERIES)]
    fig.add_trace(
        go.Scatter(
            x=ejex, y=ys, mode="lines+markers", name=d,
            line=dict(width=2.1, color=c),
            marker=dict(size=7.5, color=c, line=dict(color="white", width=1)),
            hovertemplate=f"<b>{d}</b><br>%{{x}} · AUC %{{y:.3f}}<extra></extra>",
        ),
        row=1, col=1,
    )

fig.add_hline(y=0.5, line=dict(color="#37474F", width=1.4, dash="dash"),
              row=1, col=1)
fig.add_annotation(
    text="clasificación aleatoria", xref="x domain", yref="y",
    x=0.97, y=0.5, xanchor="right", yshift=-11, showarrow=False,
    font=dict(size=9.5, color="#37474F"), row=1, col=1,
)
fig.update_xaxes(title_text="Estrato de detecciones por celda", row=1, col=1)
fig.update_yaxes(title_text="AUC", range=[0.43, 1.03], dtick=0.1, row=1, col=1)

# (b) IC 95 % DENTRO del estrato de mayor soporte. El emparejamiento global
# no alcanza equilibrio (no existen suficientes celdas negativas con soporte
# alto), de modo que la estratificación es el único control válido.
ESTRATO_CTRL = (26, 60)
ctrl = ana[(ana["n_det"] >= ESTRATO_CTRL[0]) & (ana["n_det"] <= ESTRATO_CTRL[1])]
filas = []
for d in DESCRIPTORES:
    if ctrl[d].notna().sum() < 60:
        continue
    a, lo, hi = auc_ic(ctrl["ref_positiva"].to_numpy().astype(int),
                       ctrl[d].to_numpy())
    filas.append({"descriptor": d, "auc": a, "lo": lo, "hi": hi,
                  "signif": lo > 0.5})
ic = pd.DataFrame(filas).sort_values("auc")

fig.add_vrect(x0=0.40, x1=0.60, fillcolor="rgba(120,144,156,0.10)",
              line_width=0, layer="below", row=1, col=2)
fig.add_trace(
    go.Scatter(
        x=ic["auc"], y=ic["descriptor"], mode="markers",
        error_x=dict(type="data", symmetric=False,
                     array=ic["hi"] - ic["auc"],
                     arrayminus=ic["auc"] - ic["lo"],
                     color="#37474F", thickness=1.5, width=6),
        marker=dict(size=11,
                    color=[PALETA["acento"] if s else PALETA["gris"]
                           for s in ic["signif"]],
                    line=dict(color="white", width=1.2)),
        showlegend=False,
        hovertemplate="<b>%{y}</b><br>AUC %{x:.3f}<extra></extra>",
    ),
    row=1, col=2,
)

for _, r in ic.iterrows():
    marca = "" if r["signif"] else "  n.s."
    fig.add_annotation(
        x=r["hi"], y=r["descriptor"],
        text=f"{r['auc']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]{marca}",
        xanchor="left", xshift=9, showarrow=False,
        font=dict(size=9, color="#1A1A1A" if r["signif"] else "#78909C"),
        row=1, col=2,
    )

fig.add_hline(y=0.5, line_width=0, row=1, col=2)
fig.add_vline(x=0.5, line=dict(color="#37474F", width=1.5, dash="dash"),
              row=1, col=2)
fig.update_xaxes(
    title_text=(f"AUC en el estrato {ESTRATO_CTRL[0]}–{ESTRATO_CTRL[1]} "
                f"detecciones (IC 95 %, <i>B</i> = 2000)"),
    range=[0.38, 1.14], row=1, col=2,
)

n_p_ctrl = int(ctrl["ref_positiva"].sum())
fig.add_annotation(
    text=(f"<i>n</i> = {len(ctrl):,} celdas ({n_p_ctrl} positivas) con soporte "
          f"muestral homogéneo.<br>"
          f"Puntos grises: intervalo que incluye 0,5 (no significativo)."),
    xref="x2 domain", yref="y2 domain", x=0.5, y=-0.16, xanchor="center",
    showarrow=False, font=dict(size=9.5, color="#455A64"), row=1, col=2,
)

fig.update_layout(
    height=620, width=1400,
    legend=dict(x=1.005, y=1, font=dict(size=10)),
    margin=dict(r=175, b=95),
)
letra_panel(fig, "a", x=-0.045, y=1.06)
letra_panel(fig, "b", x=0.545, y=1.06)
exportar(fig, FIG / "fig2_confusion_soporte", ancho=1400, alto=620)

# ======================================================================
# Figura 3. Distribución espacial
# ======================================================================
print("Figura 3")


def a_wgs84(df):
    g = gpd.GeoDataFrame(
        df, geometry=[Point(x, y) for x, y in zip(df["cx"], df["cy"])],
        crs=CFG.crs_metric).to_crs(CFG.crs_geo)
    return g.geometry.x.to_numpy(), g.geometry.y.to_numpy()


sub_neg = neg.sample(min(70_000, len(neg)), random_state=42)
lon_n, lat_n = a_wgs84(sub_neg)
lon_p, lat_p = a_wgs84(pos)

fig = go.Figure()

fig.add_trace(go.Scattergeo(
    lon=lon_n, lat=lat_n, mode="markers", name="Vegetación presunta",
    marker=dict(size=1.8, color="#37474F", opacity=0.35), hoverinfo="skip"))

fig.add_trace(go.Scattergeo(
    lon=lon_p, lat=lat_p, mode="markers", name="Referencia térmica (FIRMS)",
    marker=dict(
        size=np.clip(4 + 10 * np.log10(pos["n_det"]) / np.log10(370), 4, 15),
        color=pos["n_meses"], colorscale="YlOrRd", cmin=1, cmax=48,
        opacity=0.9, line=dict(width=0.7, color="#67000D"),
        colorbar=dict(
            title=dict(text="Meses con<br>actividad<br>(máx. 48)",
                       side="right", font=dict(size=10.5)),
            thickness=13, len=0.38, x=0.885, y=0.26,
            tickvals=[1, 12, 24, 36, 48], tickfont=dict(size=9.5),
            outlinewidth=0.8, outlinecolor="#616161"),
    ),
    customdata=np.column_stack([pos["n_det"], pos["n_meses"],
                                pos["frac_termica"], pos["frp_mediana"],
                                pos["frac_noche"]]),
    hovertemplate=("<b>%{lat:.4f}°, %{lon:.4f}°</b><br>"
                   "Detecciones: %{customdata[0]}<br>"
                   "Meses activos: %{customdata[1]} / 48<br>"
                   "Fracción térmica: %{customdata[2]:.2f}<br>"
                   "FRP mediana: %{customdata[3]:.1f} MW<br>"
                   "Fracción nocturna: %{customdata[4]:.2f}<extra></extra>")))

fig.update_geos(
    scope="south america", resolution=50,
    lonaxis_range=[-80.5, -65.5], lataxis_range=[-5.5, 14.5],
    showcountries=True, countrycolor="#4E6B52", countrywidth=1.1,
    showsubunits=True, subunitcolor="#9FB89F", subunitwidth=0.5,
    showland=True, landcolor="#C8DCC0",
    showocean=True, oceancolor="#D6E4EF",
    showrivers=True, rivercolor="#7FA8CC", riverwidth=0.8,
    showlakes=True, lakecolor="#D6E4EF",
    showcoastlines=True, coastlinecolor="#37474F", coastlinewidth=1.0,
    showframe=True, framecolor="#212121", framewidth=1.3,
    lataxis_showgrid=True, lonaxis_showgrid=True,
    lataxis_dtick=4, lonaxis_dtick=4,
    lataxis_gridcolor="rgba(0,0,0,0.11)",
    lonaxis_gridcolor="rgba(0,0,0,0.11)")

# Colombia resaltada sobre los países vecinos.
fig.add_trace(go.Choropleth(
    locations=["COL"], z=[1], locationmode="ISO-3",
    colorscale=[[0, "#A8CFA0"], [1, "#A8CFA0"]], showscale=False,
    marker_line_color="#1B3B22", marker_line_width=1.5, hoverinfo="skip"))
fig.data = fig.data[-1:] + fig.data[:-1]   # el relleno va al fondo

for nombre, lon, lat in [("VENEZUELA", -68.6, 8.2), ("BRASIL", -67.3, -2.6),
                         ("PERÚ", -74.0, -4.6), ("ECUADOR", -78.3, -1.2),
                         ("PANAMÁ", -78.2, 8.6)]:
    fig.add_trace(go.Scattergeo(
        lon=[lon], lat=[lat], mode="text", text=[nombre],
        textfont=dict(size=9, color="#546E5A"), showlegend=False,
        hoverinfo="skip"))

# --- Barra de escala gráfica ---------------------------------------
LAT_ESC, LON_ESC = -3.6, -79.5
KM = 200
dlon = KM / (111.32 * np.cos(np.radians(LAT_ESC)))
fig.add_trace(go.Scattergeo(
    lon=[LON_ESC, LON_ESC + dlon], lat=[LAT_ESC, LAT_ESC], mode="lines",
    line=dict(color="#212121", width=3.5), showlegend=False, hoverinfo="skip"))
for x in (LON_ESC, LON_ESC + dlon / 2, LON_ESC + dlon):
    fig.add_trace(go.Scattergeo(
        lon=[x, x], lat=[LAT_ESC - 0.16, LAT_ESC + 0.16], mode="lines",
        line=dict(color="#212121", width=1.8), showlegend=False,
        hoverinfo="skip"))
for x, t in [(LON_ESC, "0"), (LON_ESC + dlon / 2, f"{KM // 2}"),
             (LON_ESC + dlon, f"{KM} km")]:
    fig.add_trace(go.Scattergeo(
        lon=[x], lat=[LAT_ESC + 0.52], mode="text", text=[t],
        textfont=dict(size=9.5, color="#212121"), showlegend=False,
        hoverinfo="skip"))

# --- Indicador de norte geográfico ---------------------------------
fig.add_annotation(
    text="<b>N</b><br><span style='font-size:20px'>▲</span>",
    xref="paper", yref="paper", x=0.945, y=0.965, showarrow=False,
    align="center", font=dict(size=13, color="#212121"),
    bgcolor="rgba(255,255,255,0.92)", bordercolor="#546E7A",
    borderwidth=0.9, borderpad=5)

fig.add_annotation(
    text=(f"<b>{len(pos):,}</b> celdas con referencia térmica de "
          f"<b>{len(feats):,}</b> activas<br>"
          f"VIIRS 375 m (S-NPP, NOAA-20) · 2022–2025<br>"
          f"Rejilla 500 m · MAGNA-SIRGAS Origen Nacional (EPSG:9377)<br>"
          f"Proyección de visualización: equirrectangular<br>"
          f"Tamaño ∝ log₁₀(detecciones)"),
    xref="paper", yref="paper", x=0.015, y=0.015, showarrow=False,
    align="left", font=dict(size=9.5, color="#1B3B22"),
    bgcolor="rgba(255,255,255,0.94)", bordercolor="#7A9B80",
    borderwidth=0.9, borderpad=7)

fig.update_layout(
    height=880, width=740, margin=dict(l=15, r=15, t=50, b=15),
    legend=dict(x=0.015, y=0.985, bgcolor="rgba(255,255,255,0.94)",
                bordercolor="#7A9B80", borderwidth=0.8,
                font=dict(size=10.5)),
)
exportar(fig, FIG / "fig3_mapa", ancho=740, alto=880)

# ======================================================================
# Figura 3b. Versión interactiva con mapa base
# ======================================================================
print("Figura 3b: interactiva")
fig = go.Figure()

fig.add_trace(go.Scattermap(
    lon=lon_n, lat=lat_n, mode="markers", name="Vegetación presunta",
    marker=dict(size=2, color="#37474F", opacity=0.30), hoverinfo="skip"))

fig.add_trace(go.Scattermap(
    lon=lon_p, lat=lat_p, mode="markers", name="Referencia térmica",
    marker=dict(
        size=np.clip(6 + 12 * np.log10(pos["n_det"]) / np.log10(370), 6, 20),
        color=pos["n_meses"], colorscale="YlOrRd", cmin=1, cmax=48,
        opacity=0.85,
        colorbar=dict(title=dict(text="Meses<br>activos", side="right"),
                      thickness=14, len=0.35, x=0.985, y=0.22,
                      bgcolor="rgba(255,255,255,0.85)")),
    customdata=np.column_stack([pos["n_det"], pos["n_meses"],
                                pos["frac_termica"], pos["frp_mediana"],
                                pos["frac_noche"]]),
    hovertemplate=("<b>%{lat:.4f}°, %{lon:.4f}°</b><br>"
                   "Detecciones: %{customdata[0]}<br>"
                   "Meses activos: %{customdata[1]} / 48<br>"
                   "Fracción térmica: %{customdata[2]:.2f}<br>"
                   "FRP mediana: %{customdata[3]:.1f} MW<br>"
                   "Fracción nocturna: %{customdata[4]:.2f}<extra></extra>")))

fig.update_layout(
    map=dict(style="carto-positron", center=dict(lat=5.5, lon=-73.5),
             zoom=4.6),
    height=880, width=760, margin=dict(l=0, r=0, t=40, b=0),
    legend=dict(x=0.02, y=0.98, bgcolor="rgba(255,255,255,0.9)",
                bordercolor="#90A4AE", borderwidth=0.8),
)
fig.write_html(str(FIG / "fig3b_mapa_interactivo.html"), include_plotlyjs="cdn")
print("  fig3b_mapa_interactivo (html)")

# ======================================================================
# Figura 4. Inconsistencia de la máscara y curvas ROC
# ======================================================================
print("Figura 4")
fig = make_subplots(rows=1, cols=3, horizontal_spacing=0.085,
                    column_widths=[0.36, 0.28, 0.36])

h, edges = np.histogram(pos["frac_termica"], bins=25, range=(0, 1))
fig.add_trace(
    go.Bar(
        x=(edges[:-1] + edges[1:]) / 2, y=h, width=0.036,
        marker=dict(color=PALETA["candidata"],
                    line=dict(color="white", width=0.5)),
        showlegend=False,
        hovertemplate="%{x:.2f} · %{y} celdas<extra></extra>",
    ),
    row=1, col=1,
)
med = pos["frac_termica"].median()
fig.add_vline(x=med, line=dict(color=PALETA["termica"], width=1.6, dash="dash"),
              row=1, col=1)
anotar_valor(fig, med, h.max() * 0.9, f"mediana {med:.2f}", dx=-44, dy=-16,
             row=1, col=1)
fig.update_xaxes(title_text="Fracción de detecciones térmicas por celda",
                 range=[0, 1.02], row=1, col=1)
fig.update_yaxes(title_text="Celdas", row=1, col=1)

n_p, n_m = int(pos["type_pura"].sum()), int((~pos["type_pura"]).sum())
fig.add_trace(
    go.Bar(
        x=["Consistente", "Contradictoria"], y=[n_p, n_m],
        marker=dict(color=[PALETA["neutro"], PALETA["termica"]],
                    line=dict(color="white", width=1)),
        text=[f"<b>{n_p}</b><br>{100 * n_p / len(pos):.1f} %",
              f"<b>{n_m}</b><br>{100 * n_m / len(pos):.1f} %"],
        textposition="outside", textfont=dict(size=11.5), showlegend=False,
        hovertemplate="%{x} · %{y} celdas<extra></extra>",
    ),
    row=1, col=2,
)
fig.update_xaxes(title_text="Etiqueta dentro de la celda", row=1, col=2)
fig.update_yaxes(title_text="Celdas con referencia térmica",
                 range=[0, n_m * 1.3], row=1, col=2)

# Curvas ROC dentro del estrato de control, coherentes con la Fig. 2b.
top = ic.nlargest(4, "auc")["descriptor"].tolist()
for i, d in enumerate(top):
    m = ctrl[d].notna()
    s = ctrl.loc[m, d].to_numpy()
    y = ctrl.loc[m, "ref_positiva"].to_numpy().astype(int)
    if roc_auc_score(y, s) < 0.5:
        s = -s
    fpr, tpr, _ = roc_curve(y, s)
    a = float(ic.loc[ic["descriptor"] == d, "auc"].iloc[0])
    fig.add_trace(
        go.Scatter(
            x=fpr, y=tpr, mode="lines", name=f"{d} ({a:.3f})",
            line=dict(width=2.1, color=SERIES[i]),
            hovertemplate=(f"<b>{d}</b><br>FPR %{{x:.3f}} · "
                           f"TPR %{{y:.3f}}<extra></extra>"),
        ),
        row=1, col=3,
    )

fig.add_trace(
    go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
               line=dict(color="#78909C", width=1.2, dash="dash"),
               showlegend=False, hoverinfo="skip"),
    row=1, col=3,
)
fig.update_xaxes(title_text="Tasa de falsos positivos", range=[0, 1],
                 row=1, col=3)
fig.update_yaxes(title_text="Tasa de verdaderos positivos", range=[0, 1.02],
                 row=1, col=3)

fig.add_annotation(
    text=(f"Curvas ROC calculadas en el estrato {ESTRATO_CTRL[0]}–"
          f"{ESTRATO_CTRL[1]} detecciones (<i>n</i> = {len(ctrl):,})"),
    xref="x3 domain", yref="y3 domain", x=0.5, y=-0.18, xanchor="center",
    showarrow=False, font=dict(size=9, color="#455A64"), row=1, col=3,
)

fig.update_layout(
    height=500, width=1400,
    legend=dict(x=0.985, y=0.03, xanchor="right", yanchor="bottom",
                font=dict(size=9.5), bgcolor="rgba(255,255,255,0.92)",
                bordercolor="#BDBDBD", borderwidth=0.8),
    margin=dict(b=90),
)
for letra, x in zip("abc", [-0.045, 0.325, 0.655]):
    letra_panel(fig, letra, x=x, y=1.09)
exportar(fig, FIG / "fig4_inconsistencia", ancho=1400, alto=500)

# ======================================================================
volcar_imagenes()
print("\nListo. docs/figures/")