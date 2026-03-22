# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

from __future__ import annotations

import base64
import inspect
import io
from collections.abc import Callable
from typing import Any, cast

import dash
from dash import Input, Output, State, dcc, html

from dash_fn_interact import Field, FieldHook, FnForm, FromComponent, field_id
from dash_capture._ids import id_generator
from dash_capture.dropdown import build_dropdown
from dash_capture.wizard import build_wizard


class FromPlotly(FromComponent):
    """Read a value from the Plotly figure as the field default.

    Parameters
    ----------
    path :
        Dot-separated path into the figure dict, e.g. ``"layout.title.text"``.
    graph :
        The ``dcc.Graph`` component whose figure to read.
    """

    def __init__(self, path: str, graph: dcc.Graph):
        super().__init__(graph, "figure")
        self.path = path

    def get_default(self, *state_values: Any) -> Any:
        figure = state_values[0] if state_values else {}
        return _get_nested(figure, self.path)


# --- internal helpers ---

_UNSET: Callable = cast(Callable, object())


def _make_snapshot_fn(img_b64: str) -> Callable[[], bytes]:
    """Return a callable that decodes the base64 PNG to raw bytes.

    Renderers receive this callable as ``_snapshot_img`` and decode
    the bytes however their library requires (e.g. ``plt.imread``,
    ``PIL.Image.open``, …).
    """

    def _snapshot_img() -> bytes:
        b64 = img_b64.split(",", 1)[1]
        return base64.b64decode(b64)

    return _snapshot_img


def _call_renderer(
    renderer: Callable,
    has_fig_data: bool,
    has_snapshot: bool,
    fig_data: dict,
    img_b64: str,
    kwargs: dict,
) -> bytes:
    buf = io.BytesIO()
    call_kwargs = dict(kwargs)
    if has_fig_data:
        call_kwargs["_fig_data"] = fig_data
    if has_snapshot:
        call_kwargs["_snapshot_img"] = _make_snapshot_fn(img_b64)
    renderer(buf, **call_kwargs)
    buf.seek(0)
    return buf.read()


