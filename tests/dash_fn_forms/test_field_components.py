# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for make_dcc_field — each Python type produces the right Dash widget."""

from __future__ import annotations

import pathlib
from datetime import date, datetime
from enum import Enum
from typing import Literal

import pytest
from dash import dcc
from dash_fn_forms import Field, FnForm


class _Color(Enum):
    red = "red"
    green = "green"
    blue = "blue"


def _form(fn, **kwargs):
    uid = f"_t_{fn.__name__}_{id(fn)}"
    kwargs.setdefault("_field_components", "dcc")
    return FnForm(uid, fn, **kwargs)


def _find(component, cls):
    """Return first component of type cls in the tree, or None."""
    from tests.dash_fn_forms.test_forms import _all_components

    return next((c for c in _all_components(component) if isinstance(c, cls)), None)


# ── str → dcc.Input(type="text") ─────────────────────────────────────────────


def test_str_produces_text_input():
    def fn(name: str = "Alice"):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.type == "text"


def test_str_default_value():
    def fn(name: str = "Bob"):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp.value == "Bob"


# ── int → dcc.Input(type="number", step=1) ───────────────────────────────────


def test_int_produces_number_input():
    def fn(count: int = 5):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.type == "number"
    assert inp.step == 1


def test_int_default_value():
    def fn(n: int = 42):
        pass

    form = _form(fn)
    assert _find(form, dcc.Input).value == 42


def test_int_with_bounds():
    def fn(n: int = 5):
        pass

    form = _form(fn, n=(1, 100, 1))
    inp = _find(form, dcc.Input)
    assert inp.min == 1
    assert inp.max == 100


# ── float → dcc.Input(type="number") ─────────────────────────────────────────


def test_float_produces_number_input():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.type == "number"


def test_float_step_is_any_by_default():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    assert _find(form, dcc.Input).step == "any"


# ── bool → dcc.Checklist ──────────────────────────────────────────────────────


def test_bool_produces_checklist():
    def fn(flag: bool = False):
        pass

    form = _form(fn)
    assert _find(form, dcc.Checklist) is not None


def test_bool_default_true_is_checked():
    def fn(flag: bool = True):
        pass

    form = _form(fn)
    cl = _find(form, dcc.Checklist)
    assert cl.value  # non-empty list = checked


def test_bool_default_false_is_unchecked():
    def fn(flag: bool = False):
        pass

    form = _form(fn)
    cl = _find(form, dcc.Checklist)
    assert cl.value == []


# ── Literal → dcc.Dropdown ────────────────────────────────────────────────────


def test_literal_produces_dropdown():
    def fn(mode: Literal["a", "b", "c"] = "a"):
        pass

    form = _form(fn)
    dd = _find(form, dcc.Dropdown)
    assert dd is not None
    assert set(dd.options) == {"a", "b", "c"}


def test_literal_default_selected():
    def fn(mode: Literal["x", "y"] = "y"):
        pass

    form = _form(fn)
    assert _find(form, dcc.Dropdown).value == "y"


# ── Enum → dcc.Dropdown ───────────────────────────────────────────────────────


def test_enum_produces_dropdown():
    def fn(color: _Color = _Color.red):
        pass

    form = _form(fn)
    dd = _find(form, dcc.Dropdown)
    assert dd is not None
    assert {o["value"] for o in dd.options} == {"red", "green", "blue"}


def test_enum_default_selected():
    def fn(color: _Color = _Color.green):
        pass

    form = _form(fn)
    assert _find(form, dcc.Dropdown).value == "green"


# ── date → dcc.DatePickerSingle ──────────────────────────────────────────────


def test_date_produces_date_picker():
    def fn(d: date | None = None):
        pass

    form = _form(fn)
    assert _find(form, dcc.DatePickerSingle) is not None


def test_date_with_default():
    def fn(d: date = date(2024, 6, 15)):
        pass

    form = _form(fn)
    picker = _find(form, dcc.DatePickerSingle)
    assert picker.date == "2024-06-15"


# ── datetime → DatePickerSingle + time Input ─────────────────────────────────


