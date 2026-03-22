# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for make_dmc_field — each Python type produces the right DMC widget."""

from __future__ import annotations

import pathlib
from datetime import date
from enum import Enum
from typing import Literal

import pytest
from dash import dcc
import dash_mantine_components as dmc
from dash_fn_forms import Field, FnForm


class _Color(Enum):
    red = "red"
    green = "green"
    blue = "blue"


# ── helpers ───────────────────────────────────────────────────────────────────


def _form_dmc(fn, **kwargs):
    uid = f"_t_dmc_{fn.__name__}_{id(fn)}"
    kwargs["_field_components"] = "dmc"
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


# ── str → dmc.TextInput ───────────────────────────────────────────────────────


def test_str_produces_text_input():
    def fn(name: str = "Alice"):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.TextInput)
    assert result is not None
    assert isinstance(result, dmc.TextInput)


def test_str_default_value():
    def fn(name: str = "Bob"):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.TextInput)
    assert result.value == "Bob"


# ── int → dmc.NumberInput with step=1 ────────────────────────────────────────


def test_int_produces_number_input():
    def fn(count: int = 5):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.NumberInput)
    assert result is not None
    assert isinstance(result, dmc.NumberInput)
    assert result.step == 1


def test_int_default_value():
    def fn(n: int = 42):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.NumberInput)
    assert result.value == 42


# ── float → dmc.NumberInput ───────────────────────────────────────────────────


def test_float_produces_number_input():
    def fn(x: float = 1.5):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.NumberInput)
    assert result is not None
    assert isinstance(result, dmc.NumberInput)


def test_float_default_value():
    def fn(x: float = 3.14):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.NumberInput)
    assert result.value == pytest.approx(3.14)


# ── int with bounds (ge/le) → dmc.NumberInput with min/max ───────────────────


def test_int_with_bounds_sets_min_max():
    def fn(n: int = 5):
        pass

    form = _form_dmc(fn, n=Field(ge=1, le=100))
    result = _find(form, dmc.NumberInput)
    assert result is not None
    assert result.min == 1
    assert result.max == 100


# ── int with slider widget → dmc.Slider ──────────────────────────────────────


def test_int_with_slider_widget_produces_slider():
    def fn(n: int = 5):
        pass

    form = _form_dmc(fn, n=Field(ge=0, le=10, widget="slider"))
    result = _find(form, dmc.Slider)
    assert result is not None
    assert isinstance(result, dmc.Slider)


# ── float with slider → dmc.Slider, respects min/max/step ───────────────────


def test_float_slider_respects_min_max_step():
    def fn(x: float = 1.0):
        pass

    form = _form_dmc(fn, x=Field(ge=0.0, le=5.0, step=0.5, widget="slider"))
    result = _find(form, dmc.Slider)
    assert result is not None
    assert isinstance(result, dmc.Slider)
    assert result.min == 0.0
    assert result.max == 5.0
    assert result.step == pytest.approx(0.5)


def test_float_slider_default_value():
    def fn(x: float = 2.5):
        pass

    form = _form_dmc(fn, x=Field(ge=0.0, le=10.0, widget="slider"))
    result = _find(form, dmc.Slider)
    assert result.value == pytest.approx(2.5)


# ── Literal[str] → dmc.Select ────────────────────────────────────────────────


def test_literal_str_produces_select():
    def fn(mode: Literal["a", "b", "c"] = "a"):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Select)
    assert result is not None
    assert isinstance(result, dmc.Select)


def test_literal_str_data_contains_options():
    def fn(mode: Literal["x", "y", "z"] = "x"):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Select)
    assert set(result.data) == {"x", "y", "z"}


def test_literal_str_default_selected():
    def fn(mode: Literal["x", "y"] = "y"):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Select)
    assert result.value == "y"


# ── Literal[int] (non-str) → falls back to dcc.Dropdown ─────────────────────


