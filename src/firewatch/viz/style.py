"""Estilo de figuras para publicación científica.

Convenciones: ejes abiertos sin marco, rejilla punteada tenue, letras de
panel en caja con borde y anotación explícita de los valores relevantes
sobre la geometría de datos.

Nota sobre exportación. Kaleido levanta un navegador headless por cada
invocación de `write_image` y en Windows no siempre logra cerrarlo, lo que
deja procesos residuales que corrompen las llamadas posteriores de forma
intermitente. Para evitarlo, las figuras se registran durante la ejecución
y las imágenes se escriben al final, en una sola pasada, mediante
`volcar_imagenes`. El HTML se escribe de inmediato porque no depende del
renderizador.
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

PALETA = {
    "vegetacion": "#1B7837",
    "termica":    "#B2182B",
    "candidata":  "#E08214",
    "neutro":     "#37474F",
    "gris":       "#78909C",
    "gris_claro": "#CFD8DC",
    "acento":     "#2166AC",
    "tierra":     "#C8DCC0",
    "agua":       "#D6E4EF",
}

#: Secuencia cualitativa para series múltiples, con contraste suficiente
#: en impresión monocroma.
SERIES = ["#B2182B", "#2166AC", "#1B7837", "#E08214",
          "#762A83", "#01665E", "#8C510A", "#4D4D4D"]


def _eje(titulo: str = "", **kw) -> dict:
    return dict(
        title=dict(text=titulo, font=dict(size=13.5)),
        showline=True, linewidth=1.2, linecolor="#212121",
        ticks="outside", ticklen=6, tickwidth=1.2, tickcolor="#212121",
        tickfont=dict(size=11.5),
        showgrid=True, gridcolor="rgba(0,0,0,0.07)", griddash="dot",
        gridwidth=0.8, zeroline=False, mirror=False, **kw,
    )


TEMA = go.layout.Template(layout=go.Layout(
    font=dict(family="Helvetica, Arial, sans-serif", size=12, color="#1A1A1A"),
    paper_bgcolor="white", plot_bgcolor="white",
    margin=dict(l=75, r=35, t=55, b=65),
    xaxis=_eje(), yaxis=_eje(),
    hoverlabel=dict(bgcolor="white", bordercolor="#212121",
                    font=dict(size=12, family="Helvetica, Arial")),
    legend=dict(bgcolor="rgba(255,255,255,0.85)", bordercolor="#BDBDBD",
                borderwidth=0.8, font=dict(size=11)),
    colorway=SERIES,
))

pio.templates["firewatch"] = TEMA
pio.templates.default = "firewatch"


def letra_panel(fig, letra: str, x: float = -0.075, y: float = 1.09):
    """Letra de panel en caja con borde, convención de revista."""
    fig.add_annotation(
        text=f"<b>{letra}</b>", xref="paper", yref="paper", x=x, y=y,
        showarrow=False, font=dict(size=15, color="#1A1A1A"),
        bordercolor="#1A1A1A", borderwidth=1.2, borderpad=4, bgcolor="white",
    )
    return fig


def anotar_valor(fig, x, y, texto: str, dx: int = 0, dy: int = -22,
                 row=None, col=None):
    """Etiqueta numérica sobre un punto, con guía al dato."""
    kw = dict(x=x, y=y, text=texto, showarrow=True, arrowhead=0,
              arrowwidth=0.9, arrowcolor="#616161", ax=dx, ay=dy,
              font=dict(size=10.5, color="#1A1A1A"),
              bgcolor="rgba(255,255,255,0.9)", bordercolor="#BDBDBD",
              borderwidth=0.7, borderpad=2.5)
    if row is not None:
        fig.add_annotation(row=row, col=col, **kw)
    else:
        fig.add_annotation(**kw)
    return fig


# ----------------------------------------------------------------------
# Exportación diferida
# ----------------------------------------------------------------------

#: Figuras registradas a la espera de ser escritas como imagen.
_PENDIENTES: list[tuple] = []


def exportar(fig, ruta: Path, ancho: int = 1100, alto: int = 750,
             escala: int = 3) -> None:
    """Escribe el HTML y registra la figura para exportación posterior.

    Las imágenes no se escriben aquí: se acumulan y se generan al final
    mediante `volcar_imagenes`, para no reiniciar el renderizador en cada
    figura.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(f"{ruta}.html", include_plotlyjs="cdn")
    _PENDIENTES.append((fig, ruta, ancho, alto, escala))
    print(f"  {ruta.name} (html)")


def volcar_imagenes(formatos: tuple[str, ...] = ("svg", "png")) -> None:
    """Escribe las figuras registradas como imagen, en una sola pasada.

    El SVG se genera primero por ser vectorial y suficiente para
    publicación; si el renderizador falla a mitad de la ejecución, se
    conserva al menos el formato de mayor calidad.
    """
    if not _PENDIENTES:
        print("Sin figuras pendientes.")
        return

    print(f"\nExportando {len(_PENDIENTES)} figuras...")
    fallos = 0
    for fig, ruta, ancho, alto, escala in _PENDIENTES:
        for ext in formatos:
            esc = escala if ext == "png" else 1
            try:
                fig.write_image(f"{ruta}.{ext}", width=ancho, height=alto,
                                scale=esc)
                print(f"  {ruta.name}.{ext}")
            except Exception as e:
                fallos += 1
                print(f"  FALLO {ruta.name}.{ext}: {type(e).__name__}")

    _PENDIENTES.clear()
    if fallos:
        print(f"\n{fallos} exportaciones fallaron. El HTML de cada figura "
              f"está disponible y permite descargar el PNG desde el icono "
              f"de cámara en la barra de herramientas del navegador.")