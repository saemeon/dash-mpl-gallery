# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for make_dbc_field — each Python type produces the right DBC widget."""

from __future__ import annotations

import pathlib
from datetime import date, datetime
from enum import Enum
from typing import Literal

import pytest
from dash import dcc
import dash_bootstrap_components as dbc
from dash_fn_forms import Field, FnForm


class _Color(Enum):
    red = "red"
    green = "green"
    blue = "blue"


# ── helpers ───────────────────────────────────────────────────────────────────


def _form_dbc(fn, **kwargs):
    uid = f"_t_dbc_{fn.__name__}_{id(fn)}"
    kwargs["_field_components"] = "dbc"
    return FnForm(uid, fn, **kwargs)


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


def _find(component, cls):
    return next((c for c in _all_components(component) if isinstance(c, cls)), None)


# ── str → dbc.Input(type="text") ─────────────────────────────────────────────


def test_str_produces_text_input():
    def fn(name: str = "Alice"):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result is not None
    assert isinstance(result, dbc.Input)
    assert result.type == "text"


def test_str_default_value():
    def fn(name: str = "Bob"):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result.value == "Bob"


# ── int → dbc.Input(type="number", step=1) ───────────────────────────────────


def test_int_produces_number_input():
    def fn(count: int = 5):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result is not None
    assert isinstance(result, dbc.Input)
    assert result.type == "number"
    assert result.step == 1


def test_int_default_value():
    def fn(n: int = 42):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result.value == 42


# ── float → dbc.Input(type="number") ─────────────────────────────────────────


def test_float_produces_number_input():
    def fn(x: float = 1.5):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result is not None
    assert isinstance(result, dbc.Input)
    assert result.type == "number"


def test_float_default_value():
    def fn(x: float = 3.14):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result.value == pytest.approx(3.14)


# ── int with bounds → dbc.Input with min/max ─────────────────────────────────


def test_int_with_bounds_sets_min_max():
    def fn(n: int = 5):
        pass

    form = _form_dbc(fn, n=Field(ge=1, le=100))
    result = _find(form, dbc.Input)
    assert result is not None
    assert result.min == 1
    assert result.max == 100


# ── int with slider widget → dcc.Slider ──────────────────────────────────────


def test_int_with_slider_widget_produces_dcc_slider():
    def fn(n: int = 5):
        pass

    form = _form_dbc(fn, n=Field(ge=0, le=10, widget="slider"))
    result = _find(form, dcc.Slider)
    assert result is not None
    assert isinstance(result, dcc.Slider)


def test_slider_respects_min_max_step():
    def fn(x: float = 1.0):
        pass

    form = _form_dbc(fn, x=Field(ge=2.0, le=8.0, step=0.25, widget="slider"))
    result = _find(form, dcc.Slider)
    assert result is not None
    assert result.min == 2.0
    assert result.max == 8.0
    assert result.step == pytest.approx(0.25)


def test_slider_default_value():
    def fn(n: int = 7):
        pass

    form = _form_dbc(fn, n=Field(ge=0, le=10, widget="slider"))
    result = _find(form, dcc.Slider)
    assert result.value == 7


# ── bool → dbc.Checklist ─────────────────────────────────────────────────────


def test_bool_produces_checklist():
    def fn(flag: bool = False):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Checklist)
    assert result is not None
    assert isinstance(result, dbc.Checklist)


def test_bool_true_is_checked():
    def fn(flag: bool = True):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Checklist)
    assert result.value  # non-empty list


def test_bool_false_is_unchecked():
    def fn(flag: bool = False):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Checklist)
    assert result.value == []


def test_bool_checklist_has_options():
    def fn(flag: bool = True):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Checklist)
    assert result.options is not None
    assert len(result.options) > 0


# ── Literal → dbc.Select ─────────────────────────────────────────────────────


def test_literal_produces_dbc_select():
    def fn(mode: Literal["a", "b", "c"] = "a"):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Select)
    assert result is not None
    assert isinstance(result, dbc.Select)


