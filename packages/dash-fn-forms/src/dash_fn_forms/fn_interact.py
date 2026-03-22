# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Build self-contained interactive panels from typed callables."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from dash import Input, Output, State, callback, dcc, html

from dash_fn_forms._forms import FnForm
from dash_fn_forms._renderers import to_component


class FnPanel(html.Div):
    """An interactive panel returned by :func:`build_fn_panel`.

    Subclass of ``html.Div`` — embed it anywhere in a Dash layout.
    Exposes the form and output sub-components as named attributes for
    split-layout use cases::

        panel = build_fn_panel(fn)
        app.layout = html.Div([
            html.Div([panel.form], className="sidebar"),
            html.Div([panel.output], className="main"),
        ])
    """

    def __init__(
        self,
        children: list[Any],
        *,
        form: FnForm,
        output: html.Div,
        fn: Callable,
        cfg: FnForm,
        call: Callable[..., Any] | None,
        render: Callable[[Any], Any] | None,
    ) -> None:
        self._form = form
        self._output = output
        self._fn = fn
        self._cfg = cfg
        self._call = call
        self._render = render
        super().__init__(children)

    @property
    def form(self) -> FnForm:
        """The form controls sub-component."""
        return self._form

    @property
    def output(self) -> html.Div:
        """The output area sub-component (unwrapped from ``dcc.Loading``)."""
        return self._output

    def compute(self, *values: Any) -> Any:
        """Run the wrapped function with *values* from the form fields.

        Returns the ``to_component``-rendered result, or an error ``html.Pre``
        if the function raises.  This is the same logic as the Dash callback —
        calling it directly enables unit testing without a running Dash app::

            panel = build_fn_panel(fn, _id="test")
            result = panel.compute(3.14, 2)
            assert isinstance(result, html.P)
        """
        try:
            result = (
                self._call(*values)
                if self._call is not None
                else self._fn(**self._cfg.build_kwargs(values))
            )
        except Exception as exc:
            return html.Pre(
                f"Error: {exc}",
                style={"color": "#d9534f", "fontFamily": "monospace"},
            )
        return to_component(result, self._render)


def _make_hashable(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_make_hashable(x) for x in v)
    return v


def _cached_caller(
    fn: Callable, cfg: FnForm, maxsize: int
) -> Callable[..., Any]:
    """Return a wrapper around fn that memoises by the raw Dash values tuple."""

    @functools.lru_cache(maxsize=maxsize)
    def _inner(*hashed: Any) -> Any:
        return fn(**cfg.build_kwargs(hashed))

    def _call(*values: Any) -> Any:
        try:
            return _inner(*(_make_hashable(v) for v in values))
        except TypeError:
            return fn(**cfg.build_kwargs(values))

    return _call


def build_fn_panel(
    fn: Callable,
    *,
    _id: str | None = None,
    _manual: bool = False,
    _loading: bool = True,
    _render: Callable[[Any], Any] | None = None,
    _cache: bool = False,
    _cache_maxsize: int = 128,
    **kwargs: Any,
) -> FnPanel:
    """Build and return a self-contained interactive panel.

    Registers Dash callbacks and returns an ``html.Div``.  Has no knowledge
    of pages; the caller is responsible for placing the panel in a layout.

    Parameters
    ----------
    fn :
        Callable whose parameters define the form fields.
    _id :
        Explicit component-ID namespace.  Defaults to ``fn.__name__``.
        Pass a unique string when two panels wrap functions with the same name
        to prevent Dash component-ID collisions.
    _manual :
        ``False`` — live update on every field change.
        ``True`` — *Apply* button; callback fires on click only.
    _loading :
        Wrap the output area in ``dcc.Loading`` (default ``True``).
    _render :
        Optional converter applied to *fn*'s return value before display.
    _cache :
        Cache function call results by input values (default ``False``).
        Skips re-calling *fn* when the same field values are submitted again.
    _cache_maxsize :
        Maximum number of cached results (LRU eviction).  Default ``128``.
    **kwargs :
        Per-field shorthands forwarded to :class:`FnForm`.
    """
    config_id = _id or getattr(fn, "__name__", repr(fn))
    output_id = f"_dft_interact_out_{config_id}"

    cfg: FnForm = FnForm(config_id, fn, **kwargs)
    _call = _cached_caller(fn, cfg, _cache_maxsize) if _cache else None

    _inner = html.Div(id=output_id, style={"marginTop": "16px"})
    output_div = dcc.Loading(_inner, type="circle") if _loading else _inner

    _panel_kwargs: dict[str, Any] = {
        "form": cfg,
        "output": _inner,
        "fn": fn,
        "cfg": cfg,
        "call": _call,
        "render": _render,
    }

    if _manual:
        btn_id = f"_dft_interact_btn_{config_id}"

        panel = FnPanel(
            [
                cfg,
                html.Button(
                    "Apply",
                    id=btn_id,
                    n_clicks=0,
                    style={
                        "marginTop": "8px",
                        "padding": "6px 16px",
                        "cursor": "pointer",
                    },
                ),
                output_div,
            ],
            **_panel_kwargs,
        )

        @callback(
            Output(output_id, "children"),
            Input(btn_id, "n_clicks"),
            *cfg.states,
            prevent_initial_call=True,
        )
        def _on_apply(_n: int, *values: Any) -> Any:
            return panel.compute(*values)

        return panel

    else:
        cfg_states: list[State] = object.__getattribute__(cfg, "states")
        inputs = [Input(s.component_id, s.component_property) for s in cfg_states]

        panel = FnPanel([cfg, output_div], **_panel_kwargs)

        @callback(Output(output_id, "children"), *inputs)
        def _on_change(*values: Any) -> Any:
            return panel.compute(*values)

        return panel
