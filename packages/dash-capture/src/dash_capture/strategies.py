# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Three-stage capture strategies: preprocess → capture → postprocess.

The preprocess and capture stages are JS functions that run in the browser.
The postprocess stage is a Python renderer function (handled separately).

Built-in strategies:
- ``plotly_strategy`` — ``Plotly.toImage()`` with optional strip patches
- ``html2canvas_strategy`` — ``html2canvas()`` for arbitrary DOM elements
- ``canvas_strategy`` — raw ``canvas.toDataURL()`` for canvas elements

The JS fragments here are intentionally kept in sync with
``r-packages/shinycapture/inst/shinycapture/shinycapture.js``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaptureStrategy:
    """Three-stage capture pipeline definition.

    Parameters
    ----------
    preprocess :
        JS code that runs before capture.  Receives ``(el, opts)`` where
        *el* is the DOM element and *opts* is the capture options dict.
        May mutate the element or create a temporary clone.
        ``None`` means no preprocessing.
    capture :
        JS code that performs the actual capture.  Receives ``(el, opts)``
        and must return a base64 data-URI string (or a Promise thereof).

    .. warning::
        Both fields execute as JavaScript in the browser.
        Never pass untrusted user input into these fields.
    """

    preprocess: str | None = None
    capture: str = ""


# ---------------------------------------------------------------------------
# Strip-patch JS fragments (shared with shinycapture R package)
# ---------------------------------------------------------------------------

_STRIP_TITLE = [
    "layout.title = {text: ''};",
    "layout.margin = {...(layout.margin || {}), t: 20};",
]
_STRIP_LEGEND = ["layout.showlegend = false;"]
_STRIP_ANNOTATIONS = ["layout.annotations = [];"]
_STRIP_AXIS_TITLES = [
    "Object.keys(layout).forEach(k => {"
    " if (/^[xy]axis/.test(k))"
    " layout[k] = {...(layout[k]||{}), title: {text: ''}}; });"
]
_STRIP_COLORBAR = ["data = data.map(t => ({...t, showscale: false}));"]
_STRIP_MARGIN = ["layout.margin = {l:0, r:0, t:0, b:0, pad:0};"]


def _build_strip_patches(
    strip_title: bool = False,
    strip_legend: bool = False,
    strip_annotations: bool = False,
    strip_axis_titles: bool = False,
    strip_colorbar: bool = False,
    strip_margin: bool = False,
) -> list[str]:
    """Build JS patch statements for Plotly figure stripping."""
    patches: list[str] = []
    if strip_title:
        patches += _STRIP_TITLE
    if strip_legend:
        patches += _STRIP_LEGEND
    if strip_annotations:
        patches += _STRIP_ANNOTATIONS
    if strip_axis_titles:
        patches += _STRIP_AXIS_TITLES
    if strip_colorbar:
        patches += _STRIP_COLORBAR
    if strip_margin:
        patches += _STRIP_MARGIN
    return patches


def _build_plotly_preprocess(patches: list[str], params: dict) -> str | None:
    """Build JS preprocess code that clones the Plotly figure into an offscreen div."""
    if not patches:
        return None

    dim_w = (
        "capture_width != null ? capture_width : graphDiv.offsetWidth"
        if "capture_width" in params
        else "graphDiv.offsetWidth"
    )
    dim_h = (
        "capture_height != null ? capture_height : graphDiv.offsetHeight"
        if "capture_height" in params
        else "graphDiv.offsetHeight"
    )
    patches_js = "\n                ".join(patches)

    return f"""\
                const layout = JSON.parse(
                    JSON.stringify(graphDiv.layout || {{}}));
                let data = graphDiv.data;
                {patches_js}
                const tmp = document.createElement('div');
                tmp.style.cssText =
                    'position:fixed;left:-9999px;width:'
                    + ({dim_w}) + 'px;height:' + ({dim_h}) + 'px';
                document.body.appendChild(tmp);
                await Plotly.newPlot(tmp, data, layout);
                el._dcap_tmp = tmp;"""


_PLOTLY_CAPTURE = """\
                const target = el._dcap_tmp || graphDiv;
                try {
                    return await Plotly.toImage(target, opts);
                } finally {
                    if (el._dcap_tmp) {
                        document.body.removeChild(el._dcap_tmp);
                        delete el._dcap_tmp;
                    }
                }"""