def test_literal_options_contain_values():
    def fn(mode: Literal["x", "y", "z"] = "x"):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Select)
    values = {opt["value"] for opt in result.options}
    assert values == {"x", "y", "z"}


def test_literal_default_selected():
    def fn(mode: Literal["x", "y"] = "y"):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Select)
    assert result.value == "y"


# ── Enum → dbc.Select ────────────────────────────────────────────────────────


def test_enum_produces_dbc_select():
    def fn(color: _Color = _Color.red):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Select)
    assert result is not None
    assert isinstance(result, dbc.Select)


def test_enum_options_contain_member_names():
    def fn(color: _Color = _Color.green):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Select)
    values = {opt["value"] for opt in result.options}
    assert values == {"red", "green", "blue"}


def test_enum_default_selected():
    def fn(color: _Color = _Color.blue):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Select)
    assert result.value == "blue"


# ── list[Literal["a","b"]] → dcc.Dropdown(multi=True) (DBC fallback) ─────────


def test_list_literal_produces_multi_dropdown():
    def fn(tags: list[Literal["a", "b", "c"]] | None = None):
        pass

    form = _form_dbc(fn)
    result = _find(form, dcc.Dropdown)
    assert result is not None
    assert isinstance(result, dcc.Dropdown)
    assert result.multi is True


def test_list_literal_options_contain_values():
    def fn(tags: list[Literal["alpha", "beta"]] | None = None):
        pass

    form = _form_dbc(fn)
    result = _find(form, dcc.Dropdown)
    assert set(result.options) == {"alpha", "beta"}


# ── list[float] → dbc.Input(type="text") ─────────────────────────────────────


def test_list_non_literal_produces_text_input():
    def fn(values: list[float] | None = None):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result is not None
    assert isinstance(result, dbc.Input)
    assert result.type == "text"


# ── path → dbc.Input(type="text") ────────────────────────────────────────────


def test_path_produces_text_input():
    def fn(p: pathlib.Path = pathlib.Path("/tmp")):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result is not None
    assert isinstance(result, dbc.Input)
    assert result.type == "text"


def test_path_default_value():
    def fn(p: pathlib.Path = pathlib.Path("/usr/local")):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Input)
    assert result.value == "/usr/local"


# ── dict → dbc.Textarea ──────────────────────────────────────────────────────


def test_dict_produces_textarea():
    def fn(cfg: dict | None = None):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Textarea)
    assert result is not None
    assert isinstance(result, dbc.Textarea)


def test_dict_with_default_serialized_as_json():
    def fn(cfg: dict = {"key": "val"}):
        pass

    form = _form_dbc(fn)
    result = _find(form, dbc.Textarea)
    import json
    assert json.loads(result.value) == {"key": "val"}


# ── date → dcc.DatePickerSingle (fallback) ───────────────────────────────────


def test_date_falls_back_to_date_picker():
    def fn(d: date | None = None):
        pass

    form = _form_dbc(fn)
    result = _find(form, dcc.DatePickerSingle)
    assert result is not None
    assert isinstance(result, dcc.DatePickerSingle)


def test_date_with_default_value():
    def fn(d: date = date(2024, 6, 15)):
        pass

    form = _form_dbc(fn)
    result = _find(form, dcc.DatePickerSingle)
    assert result.date == "2024-06-15"


# ── datetime → dcc.DatePickerSingle (fallback) ───────────────────────────────


def test_datetime_falls_back_to_date_picker():
    def fn(ts: datetime | None = None):
        pass

    form = _form_dbc(fn)
    result = _find(form, dcc.DatePickerSingle)
    assert result is not None
    assert isinstance(result, dcc.DatePickerSingle)


def test_datetime_with_default_date_part():
    def fn(ts: datetime = datetime(2024, 6, 15, 9, 30)):
        pass

    form = _form_dbc(fn)
    result = _find(form, dcc.DatePickerSingle)
    assert result.date == "2024-06-15"
