# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Capture pipeline for Dash components.

Three API levels:

- **Low-level**: :class:`CaptureBinding` — wires JS capture → ``dcc.Store``.
  No wizard, no form. User builds their own UI.
- **High-level**: :func:`capture_graph` / :func:`capture_element` — full wizard
  with auto-generated form, live preview, and download.
"""

from __future__ import annotations

import base64
import inspect
import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import dash
from dash import Input, Output, State, dcc, html

from dash_fn_forms import Field, FieldHook, FnForm, FromComponent, field_id
from dash_capture._ids import id_generator
from dash_capture.dropdown import build_dropdown
from dash_capture.strategies import (
    CaptureStrategy,
    build_capture_js,
    html2canvas_strategy,
    plotly_strategy,
)
from dash_capture.wizard import build_wizard


# ---------------------------------------------------------------------------
# FromPlotly hook
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_UNSET: Callable = cast(Callable, object())


def _make_snapshot_fn(img_b64: str) -> Callable[[], bytes]:
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


def _get_nested(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
        if data is None:
            return None
    return data


# ═══════════════════════════════════════════════════════════════════════════
# Low-level API: CaptureBinding
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class CaptureBinding:
    """Low-level capture wiring: JS capture → ``dcc.Store``.

    Place ``.store`` in your layout. Wire ``.arm(trigger_input)`` to start
    the capture. Read the base64 result from ``State(binding.store_id, "data")``.

    Example::

        binding = capture_binding("my-graph")
        app.layout = html.Div([
            dcc.Graph(id="my-graph", figure=fig),
            binding.store,
            html.Button("Capture", id="cap-btn"),
            html.Img(id="preview"),
        ])

        @app.callback(
            Output("preview", "src"),
            Input(binding.store_id, "data"),
            prevent_initial_call=True,
        )
        def show_preview(b64):
            return b64  # data:image/png;base64,...
    """

    store: dcc.Store
    """Place this ``dcc.Store`` in your layout."""

    store_id: str
    """The store's component ID — use in ``State(store_id, "data")``."""

    element_id: str
    """The captured element's DOM ID."""


def capture_binding(
    element: str | Any,
    strategy: CaptureStrategy | None = None,
    trigger: Input | None = None,
) -> CaptureBinding:
    """Create a low-level capture binding.

    Wires the JS capture → ``dcc.Store`` without any wizard or form.
    The user is responsible for placing the store in the layout and
    building their own UI.

    Parameters
    ----------
    element :
        A Dash component with an ``id``, or a string ID.
    strategy :
        Capture strategy. Defaults to ``plotly_strategy()``.
    trigger :
        A Dash ``Input`` that triggers the capture (e.g.
        ``Input("btn", "n_clicks")``). If ``None``, you must wire
        the clientside callback yourself.

    Returns
    -------
    CaptureBinding
        Contains ``.store`` (place in layout) and ``.store_id``.
    """
    el_id = element if isinstance(element, str) else cast(Any, element).id

    if strategy is None:
        strategy = plotly_strategy()

    uid = id_generator(el_id)
    store_id = f"_dcap_store_{uid}"
    store = dcc.Store(id=store_id)

    if trigger is not None:
        capture_js = build_capture_js(el_id, strategy, [], {})
        dash.clientside_callback(
            capture_js,
            Output(store_id, "data"),
            trigger,
            Input(f"_dcap_dummy_{uid}", "n_intervals"),  # unused but required
            prevent_initial_call=True,
        )

    return CaptureBinding(store=store, store_id=store_id, element_id=el_id)


# ═══════════════════════════════════════════════════════════════════════════
# High-level API: capture_graph / capture_element (wizard with form)
# ═══════════════════════════════════════════════════════════════════════════