def _to_src(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _build_strip_patches(
    strip_title: bool,
    strip_legend: bool,
    strip_annotations: bool,
    strip_axis_titles: bool,
    strip_colorbar: bool,
    strip_margin: bool,
) -> list[str]:
    patches = []
    if strip_title:
        patches += [
            "layout.title = {text: ''};",
            "layout.margin = {...(layout.margin || {}), t: 20};",
        ]
    if strip_legend:
        patches.append("layout.showlegend = false;")
    if strip_annotations:
        patches.append("layout.annotations = [];")
    if strip_axis_titles:
        patches.append(
            "Object.keys(layout).forEach(k => {"
            " if (/^[xy]axis/.test(k))"
            " layout[k] = {...(layout[k]||{}), title: {text: ''}}; });"
        )
    if strip_colorbar:
        patches.append("data = data.map(t => ({...t, showscale: false}));")
    if strip_margin:
        patches.append("layout.margin = {l:0, r:0, t:0, b:0, pad:0};")
    return patches


def _build_capture_js(
    graph_id: str,
    active_capture: list[str],
    strip_patches: list[str],
    params,
) -> str:
    js_args = ", ".join(["n_clicks", "n_intervals", *active_capture])
    js_build_opts = "\n                ".join(
        f"if ({p} != null) opts.{p[len('capture_') :]} = {p};" for p in active_capture
    )
    js_head = f"""
            async function({js_args}) {{
                if (!n_clicks && !n_intervals) {{
                    return window.dash_clientside.no_update;
                }}
                if (!window.Plotly) return window.dash_clientside.no_update;
                const container = document.getElementById('{graph_id}');
                if (!container) return window.dash_clientside.no_update;
                const graphDiv =
                    container.querySelector('.js-plotly-plot') || container;
                const opts = {{format: 'png'}};
                {js_build_opts}
        """
    if not strip_patches:
        return js_head + "return await Plotly.toImage(graphDiv, opts);\n            }"

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
    patches_js = "\n                ".join(strip_patches)
    return (
        js_head
        + f"""
                const layout = JSON.parse(
                    JSON.stringify(graphDiv.layout || {{}}));
                let data = graphDiv.data;
                {patches_js}
                const tmp = document.createElement('div');
                tmp.style.cssText =
                    'position:fixed;left:-9999px;width:'
                    + ({dim_w}) + 'px;height:' + ({dim_h}) + 'px';
                document.body.appendChild(tmp);
                try {{
                    await Plotly.newPlot(tmp, data, layout);
                    const img = await Plotly.toImage(tmp, opts);
                    return img;
                }} finally {{
                    document.body.removeChild(tmp);
                }}
            }}"""
    )


def _build_modal_body(
    config_div,
    generate_id: str,
    download_id: str,
    preview_id: str,
    interval_id: str,
    snapshot_store_id: str,
    styles: dict,
    class_names: dict,
) -> html.Div:
    return html.Div(
        style={"display": "flex", "gap": "24px"},
        children=[
            html.Div(
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "8px",
                    "minWidth": "160px",
                },
                children=[
                    config_div,
                    html.Button(
                        "Generate",
                        id=generate_id,
                        style=styles.get("button"),
                        className=class_names.get("button", ""),
                    ),
                    dcc.Download(id=download_id),
                    html.Button(
                        "Download",
                        id=f"{download_id}_btn",
                        style=styles.get("button"),
                        className=class_names.get("button", ""),
                    ),
                ],
            ),
            html.Div(
                style={"position": "relative", "width": "400px", "height": "300px"},
                children=[
                    dcc.Loading(
                        type="circle",
                        children=[html.Img(id=preview_id, style={"maxWidth": "400px"})],
                    ),
                ],
            ),
            dcc.Interval(
                id=interval_id,
                interval=500,
                n_intervals=0,
                max_intervals=1,
                disabled=True,
            ),
            dcc.Store(id=snapshot_store_id),
        ],
    )


