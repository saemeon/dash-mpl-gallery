# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Output rendering pipeline for interact().

Analogous to matplotlib's unit converter registry: a global type → renderer
mapping is checked before the built-in converter chain.  Register third-party
types once at app startup; all interact() calls pick it up automatically.
"""

from __future__ import annotations

import base64
import io
import sys
from collections.abc import Callable
from typing import Any

from dash import dcc, html

# Global type → renderer registry.
# Keys are types; values are callables (result) -> Dash component.
_RENDERERS: dict[type, Callable] = {}


def register_renderer(type_: type, renderer: Callable[[Any], Any]) -> None:
    """Register a custom renderer for a Python type.

    The renderer is called with the return value of the function whenever
    ``interact()`` produces a result of the registered type (or a subclass).
    This avoids passing ``_render=`` on every ``interact()`` call.

    Analogous to matplotlib's unit converter registry — register once at app
    startup, applies everywhere.

    Later registrations for the same type overwrite earlier ones.  For subclass
    disambiguation, register the more-specific type after the base type; the
    registry is checked in insertion order and the first ``isinstance`` match wins.

    Example::

        import pandas as pd
        from dash import dash_table
        from dash_fn_forms import register_renderer

        register_renderer(
            pd.DataFrame,
            lambda df: dash_table.DataTable(
                data=df.to_dict("records"),
                columns=[{"name": c, "id": c} for c in df.columns],
            ),
        )

        # all interact() calls that return a DataFrame now use this renderer
        panel = interact(get_data)
    """
    _RENDERERS[type_] = renderer


def to_component(result: Any, renderer: Callable[[Any], Any] | None) -> Any:
    """Convert *result* to a Dash-renderable value.

    Resolution order:

    1. Explicit *renderer* callable (highest priority).
    2. Global registry — first ``isinstance`` match wins.
    3. Built-ins (in order):
       - ``go.Figure`` → ``dcc.Graph``
       - Dash component → as-is
       - ``dict`` → labelled card grid
       - ``str`` → ``dcc.Markdown``
       - ``int`` / ``float`` / ``bool`` → ``html.P``
       - ``pd.DataFrame`` → ``DataTable`` (or ``html.Table`` fallback)
       - ``matplotlib.figure.Figure`` → base64 PNG ``html.Img``
    4. Fallback: ``html.Pre(repr(...))``

    Optional-library checks (pandas, matplotlib) use ``sys.modules`` so those
    packages are never imported solely for a type check.
    """
    if result is None:
        return None

    if renderer is not None:
        try:
            return renderer(result)
        except Exception as exc:
            return _error(f"Render error: {exc}")

    # Global registry
    for type_, registered in _RENDERERS.items():
        if isinstance(result, type_):
            try:
                return registered(result)
            except Exception as exc:
                return _error(f"Render error: {exc}")

    # Built-in: Plotly Figure → dcc.Graph (plotly is a project dependency)
    try:
        import plotly.graph_objects as go  # noqa: PLC0415

        if isinstance(result, go.Figure):
            return dcc.Graph(figure=result)
    except ImportError:
        pass

    # Built-in: Dash component → as-is
    if hasattr(result, "_type"):
        return result

    # Built-in: dict → labelled card grid
    if isinstance(result, dict):
        return _dict_to_component(result, renderer)

    # Built-in: str → Markdown
    if isinstance(result, str):
        return dcc.Markdown(result)

    # Built-in: scalar → plain text
    if isinstance(result, (int, float, bool)):
        return html.P(str(result))

    # Built-in: pandas DataFrame → DataTable or html.Table
    # sys.modules check avoids importing pandas just for the isinstance
    if "pandas" in sys.modules:
        pd = sys.modules["pandas"]
        if isinstance(result, pd.DataFrame):
            return _dataframe_to_component(result)

    # Built-in: matplotlib Figure → base64 PNG image
    if "matplotlib.figure" in sys.modules and isinstance(
        result, sys.modules["matplotlib.figure"].Figure
    ):
        return _matplotlib_to_img(result)

    # Fallback: repr
    return html.Pre(
        repr(result),
        style={"fontFamily": "monospace", "whiteSpace": "pre-wrap"},
    )


def _dataframe_to_component(df: Any) -> Any:
    try:
        from dash import dash_table  # noqa: PLC0415

        return dash_table.DataTable(
            data=df.to_dict("records"),
            columns=[{"name": str(c), "id": str(c)} for c in df.columns],
            page_size=20,
            style_table={"overflowX": "auto"},
        )
    except ImportError:
        # Dash < 2.0 ships dash_table separately; fall back to plain html.Table
        header = html.Thead(html.Tr([html.Th(str(c)) for c in df.columns]))
        rows = [
            html.Tr([html.Td(str(v)) for v in row])
            for row in df.itertuples(index=False)
        ]
        return html.Table(
            [header, html.Tbody(rows)],
            style={"borderCollapse": "collapse", "width": "100%"},
        )


def _matplotlib_to_img(fig: Any) -> Any:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return html.Img(
        src=f"data:image/png;base64,{encoded}",
        style={"maxWidth": "100%"},
    )


def _dict_to_component(d: dict, renderer: Callable[[Any], Any] | None) -> html.Div:
    _label_style = {"color": "#888", "fontSize": "0.75rem", "marginRight": "6px"}
    rows = []
    for key, val in d.items():
        content = to_component(val, renderer)
        label = html.Span(str(key), style=_label_style)
        # scalars: single inline row — "key  value"
        if isinstance(content, (html.P, dcc.Markdown)) or content is None:
            rows.append(
                html.Div(
                    [label, content],
                    style={"display": "flex", "alignItems": "baseline", "gap": "4px", "marginBottom": "4px"},
                )
            )
        else:
            # rich content (figure, table, …): label on top, content below
            rows.append(
                html.Div(
                    [label, html.Div(content, style={"marginTop": "4px"})],
                    style={"marginBottom": "8px"},
                )
            )
    return html.Div(rows)


def _error(msg: str) -> html.Pre:
    return html.Pre(msg, style={"color": "#d9534f", "fontFamily": "monospace"})