_PLOTLY_CAPTURE_SIMPLE = """\
                return await Plotly.toImage(graphDiv, opts);"""

_HTML2CANVAS_CAPTURE = """\
                if (!window.html2canvas) {
                    console.error('dash-capture: html2canvas is not loaded. '
                        + 'Include it via app.scripts or external_scripts.');
                    return window.dash_clientside.no_update;
                }
                const canvas = await html2canvas(el, {
                    scale: opts.scale || 2,
                    useCORS: true,
                    logging: false
                });
                return canvas.toDataURL('image/png');"""

_CANVAS_CAPTURE = """\
                const cvs = el.querySelector('canvas') || el;
                return cvs.toDataURL('image/png');"""


# ---------------------------------------------------------------------------
# Built-in strategy factories
# ---------------------------------------------------------------------------


def plotly_strategy(
    strip_title: bool = False,
    strip_legend: bool = False,
    strip_annotations: bool = False,
    strip_axis_titles: bool = False,
    strip_colorbar: bool = False,
    strip_margin: bool = False,
    _params: dict | None = None,
) -> CaptureStrategy:
    """Plotly.toImage() strategy with optional strip patches.

    Parameters
    ----------
    strip_title, strip_legend, strip_annotations, strip_axis_titles,
    strip_colorbar, strip_margin :
        Remove the corresponding element from the figure before capture.
    """
    patches = _build_strip_patches(
        strip_title, strip_legend, strip_annotations,
        strip_axis_titles, strip_colorbar, strip_margin,
    )
    preprocess = _build_plotly_preprocess(patches, _params or {})
    capture = _PLOTLY_CAPTURE if preprocess else _PLOTLY_CAPTURE_SIMPLE
    return CaptureStrategy(preprocess=preprocess, capture=capture)


def html2canvas_strategy() -> CaptureStrategy:
    """html2canvas strategy for capturing arbitrary DOM elements."""
    return CaptureStrategy(capture=_HTML2CANVAS_CAPTURE)


def canvas_strategy() -> CaptureStrategy:
    """Raw canvas.toDataURL() strategy for canvas-based components."""
    return CaptureStrategy(capture=_CANVAS_CAPTURE)


# ---------------------------------------------------------------------------
# JS assembly — wraps the strategy into a Dash clientside callback function
# ---------------------------------------------------------------------------


def build_capture_js(
    element_id: str,
    strategy: CaptureStrategy,
    active_capture: list[str],
    params: dict,
) -> str:
    """Assemble a CaptureStrategy into a Dash clientside callback JS function.

    Parameters
    ----------
    element_id :
        The DOM id of the element to capture.
    strategy :
        The capture strategy (preprocess + capture JS fragments).
    active_capture :
        Parameter names starting with ``capture_`` that map to Plotly.toImage
        options (e.g. ``capture_width`` → ``width``).
    params :
        The renderer's ``inspect.signature().parameters`` dict.
    """
    js_args = ", ".join(["n_clicks", "n_intervals", *active_capture])
    js_build_opts = "\n                ".join(
        f"if ({p} != null) opts.{p[len('capture_'):]} = {p};"
        for p in active_capture
    )

    # Element lookup — Plotly-aware (look for .js-plotly-plot inside container)
    # For non-Plotly strategies, graphDiv === el which is fine.
    # Escape element_id to prevent JS injection via crafted component IDs
    safe_id = element_id.replace("\\", "\\\\").replace("'", "\\'")

    js_head = f"""
            async function({js_args}) {{
                if (!n_clicks && !n_intervals) {{
                    return window.dash_clientside.no_update;
                }}
                const el = document.getElementById('{safe_id}');
                if (!el) return window.dash_clientside.no_update;
                const graphDiv =
                    el.querySelector('.js-plotly-plot') || el;
                const opts = {{format: 'png'}};
                {js_build_opts}
        """

    body_parts = []
    if strategy.preprocess:
        body_parts.append(strategy.preprocess)
    body_parts.append(strategy.capture)

    body = "\n".join(body_parts)
    return js_head + body + "\n            }"