def _build_modal_body(
    config_div, generate_id, download_id, preview_id,
    interval_id, snapshot_store_id, styles, class_names,
) -> html.Div:
    return html.Div(
        style={"display": "flex", "gap": "24px"},
        children=[
            html.Div(
                style={
                    "display": "flex", "flexDirection": "column",
                    "gap": "8px", "minWidth": "160px",
                },
                children=[
                    config_div,
                    html.Button(
                        "Generate", id=generate_id,
                        style=styles.get("button"),
                        className=class_names.get("button", ""),
                    ),
                    dcc.Download(id=download_id),
                    html.Button(
                        "Download", id=f"{download_id}_btn",
                        style=styles.get("button"),
                        className=class_names.get("button", ""),
                    ),
                ],
            ),
            html.Div(
                style={"position": "relative", "width": "400px", "height": "300px"},
                children=[dcc.Loading(
                    type="circle",
                    children=[html.Img(id=preview_id, style={"maxWidth": "400px"})],
                )],
            ),
            dcc.Interval(
                id=interval_id, interval=500,
                n_intervals=0, max_intervals=1, disabled=True,
            ),
            dcc.Store(id=snapshot_store_id),
        ],
    )


def _wire_wizard(
    *,
    element_id: str,
    strategy: CaptureStrategy,
    renderer: Callable,
    config: FnForm,
    has_snapshot: bool,
    has_fig_data: bool,
    active_capture: list[str],
    params: dict,
    ids: dict[str, str],
    trigger: str | Any,
    filename: str,
    autogenerate: bool,
    styles: dict,
    class_names: dict,
) -> html.Div:
    """Wire the full wizard: modal + capture JS + preview/download callbacks."""
    config_id = ids["cfg"]
    wizard_id = ids["wiz"]
    preview_id = ids["preview"]
    generate_id = ids["generate"]
    download_id = ids["download"]
    interval_id = ids["interval"]
    restore_id = ids["restore"]
    menu_id = ids["menu"]
    autogenerate_id = ids["autogen"]
    snapshot_store_id = ids["snapshot"]

    menu = build_dropdown(
        menu_id,
        trigger_label="···",
        close_inputs=[Input(restore_id, "n_clicks")],
        styles=styles, class_names=class_names,
        children=[
            html.Button(
                "Reset to defaults", id=restore_id,
                style=styles.get("button"),
                className=class_names.get("button", ""),
            ),
            dcc.Checklist(
                id=autogenerate_id,
                options=[{"label": " Auto-generate", "value": "auto"}],
                value=["auto"] if autogenerate else [],
                style={"padding": "4px 8px"},
                labelStyle={
                    k: v for k, v in (styles.get("label") or {}).items()
                    if k == "color"
                },
            ),
        ],
    )

    body = _build_modal_body(
        config, generate_id, download_id, preview_id,
        interval_id, snapshot_store_id, styles, class_names,
    )

    wizard = build_wizard(
        wizard_id, body, trigger=trigger, title="Capture",
        header_actions=menu,
        dialog_style=styles.get("dialog"),
        dialog_class_name=class_names.get("dialog", ""),
        title_style=styles.get("title"),
        close_style=styles.get("close"),
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

    if has_snapshot:
        _capture_states = [
            State(field_id(config_id, name), "value") for name in active_capture
        ]
        capture_js = build_capture_js(element_id, strategy, active_capture, params)

        dash.clientside_callback(
            capture_js,
            Output(snapshot_store_id, "data"),
            Input(generate_id, "n_clicks"),
            Input(interval_id, "n_intervals"),
            *_capture_states,
            prevent_initial_call=True,
        )

        _fig_states = [State(element_id, "figure")] if has_fig_data else []

        @dash.callback(
            Output(preview_id, "src"),
            Input(snapshot_store_id, "data"),
            *_fig_states, *config.states,
            prevent_initial_call=True,
        )
        def generate_preview(_img_b64, *args):
            if not _img_b64:
                return dash.no_update
            if has_fig_data:
                fig_data, *field_values = args
            else:
                fig_data, field_values = {}, args
            kwargs = config.build_kwargs(tuple(field_values))
            return _to_src(_call_renderer(
                renderer, has_fig_data, True, fig_data, _img_b64, kwargs
            ))
    else:
        _fig_states2 = [State(element_id, "figure")] if has_fig_data else []

        @dash.callback(
            Output(preview_id, "src"),
            Input(generate_id, "n_clicks"),
            Input(interval_id, "n_intervals"),
            *_fig_states2,
            *config.states,
            prevent_initial_call=True,
        )
        def generate_preview(n_clicks, n_intervals, *args):
            if not n_clicks and not n_intervals:
                return dash.no_update
            if has_fig_data:
                _fig_data, *field_values = args
            else:
                _fig_data, field_values = {}, args
            kwargs = config.build_kwargs(tuple(field_values))
            return _to_src(_call_renderer(
                renderer, has_fig_data, False, _fig_data, "", kwargs
            ))

    _fig_states_ag = [State(element_id, "figure")] if has_fig_data else []

    if config.states:
        @dash.callback(
            Output(preview_id, "src", allow_duplicate=True),
            *[Input(s.component_id, s.component_property) for s in config.states],
            State(autogenerate_id, "value"),
            State(snapshot_store_id, "data"),
            *_fig_states_ag,
            prevent_initial_call=True,
        )
        def autogenerate_preview(*args):
            if has_fig_data:
                *field_values, autogen, _img_b64, _fig_data = args
            else:
                *field_values, autogen, _img_b64 = args
                _fig_data = {}
            if not autogen:
                return dash.no_update
            if has_snapshot and not _img_b64:
                return dash.no_update
            kwargs = config.build_kwargs(tuple(field_values))
            return _to_src(_call_renderer(
                renderer, has_fig_data, has_snapshot, _fig_data, _img_b64 or "", kwargs
            ))

    _fig_states_dl = [State(element_id, "figure")] if has_fig_data else []

    @dash.callback(
        Output(download_id, "data"),
        Input(f"{download_id}_btn", "n_clicks"),
        State(snapshot_store_id, "data"),
        *_fig_states_dl,
        *config.states,
        prevent_initial_call=True,
    )
    def download_figure(n_clicks, _img_b64, *args):
        if has_fig_data:
            _fig_data, *field_values = args
        else:
            _fig_data, field_values = {}, args
        kwargs = config.build_kwargs(tuple(field_values))
        return dcc.send_bytes(
            _call_renderer(
                renderer, has_fig_data, has_snapshot, _fig_data, _img_b64 or "", kwargs
            ),
            filename,
        )

    return wizard.div


def _make_wizard(
    element_id: str,
    renderer: Callable,
    strategy: CaptureStrategy,
    preprocess: str | None,
    trigger: str | Any,
    filename: str,
    autogenerate: bool,
    styles: dict | None,
    class_names: dict | None,
    field_specs: dict[str, Field | FieldHook] | None,
    field_components: Any,
) -> html.Div:
    """Shared implementation for capture_graph and capture_element."""
    if preprocess is not None:
        strategy = CaptureStrategy(preprocess=preprocess, capture=strategy.capture)

    params = inspect.signature(renderer).parameters
    has_snapshot = "_snapshot_img" in params
    has_fig_data = "_fig_data" in params
    active_capture = [name for name in params if name.startswith("capture_")]
    exclude = ["_target", "_snapshot_img", "_fig_data", *active_capture]

    _styles = styles or {}
    _class_names = class_names or {}

    uid = id_generator(element_id)
    ids = {k: f"_dcap_{k}_{uid}" for k in (
        "cfg", "wiz", "preview", "generate", "download",
        "interval", "restore", "menu", "autogen", "snapshot",
    )}

    config = FnForm(
        ids["cfg"], renderer,
        _styles=_styles, _class_names=_class_names,
        _field_specs=field_specs, _show_docstring=False,
        _exclude=exclude, _field_components=field_components,
    )

    return _wire_wizard(
        element_id=element_id, strategy=strategy, renderer=renderer,
        config=config, has_snapshot=has_snapshot, has_fig_data=has_fig_data,
        active_capture=active_capture, params=params, ids=ids,
        trigger=trigger, filename=filename, autogenerate=autogenerate,
        styles=_styles, class_names=_class_names,
    )


# ---------------------------------------------------------------------------
# Public high-level API
# ---------------------------------------------------------------------------


def capture_graph(
    graph: str | dcc.Graph,
    renderer: Callable = _UNSET,
    trigger: str | Any = "Capture",
    strip_title: bool = False,
    strip_legend: bool = False,
    strip_annotations: bool = False,
    strip_axis_titles: bool = False,
    strip_colorbar: bool = False,
    strip_margin: bool = False,
    strategy: CaptureStrategy | None = None,
    preprocess: str | None = None,
    filename: str = "figure.png",
    autogenerate: bool = False,
    styles: dict | None = None,
    class_names: dict | None = None,
    field_specs: dict[str, Field | FieldHook] | None = None,
    field_components: Any = "dcc",
) -> html.Div:
    """Capture wizard for a ``dcc.Graph``.

    Renders a trigger button that opens a wizard modal with live preview,
    auto-generated form fields from the renderer's signature, and a
    download button.

    Parameters
    ----------
    graph :
        The ``dcc.Graph`` component or its string ``id``.
    renderer :
        Callable with signature
        ``(_target, [_fig_data], [_snapshot_img], **fields)``.
        Defaults to :func:`dash_capture.mpl.snapshot_renderer`.
    trigger :
        String label or custom Dash component with ``n_clicks``.
    strip_title, strip_legend, strip_annotations, strip_axis_titles,
    strip_colorbar, strip_margin :
        Remove the corresponding Plotly element before capture.
        Ignored when ``strategy`` is explicitly provided.
    strategy :
        A :class:`CaptureStrategy` overriding the built-in Plotly strategy.
    preprocess :
        Custom JS preprocess code, overriding the strategy's default.
        **Security:** This executes as JavaScript in the browser.
        Never pass untrusted user input here.
    filename :
        Download filename. Defaults to ``"figure.png"``.
    field_components :
        Component factory for form fields: ``"dcc"`` (default),
        ``"dmc"`` (Mantine), ``"dbc"`` (Bootstrap), or a custom callable.
    """
    if renderer is _UNSET:
        from dash_capture.mpl import snapshot_renderer
        renderer = snapshot_renderer

    graph_id = graph if isinstance(graph, str) else cast(Any, graph).id

    if strategy is None:
        params = inspect.signature(renderer).parameters
        strategy = plotly_strategy(
            strip_title=strip_title, strip_legend=strip_legend,
            strip_annotations=strip_annotations, strip_axis_titles=strip_axis_titles,
            strip_colorbar=strip_colorbar, strip_margin=strip_margin,
            _params=params,
        )

    return _make_wizard(
        graph_id, renderer, strategy, preprocess, trigger, filename,
        autogenerate, styles, class_names, field_specs, field_components,
    )


def capture_element(
    component: str | Any,
    renderer: Callable = _UNSET,
    trigger: str | Any = "Capture",
    strategy: CaptureStrategy | None = None,
    preprocess: str | None = None,
    filename: str = "capture.png",
    autogenerate: bool = False,
    styles: dict | None = None,
    class_names: dict | None = None,
    field_specs: dict[str, Field | FieldHook] | None = None,
    field_components: Any = "dcc",
) -> html.Div:
    """Capture wizard for any Dash component.

    Uses ``html2canvas`` by default. Requires html2canvas to be loaded
    (e.g. via ``app.scripts``).

    Parameters
    ----------
    component :
        Any Dash component with an ``id``, or a string ID.
    renderer :
        Callable with signature ``(_target, _snapshot_img, **fields)``.
        Defaults to :func:`dash_capture.mpl.snapshot_renderer`.
    field_components :
        Component factory: ``"dcc"`` (default), ``"dmc"``, ``"dbc"``,
        or a custom callable.
    """
    if renderer is _UNSET:
        from dash_capture.mpl import snapshot_renderer
        renderer = snapshot_renderer

    comp_id = component if isinstance(component, str) else cast(Any, component).id

    if strategy is None:
        strategy = html2canvas_strategy()

    return _make_wizard(
        comp_id, renderer, strategy, preprocess, trigger, filename,
        autogenerate, styles, class_names, field_specs, field_components,
    )


# Backwards compatibility aliases
graph_exporter = capture_graph
component_exporter = capture_element