def test_datetime_produces_date_picker_and_time_input():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    assert _find(form, dcc.DatePickerSingle) is not None
    # There must also be a text Input for the time part
    inputs = [
        c
        for c in _all_components(form)
        if isinstance(c, dcc.Input) and c.type == "text"
    ]
    assert inputs, "expected a text input for the HH:MM time part"


def test_datetime_with_default():
    def fn(ts: datetime = datetime(2024, 6, 15, 9, 30)):
        pass

    form = _form(fn)
    picker = _find(form, dcc.DatePickerSingle)
    assert picker.date == "2024-06-15"
    inputs = [c for c in _all_components(form) if isinstance(c, dcc.Input)]
    time_inputs = [i for i in inputs if getattr(i, "value", None) == "09:30"]
    assert time_inputs


# ── list[T] → dcc.Input (comma-separated) ────────────────────────────────────


def test_list_produces_text_input():
    def fn(values: list[float] | None = None):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.type == "text"


def test_list_literal_produces_multi_dropdown():
    """list[Literal[...]] produces a multi-select dropdown."""
    def fn(tags: list[Literal["a", "b", "c"]] | None = None):
        pass

    form = _form(fn)
    dd = _find(form, dcc.Dropdown)
    assert dd is not None
    assert dd.multi is True


# ── path → dcc.Input(type="text") ────────────────────────────────────────────


def test_path_produces_text_input():
    def fn(p: pathlib.Path = pathlib.Path("/tmp")):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.type == "text"


# ── slider via Field(widget="slider") ────────────────────────────────────────


def test_slider_widget_produces_slider():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(ge=0.0, le=10.0, step=0.5, widget="slider"))
    assert _find(form, dcc.Slider) is not None


def test_slider_respects_min_max_step():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(ge=2.0, le=8.0, step=0.25, widget="slider"))
    s = _find(form, dcc.Slider)
    assert s.min == 2.0
    assert s.max == 8.0
    assert s.step == pytest.approx(0.25)


# ── Field(component=...) override ────────────────────────────────────────────


def test_custom_component_override():
    from dash import dcc as _dcc

    custom = _dcc.RadioItems(options=["a", "b"], value="a", id="custom-radio")

    def fn(mode: str = "a"):
        pass

    form = _form(fn, mode=Field(component=custom))
    assert _find(form, _dcc.RadioItems) is not None


# ── dict type → dcc.Textarea ─────────────────────────────────────────────────


def test_dict_produces_textarea():
    def fn(cfg: dict = {}):  # noqa: B006
        pass

    form = _form(fn)
    ta = _find(form, dcc.Textarea)
    assert ta is not None


def test_dict_default_json_serialized():
    def fn(cfg: dict = {"key": "val"}):  # noqa: B006
        pass

    form = _form(fn)
    ta = _find(form, dcc.Textarea)
    assert '"key"' in (ta.value or "")


# ── tuple type → dcc.Input(type="text") ───────────────────────────────────────


def test_tuple_produces_text_input():
    def fn(coords: tuple = (0, 0)):
        pass

    form = _form(fn)
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.type == "text"


# ── _resolve_field_maker branches ─────────────────────────────────────────────


def test_resolve_field_maker_callable():
    from dash_fn_forms._field_components import _resolve_field_maker, make_dcc_field

    sentinel = make_dcc_field
    result = _resolve_field_maker(sentinel)
    assert result is sentinel


def test_resolve_field_maker_invalid_raises():
    import pytest
    from dash_fn_forms._field_components import _resolve_field_maker

    with pytest.raises(ValueError, match="Unknown"):
        _resolve_field_maker("invalid_maker")


def test_resolve_field_maker_auto_returns_dmc():
    from dash_fn_forms._field_components import _resolve_field_maker, make_dmc_field

    # dmc is installed, so auto should return make_dmc_field
    result = _resolve_field_maker("auto")
    assert result is make_dmc_field


def test_resolve_field_maker_none_returns_dmc():
    from dash_fn_forms._field_components import _resolve_field_maker, make_dmc_field

    result = _resolve_field_maker(None)
    assert result is make_dmc_field


# ── helpers (reused from test_forms) ─────────────────────────────────────────


def _all_components(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        if hasattr(child, "_type"):
            yield from _all_components(child)
