# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for the to_component rendering pipeline."""

from __future__ import annotations

from dash import dcc, html
from dash_fn_forms._renderers import register_renderer, to_component

# ── built-ins ─────────────────────────────────────────────────────────────────


def test_none_returns_none():
    assert to_component(None, None) is None


def test_str_returns_markdown():
    result = to_component("hello **world**", None)
    assert isinstance(result, dcc.Markdown)


def test_int_returns_p():
    result = to_component(42, None)
    assert isinstance(result, html.P)


def test_float_returns_p():
    result = to_component(3.14, None)
    assert isinstance(result, html.P)


def test_bool_returns_p():
    result = to_component(True, None)
    assert isinstance(result, html.P)


def test_dash_component_returned_as_is():
    comp = html.Div("content")
    result = to_component(comp, None)
    assert result is comp


def test_plotly_figure_returns_graph():
    import plotly.graph_objects as go

    fig = go.Figure()
    result = to_component(fig, None)
    assert isinstance(result, dcc.Graph)


def test_matplotlib_figure_returns_img():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    result = to_component(fig, None)
    plt.close(fig)
    assert isinstance(result, html.Img)
    assert result.src.startswith("data:image/png;base64,")


def test_pandas_dataframe_returns_table():
    import pandas as pd
    from dash import dash_table

    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    result = to_component(df, None)
    assert isinstance(result, dash_table.DataTable)


def test_unknown_type_returns_pre():
    class Weird:
        def __repr__(self):
            return "weird!"

    result = to_component(Weird(), None)
    assert isinstance(result, html.Pre)


# ── explicit renderer ─────────────────────────────────────────────────────────


def test_explicit_renderer_takes_priority():
    custom = html.Span("custom")
    result = to_component("any string", lambda _: custom)
    assert result is custom


def test_explicit_renderer_error_shows_error_component():
    def bad_renderer(_):
        raise ValueError("oops")

    result = to_component("x", bad_renderer)
    # Should return some error component, not raise
    assert result is not None


# ── global registry ───────────────────────────────────────────────────────────


def test_register_renderer_used_for_type():
    class MyType:
        pass

    register_renderer(MyType, lambda _: html.Span("registered"))
    result = to_component(MyType(), None)
    assert isinstance(result, html.Span)
    assert result.children == "registered"


def test_explicit_renderer_overrides_registry():
    class MyType:
        pass

    register_renderer(MyType, lambda _: html.Span("from registry"))
    override = html.B("override")
    result = to_component(MyType(), lambda _: override)
    assert result is override


def test_registry_checked_before_builtins():
    # Register a renderer for str — should beat the built-in str → Markdown
    register_renderer(str, lambda s: html.H1(s))
    result = to_component("hi", None)
    assert isinstance(result, html.H1)


# ── dict rendering ────────────────────────────────────────────────────────────


def test_dict_returns_div():
    result = to_component({"a": 1, "b": 2}, None)
    assert isinstance(result, html.Div)


def test_dict_empty_returns_div():
    result = to_component({}, None)
    assert isinstance(result, html.Div)
    assert result.children == []


def test_dict_keys_appear_as_labels():
    result = to_component({"mean": 3.14, "std": 0.5}, None)
    json_str = str(result.to_plotly_json())
    assert "mean" in json_str
    assert "std" in json_str


def test_dict_values_rendered_recursively():
    result = to_component({"msg": "hello **world**"}, None)
    # The string value should be rendered as Markdown somewhere in the tree
    json_str = str(result.to_plotly_json())
    assert "Markdown" in json_str


def test_dict_values_can_be_mixed_types():
    result = to_component({"n": 42, "text": "hi", "flag": True}, None)
    assert isinstance(result, html.Div)
    assert len(result.children) == 3


# ── dict scalar vs rich branching ────────────────────────────────────────────


def test_dict_scalar_value_rendered_inline():
    """str/int/float/bool values → html.P or dcc.Markdown, rendered inline."""
    result = to_component({"score": 42}, None)
    # The int should become html.P inside the card
    json_str = str(result.to_plotly_json())
    assert "42" in json_str


def test_dict_figure_value_rendered_as_graph():
    import plotly.graph_objects as go

    fig = go.Figure()
    result = to_component({"chart": fig}, None)
    json_str = str(result.to_plotly_json())
    assert "Graph" in json_str


# ── _error helper ────────────────────────────────────────────────────────────


def test_error_returns_pre():
    from dash_fn_forms._renderers import _error

    result = _error("something went wrong")
    assert isinstance(result, html.Pre)
    assert "something went wrong" in str(result.children)
    assert result.style["color"] == "#d9534f"


def test_explicit_renderer_error_is_pre():
    """Renderer exception produces an error Pre, not a crash."""
    result = to_component("data", lambda _: 1 / 0)
    assert isinstance(result, html.Pre)


# ── None passthrough ──────────────────────────────────────────────────────────


def test_dict_with_none_value():
    """None values inside a dict are handled (to_component(None) → None)."""
    result = to_component({"empty": None}, None)
    assert isinstance(result, html.Div)
    assert len(result.children) == 1
