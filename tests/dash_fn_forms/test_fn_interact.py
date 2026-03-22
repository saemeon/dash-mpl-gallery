# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for build_fn_panel and FnPanel."""

from __future__ import annotations

from dash import dcc, html
from dash_fn_forms import FnForm
from dash_fn_forms.fn_interact import FnPanel, _cached_caller, build_fn_panel


def _panel(fn, **kwargs):
    uid = f"_t_{fn.__name__}_{id(fn)}"
    return build_fn_panel(fn, _id=uid, **kwargs)


# ── FnPanel structure ─────────────────────────────────────────────────────────


def test_build_fn_panel_returns_fn_panel():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn)
    assert isinstance(panel, FnPanel)


def test_fn_panel_form_is_fn_form():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn)
    assert isinstance(panel.form, FnForm)


def test_fn_panel_output_is_div():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn)
    assert isinstance(panel.output, html.Div)


def test_fn_panel_output_has_id():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn)
    assert panel.output.id is not None


def test_fn_panel_form_and_output_are_distinct():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn)
    assert panel.form is not panel.output
    assert type(panel.form).__name__ == "FnForm"
    assert panel.output.id is not None


# ── loading wrapper ───────────────────────────────────────────────────────────


def test_loading_true_wraps_output():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn, _loading=True)

    def _has_loading(comp):
        if isinstance(comp, dcc.Loading):
            return True
        for child in getattr(comp, "children", None) or []:
            if isinstance(child, list):
                if any(_has_loading(c) for c in child):
                    return True
            elif hasattr(child, "_type") and _has_loading(child):
                return True
        return False

    assert _has_loading(panel)


def test_loading_false_no_loading_wrapper():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn, _loading=False)

    def _has_loading(comp):
        if isinstance(comp, dcc.Loading):
            return True
        for child in getattr(comp, "children", None) or []:
            if isinstance(child, list):
                if any(_has_loading(c) for c in child):
                    return True
            elif hasattr(child, "_type") and _has_loading(child):
                return True
        return False

    assert not _has_loading(panel)


# ── manual mode ───────────────────────────────────────────────────────────────


def test_manual_mode_has_apply_button():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn, _manual=True)

    def _has_button(comp):
        if isinstance(comp, html.Button):
            return True
        for child in getattr(comp, "children", None) or []:
            if isinstance(child, list):
                if any(_has_button(c) for c in child):
                    return True
            elif hasattr(child, "_type") and _has_button(child):
                return True
        return False

    assert _has_button(panel)


def test_auto_mode_has_no_apply_button():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn, _manual=False)

    def _has_button(comp):
        if isinstance(comp, html.Button):
            return True
        for child in getattr(comp, "children", None) or []:
            if isinstance(child, list):
                if any(_has_button(c) for c in child):
                    return True
            elif hasattr(child, "_type") and _has_button(child):
                return True
        return False

    assert not _has_button(panel)


# ── caching ───────────────────────────────────────────────────────────────────


def test_cached_caller_reuses_result():
    call_count = [0]

    def fn(x: float = 1.0):
        call_count[0] += 1
        return x * 2

    uid = f"_t_cache_{id(fn)}"
    cfg = FnForm(uid, fn)
    caller = _cached_caller(fn, cfg, maxsize=128)

    caller(1.0)
    caller(1.0)  # same values — should hit cache
    caller(2.0)  # different value — new call

    assert call_count[0] == 2


def test_cached_caller_different_values_not_cached():
    call_count = [0]

    def fn(x: float = 1.0):
        call_count[0] += 1
        return x

    uid = f"_t_cache2_{id(fn)}"
    cfg = FnForm(uid, fn)
    caller = _cached_caller(fn, cfg, maxsize=128)

    caller(1.0)
    caller(2.0)
    caller(3.0)

    assert call_count[0] == 3