def test_literal_int_falls_back_to_dcc_dropdown():
    # Need Optional so default=None doesn't trigger int inference
    def fn(n: Literal[1, 2, 3] | None = None):
        pass

    form = _form_dmc(fn)
    result = _find(form, dcc.Dropdown)
    assert result is not None
    assert isinstance(result, dcc.Dropdown)


# ── Enum → dmc.Select ────────────────────────────────────────────────────────


def test_enum_produces_dmc_select():
    def fn(color: _Color = _Color.red):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Select)
    assert result is not None
    assert isinstance(result, dmc.Select)


def test_enum_data_contains_member_names():
    def fn(color: _Color = _Color.green):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Select)
    values = {item["value"] for item in result.data}
    assert values == {"red", "green", "blue"}


def test_enum_default_selected():
    def fn(color: _Color = _Color.green):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Select)
    assert result.value == "green"


# ── bool → dcc.Checklist (fallback) ──────────────────────────────────────────


def test_bool_falls_back_to_dcc_checklist():
    def fn(flag: bool = False):
        pass

    form = _form_dmc(fn)
    result = _find(form, dcc.Checklist)
    assert result is not None
    assert isinstance(result, dcc.Checklist)


def test_bool_true_is_checked():
    def fn(flag: bool = True):
        pass

    form = _form_dmc(fn)
    result = _find(form, dcc.Checklist)
    assert result.value  # non-empty list


def test_bool_false_is_unchecked():
    def fn(flag: bool = False):
        pass

    form = _form_dmc(fn)
    result = _find(form, dcc.Checklist)
    assert result.value == []


# ── date → dcc.DatePickerSingle (fallback) ───────────────────────────────────


def test_date_falls_back_to_date_picker():
    def fn(d: date | None = None):
        pass

    form = _form_dmc(fn)
    result = _find(form, dcc.DatePickerSingle)
    assert result is not None
    assert isinstance(result, dcc.DatePickerSingle)


def test_date_with_default_value():
    def fn(d: date = date(2024, 6, 15)):
        pass

    form = _form_dmc(fn)
    result = _find(form, dcc.DatePickerSingle)
    assert result.date == "2024-06-15"


# ── list[float] → dmc.TextInput (falls through) ──────────────────────────────


def test_list_non_literal_produces_text_input():
    def fn(values: list[float] | None = None):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.TextInput)
    assert result is not None
    assert isinstance(result, dmc.TextInput)


# ── list[Literal["a","b"]] → dmc.MultiSelect ─────────────────────────────────


def test_list_literal_str_produces_multi_select():
    def fn(tags: list[Literal["a", "b", "c"]] | None = None):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.MultiSelect)
    assert result is not None
    assert isinstance(result, dmc.MultiSelect)


def test_list_literal_str_data_contains_options():
    def fn(tags: list[Literal["alpha", "beta", "gamma"]] | None = None):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.MultiSelect)
    assert set(result.data) == {"alpha", "beta", "gamma"}


def test_list_literal_str_default_value():
    def fn(tags: list[Literal["a", "b", "c"]] = ["a", "b"]):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.MultiSelect)
    assert result.value == ["a", "b"]


# ── path → dmc.TextInput ─────────────────────────────────────────────────────


def test_path_produces_text_input():
    def fn(p: pathlib.Path = pathlib.Path("/tmp")):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.TextInput)
    assert result is not None
    assert isinstance(result, dmc.TextInput)


def test_path_default_value():
    def fn(p: pathlib.Path = pathlib.Path("/usr/local")):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.TextInput)
    assert result.value == "/usr/local"


# ── dict → dmc.Textarea ──────────────────────────────────────────────────────


def test_dict_produces_textarea():
    def fn(cfg: dict | None = None):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Textarea)
    assert result is not None
    assert isinstance(result, dmc.Textarea)


def test_dict_with_default_serialized_as_json():
    def fn(cfg: dict = {"key": "val"}):
        pass

    form = _form_dmc(fn)
    result = _find(form, dmc.Textarea)
    import json
    assert json.loads(result.value) == {"key": "val"}