def graph_exporter(
    graph: str | dcc.Graph,
    renderer: Callable = _UNSET,
    trigger: str | Any = "Export",
    strip_title: bool = False,
    strip_legend: bool = False,
    strip_annotations: bool = False,
    strip_axis_titles: bool = False,
    strip_colorbar: bool = False,
    strip_margin: bool = False,
    filename: str = "figure.png",
    autogenerate: bool = False,
    styles: dict | None = None,
    class_names: dict | None = None,
    field_specs: dict[str, Field | FieldHook] | None = None,
) -> html.Div:
    """Add an export wizard button for a dcc.Graph.

    The renderer controls everything: how the figure is built, what library
    is used, and what format is written to ``_target``. The library only
    manages the Dash wiring and provides the ``_target`` buffer and, when
    requested, a raw PNG ``_snapshot_img`` callable.

    Parameters
    ----------
    graph :
        The ``dcc.Graph`` component or its string ``id``.
    renderer :
        Callable with signature
        ``(_target, [_fig_data], [_snapshot_img], **wizard_fields)``.

        * ``_target`` — always injected: file-like object to write to.
        * ``_fig_data`` — injected when present: Plotly figure dict.
        * ``_snapshot_img`` — injected when present: triggers browser capture;
          calling it returns the raw PNG bytes of the captured image.
        * All other parameters become wizard fields (type-inferred from
          annotations/defaults). Parameters named ``capture_*`` are also
          forwarded to ``Plotly.toImage`` at capture time (prefix stripped).
        * Parameters whose default is a :class:`FromPlotly` instance are
          populated from the live figure when the wizard opens.

        The renderer is responsible for writing to ``_target``. It may use
        any library (matplotlib, plotnine, PIL, …).
        Defaults to :func:`dash_capture.mpl.snapshot_renderer`.
    trigger :
        Either a string label (creates a plain ``html.Button``) or a custom
        Dash component with an ``id`` attribute that responds to ``n_clicks``.
        Defaults to ``"Export"``.
    strip_title :
        Remove the figure title before capture.
    strip_legend :
        Hide the legend before capture.
    strip_annotations :
        Remove all annotations before capture.
    strip_axis_titles :
        Remove x/y axis titles before capture.
    strip_colorbar :
        Hide colorbars (``showscale: false``) on all traces before capture.
    strip_margin :
        Zero all figure margins before capture.
    filename :
        Download filename including extension. Defaults to ``"figure.png"``.
    autogenerate :
        Whether Auto-generate is checked by default. Defaults to ``False``.
    styles :
        Dict mapping slot names to CSS-property dicts. Slots:
        ``"dialog"`` (modal container), ``"title"`` (header title),
        ``"close"`` (✕ button), ``"button"`` (Generate/Download/Reset/···
        buttons), ``"panel"`` (··· dropdown panel), ``"label"`` (field
        labels), and all Python type slots
        (``"str"``, ``"int"``, ``"float"``, ``"bool"``, ``"date"``,
        ``"datetime"``, ``"literal"``, ``"list"``, ``"tuple"``).
        Example: ``{"dialog": {"borderRadius": "8px"},
        "button": {"background": "#2563eb"}}``.
    class_names :
        Dict mapping the same slot names to CSS class name strings.
    field_specs :
        Per-field customisation for renderer parameters, keyed by name.
        Values may be a :class:`~dash_fn_interact.Field` or a bare
        :class:`~dash_fn_interact.FieldHook`.  Use this to override a
        component, add a label, set min/max, etc.

        Example::

            field_specs={
                "dpi": FieldSpec(component=dcc.Slider(min=72, max=600, value=300)),
            }

    Returns
    -------
    html.Div
        A component containing the trigger button and the self-contained modal.
        Place it anywhere in the layout.
    """
    if renderer is _UNSET:
        from dash_capture.mpl import snapshot_renderer

        renderer = snapshot_renderer

    graph_id = graph if isinstance(graph, str) else cast(Any, graph).id
    uid = id_generator(graph_id)
    config_id = f"_dcap_cfg_{uid}"
    wizard_id = f"_dcap_fig_{uid}"
    preview_id = f"_dcap_preview_{uid}"
    generate_id = f"_dcap_generate_{uid}"
    download_id = f"_dcap_download_{uid}"
    interval_id = f"_dcap_interval_{uid}"
    restore_id = f"_dcap_restore_{uid}"
    menu_id = f"_dcap_menu_{uid}"
    autogenerate_id = f"_dcap_autogen_{uid}"
    snapshot_store_id = f"_dcap_snapshot_{uid}"

    params = inspect.signature(renderer).parameters
    _has_snapshot = "_snapshot_img" in params
    _has_fig_data = "_fig_data" in params
    _active_capture = [name for name in params if name.startswith("capture_")]

    _styles = styles or {}
    _class_names = class_names or {}

    config = FnForm(
        config_id,
        renderer,
        _styles=_styles,
        _class_names=_class_names,
        _field_specs=field_specs,
        _show_docstring=False,
    )

    menu = build_dropdown(
        menu_id,
        trigger_label="···",
        close_inputs=[Input(restore_id, "n_clicks")],
        styles=_styles,
        class_names=_class_names,
        children=[
            html.Button(
                "Reset to defaults",
                id=restore_id,
                style=_styles.get("button"),
                className=_class_names.get("button", ""),
            ),
            dcc.Checklist(
                id=autogenerate_id,
                options=[{"label": " Auto-generate", "value": "auto"}],
                value=["auto"] if autogenerate else [],
                style={"padding": "4px 8px"},
                labelStyle={
                    k: v
                    for k, v in (_styles.get("label") or {}).items()
                    if k == "color"
                },
            ),
        ],
    )

    body = _build_modal_body(
        config,
        generate_id,
        download_id,
        preview_id,
        interval_id,
        snapshot_store_id,
        _styles,
        _class_names,
    )

    wizard = build_wizard(
        wizard_id,
        body,
        trigger=trigger,
        title="Export figure",
        header_actions=menu,
        dialog_style=_styles.get("dialog"),
        dialog_class_name=_class_names.get("dialog", ""),
        title_style=_styles.get("title"),
        close_style=_styles.get("close"),
    )
    config.register_populate_callback(wizard.open_input)
    config.register_restore_callback(Input(restore_id, "n_clicks"))

    dash.clientside_callback(
        "function(v) { return v != null && v.length > 0; }",
        Output(generate_id, "disabled"),
        Input(autogenerate_id, "value"),
    )

    @dash.callback(
        Output(interval_id, "disabled"),
        Output(interval_id, "n_intervals"),
        wizard.open_input,
        prevent_initial_call=True,
    )
    def arm_interval(is_open):
        return (not is_open, 0)

    if _has_snapshot:
        _capture_states = [
            State(field_id(config_id, name), "value") for name in _active_capture
        ]
        strip_patches = _build_strip_patches(
            strip_title,
            strip_legend,
            strip_annotations,
            strip_axis_titles,
            strip_colorbar,
            strip_margin,
        )
        capture_js = _build_capture_js(graph_id, _active_capture, strip_patches, params)

        dash.clientside_callback(
            capture_js,
            Output(snapshot_store_id, "data"),
            Input(generate_id, "n_clicks"),
            Input(interval_id, "n_intervals"),
            *_capture_states,
            prevent_initial_call=True,
        )

        _fig_states = [State(graph_id, "figure")] if _has_fig_data else []

        @dash.callback(
            Output(preview_id, "src"),
            Input(snapshot_store_id, "data"),
            *_fig_states,
            *config.states,
            prevent_initial_call=True,
        )
        def generate_preview(_img_b64, *args):
            if not _img_b64:
                return dash.no_update
            if _has_fig_data:
                fig_data, *field_values = args
            else:
                fig_data, field_values = {}, args
            kwargs = config.build_kwargs(tuple(field_values))
            data = _call_renderer(
                renderer, _has_fig_data, True, fig_data, _img_b64, kwargs
            )
            return _to_src(data)

    else:

        @dash.callback(
            Output(preview_id, "src"),
            Input(generate_id, "n_clicks"),
            Input(interval_id, "n_intervals"),
            State(graph_id, "figure"),
            *config.states,
            prevent_initial_call=True,
        )
        def generate_preview(n_clicks, n_intervals, _fig_data, *field_values):
            if not n_clicks and not n_intervals:
                return dash.no_update
            kwargs = config.build_kwargs(field_values)
            data = _call_renderer(renderer, _has_fig_data, False, _fig_data, "", kwargs)
            return _to_src(data)

    @dash.callback(
        Output(preview_id, "src", allow_duplicate=True),
        *[Input(s.component_id, s.component_property) for s in config.states],
        State(autogenerate_id, "value"),
        State(snapshot_store_id, "data"),
        State(graph_id, "figure"),
        prevent_initial_call=True,
    )
    def autogenerate_preview(*args):
        *field_values, autogen, _img_b64, _fig_data = args
        if not autogen:
            return dash.no_update
        if _has_snapshot and not _img_b64:
            return dash.no_update  # capture not yet available
        kwargs = config.build_kwargs(tuple(field_values))
        data = _call_renderer(
            renderer, _has_fig_data, _has_snapshot, _fig_data, _img_b64 or "", kwargs
        )
        return _to_src(data)

    @dash.callback(
        Output(download_id, "data"),
        Input(f"{download_id}_btn", "n_clicks"),
        State(snapshot_store_id, "data"),
        State(graph_id, "figure"),
        *config.states,
        prevent_initial_call=True,
    )
    def download_figure(n_clicks, _img_b64, _fig_data, *field_values):
        kwargs = config.build_kwargs(field_values)
        data = _call_renderer(
            renderer, _has_fig_data, _has_snapshot, _fig_data, _img_b64 or "", kwargs
        )
        return dcc.send_bytes(data, filename)

    return wizard.div


def _get_nested(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
        if data is None:
            return None
    return data