def test_cached_caller_bool_list_values():
    """Checkbox values are lists — _make_hashable must handle them."""
    call_count = [0]

    def fn(flag: bool = False):
        call_count[0] += 1
        return flag

    uid = f"_t_cache3_{id(fn)}"
    cfg = FnForm(uid, fn)
    caller = _cached_caller(fn, cfg, maxsize=128)

    caller([])       # unchecked
    caller([])       # same — cached
    caller(["flag"]) # checked — new call

    assert call_count[0] == 2


def test_build_fn_panel_cache_false_by_default():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn)
    assert isinstance(panel, FnPanel)  # builds without error, cache=False is default


def test_build_fn_panel_cache_true():
    def fn(x: float = 1.0):
        pass

    panel = _panel(fn, _cache=True)
    assert isinstance(panel, FnPanel)


# ── _make_hashable ────────────────────────────────────────────────────────────


def test_make_hashable_scalar_passthrough():
    from dash_fn_forms.fn_interact import _make_hashable

    assert _make_hashable(42) == 42
    assert _make_hashable("hello") == "hello"
    assert _make_hashable(None) is None
    assert _make_hashable(3.14) == 3.14


def test_make_hashable_list_becomes_tuple():
    from dash_fn_forms.fn_interact import _make_hashable

    result = _make_hashable([1, 2, 3])
    assert result == (1, 2, 3)
    assert isinstance(result, tuple)


def test_make_hashable_nested_list():
    from dash_fn_forms.fn_interact import _make_hashable

    result = _make_hashable([["a", "b"], "c"])
    assert result == (("a", "b"), "c")


def test_make_hashable_empty_list():
    from dash_fn_forms.fn_interact import _make_hashable

    assert _make_hashable([]) == ()


# ── FnPanel.compute ───────────────────────────────────────────────────────────


def test_compute_returns_rendered_result():
    def fn(x: float = 1.0):
        return x * 2

    panel = _panel(fn)
    result = panel.compute(3.0)
    # 6.0 → html.P
    assert isinstance(result, html.P)


def test_compute_renders_string_as_markdown():
    def fn(name: str = "world"):
        return f"Hello **{name}**"

    from dash import dcc as _dcc

    panel = _panel(fn)
    result = panel.compute("Alice")
    assert isinstance(result, _dcc.Markdown)


def test_compute_exception_returns_error_pre():
    def fn(x: float = 1.0):
        raise ValueError("bad input")

    panel = _panel(fn)
    result = panel.compute(1.0)
    assert isinstance(result, html.Pre)
    assert "bad input" in str(result.children)


def test_compute_with_cache():
    call_count = [0]

    def fn(x: float = 1.0):
        call_count[0] += 1
        return x

    panel = _panel(fn, _cache=True)
    panel.compute(5.0)
    panel.compute(5.0)  # cached
    assert call_count[0] == 1


def test_compute_custom_renderer():
    from dash import html as _html

    def fn(x: float = 1.0):
        return x

    panel = build_fn_panel(fn, _id=f"_t_render_{id(fn)}", _render=lambda v: _html.H2(str(v)))
    result = panel.compute(42.0)
    assert isinstance(result, _html.H2)


# ── _cached_caller TypeError fallback ─────────────────────────────────────────


def test_cached_caller_unhashable_falls_back_to_direct_call():
    """Values that can't be hashed (e.g. dicts) fall back to direct fn call."""
    call_count = [0]

    def fn(x: float = 1.0):
        call_count[0] += 1
        return x

    uid = f"_t_cache_fallback_{id(fn)}"
    cfg = FnForm(uid, fn)
    caller = _cached_caller(fn, cfg, maxsize=128)

    # Patch _make_hashable to raise TypeError to simulate unhashable
    import dash_fn_forms.fn_interact as _fi
    original = _fi._make_hashable

    def _raise(_):
        raise TypeError("not hashable")

    _fi._make_hashable = _raise
    try:
        caller(1.0)
        caller(1.0)
    finally:
        _fi._make_hashable = original

    # Both calls went through (no caching due to TypeError fallback)
    assert call_count[0] == 2
