# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for FnForm: type inference, build_kwargs, Field options, validation."""

from __future__ import annotations

import pathlib
import warnings
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

import pytest
from dash import dcc
from dash_fn_forms import Field, FnForm, fixed


class _Mode(Enum):
    fast = "fast"
    slow = "slow"


# ── helpers ───────────────────────────────────────────────────────────────────


def _form(fn, **kwargs):
    """Create a FnForm with a unique ID derived from the function name."""
    uid = f"_t_{fn.__name__}_{id(fn)}"
    kwargs.setdefault("_field_components", "dcc")
    return FnForm(uid, fn, **kwargs)


def _all_components(component):
    """Recursively yield all Dash components from a component tree."""
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        if hasattr(child, "_type"):  # any Dash component, with or without children
            yield from _all_components(child)


def _find(component, cls):
    """Return the first component of type cls in the tree, or None."""
    return next((c for c in _all_components(component) if isinstance(c, cls)), None)


# ── build_kwargs ──────────────────────────────────────────────────────────────


def test_build_kwargs_basic():
    def fn(x: float = 1.0, y: int = 2, name: str = "hi"):
        pass

    form = _form(fn)
    result = form.build_kwargs((3.0, 5, "hello"))
    assert result == {"x": 3.0, "y": 5, "name": "hello"}


def test_build_kwargs_coerces_types():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn)
    # Dash sends numbers as numbers — coercion should handle string-like inputs too
    result = form.build_kwargs(("2.5", "7"))
    assert result == {"x": 2.5, "y": 7}
    assert isinstance(result["x"], float)
    assert isinstance(result["y"], int)


def test_build_kwargs_bool_checked():
    def fn(flag: bool = False):
        pass

    form = _form(fn)
    # dcc.Checklist returns a non-empty list when checked
    result = form.build_kwargs((["flag"],))
    assert result["flag"] is True


def test_build_kwargs_bool_unchecked():
    def fn(flag: bool = True):
        pass

    form = _form(fn)
    result = form.build_kwargs(([],))
    assert result["flag"] is False


def test_build_kwargs_optional_none():
    def fn(x: float | None = None):
        pass

    form = _form(fn)
    assert form.build_kwargs((None,))["x"] is None
    assert form.build_kwargs(("",))["x"] is None


def test_build_kwargs_optional_with_value():
    def fn(x: float | None = None):
        pass

    form = _form(fn)
    assert form.build_kwargs((3.14,))["x"] == pytest.approx(3.14)


def test_build_kwargs_literal():
    def fn(color: Literal["red", "blue"] = "red"):
        pass

    form = _form(fn)
    assert form.build_kwargs(("blue",)) == {"color": "blue"}


def test_build_kwargs_enum():
    def fn(mode: _Mode = _Mode.fast):
        pass

    form = _form(fn)
    assert form.build_kwargs(("slow",)) == {"mode": _Mode.slow}


def test_build_kwargs_list():
    def fn(values: list[float] | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs(("1.0, 2.5, 3.0",))
    assert result["values"] == pytest.approx([1.0, 2.5, 3.0])


def test_build_kwargs_path():
    def fn(p: pathlib.Path = pathlib.Path("/tmp")):
        pass

    form = _form(fn)
    result = form.build_kwargs(("/tmp/out.png",))
    assert result["p"] == pathlib.Path("/tmp/out.png")


def test_build_kwargs_date():
    def fn(d: date | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs(("2024-06-15",))
    assert result["d"] == date(2024, 6, 15)


def test_build_kwargs_datetime():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    # datetime fields consume two values: date + time
    result = form.build_kwargs(("2024-06-15", "09:30"))
    assert result["ts"] == datetime(2024, 6, 15, 9, 30)


# ── Field options ─────────────────────────────────────────────────────────────


def test_exclude_removes_field_from_states():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn, _exclude=["y"])
    assert len(form.states) == 1
    result = form.build_kwargs((5.0,))
    # excluded fields are not present in build_kwargs output
    assert result == {"x": 5.0}


def test_fixed_value_bypasses_widget():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn, y=fixed(99))
    # y is not in states — only x
    assert len(form.states) == 1
    result = form.build_kwargs((3.0,))
    assert result == {"x": 3.0, "y": 99}


def test_tuple_shorthand_creates_bounded_input():
    def fn(n: int = 10):
        pass

    form = _form(fn, n=(1, 100, 5))
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.min == 1
    assert inp.max == 100
    assert inp.step == 5


def test_field_widget_slider_creates_slider():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(ge=0.0, le=10.0, step=0.5, widget="slider"))
    slider = _find(form, dcc.Slider)
    assert slider is not None
    assert slider.min == 0.0
    assert slider.max == 10.0
    assert slider.step == 0.5


def test_field_persist_adds_store():
    from dash import dcc as _dcc

    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(ge=0.0, le=5.0, step=0.1, persist=True))
    store = _find(form, _dcc.Store)
    assert store is not None


def test_literal_produces_dropdown():
    def fn(color: Literal["red", "blue", "green"] = "red"):
        pass

    form = _form(fn)
    dropdown = _find(form, dcc.Dropdown)
    assert dropdown is not None
    assert set(dropdown.options) == {"red", "blue", "green"}


def test_annotated_field_label():
    def fn(
        x: Annotated[float, Field(label="My Label")] = 1.0,
    ):
        pass

    form = _form(fn)
    # The label text appears somewhere in the form's children
    form_json = str(form.to_plotly_json())
    assert "My Label" in form_json


# ── validation ────────────────────────────────────────────────────────────────


def test_build_kwargs_validated_passes():
    def fn(x: float, y: int = 2):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated((3.0, 5))
    assert errors == {}
    assert kwargs == {"x": 3.0, "y": 5}


def test_build_kwargs_validated_required_missing():
    def fn(x: float):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated((None,))
    assert "x" in errors


def test_build_kwargs_validated_custom_validator():
    def fn(
        username: Annotated[str, lambda v: None if len(v) >= 3 else "Min 3 chars"],
    ):
        pass

    form = _form(fn)
    _, errors = form.build_kwargs_validated(("ab",))
    assert "username" in errors

    _, errors = form.build_kwargs_validated(("alice",))
    assert errors == {}


# ── FieldRef ──────────────────────────────────────────────────────────────────


def test_field_ref_id():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    ref = form.x
    assert isinstance(ref.id, str)
    assert "x" in ref.id


def test_field_ref_str_equals_id():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    assert str(form.x) == form.x.id


def test_field_ref_repr():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    assert "FieldRef" in repr(form.x)


def test_field_ref_eq_string():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    assert form.x == form.x.id


def test_field_ref_eq_other_ref():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    assert form.x == form.x


def test_field_ref_hash_usable_as_dict_key():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    d = {form.x: "found"}
    assert d[form.x] == "found"
    assert d.get(form.x.id) == "found"  # string key also works


def test_field_ref_state():
    from dash import State

    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    s = form.x.state
    assert isinstance(s, State)
    assert s.component_id == form.x.id


def test_field_ref_output():
    from dash import Output

    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    o = form.x.output
    assert isinstance(o, Output)
    assert o.component_id == form.x.id


# ── named_states ──────────────────────────────────────────────────────────────


def test_named_states_keys_match_params():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn)
    ns = form.named_states
    assert set(ns.keys()) == {"x", "y"}


def test_named_states_values_are_state_objects():
    from dash import State

    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    assert isinstance(form.named_states["x"], State)


def test_named_states_datetime_emits_two_keys():

    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    ns = form.named_states
    assert "ts" in ns
    assert "ts_time" in ns


# ── dirty_states ──────────────────────────────────────────────────────────────


def test_dirty_states_returns_list_of_one_state():
    from dash import State

    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    ds = form.dirty_states
    assert len(ds) == 1
    assert isinstance(ds[0], State)


# ── validation_outputs / invalid_outputs ──────────────────────────────────────


def test_validation_outputs_length():
    def fn(x: float = 1.0, name: str = "hi"):
        pass

    form = _form(fn)
    # each validatable field → 2 outputs (message + style)
    assert len(form.validation_outputs) == 4


def test_invalid_outputs_no_errors():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    result = form.invalid_outputs({})
    assert result[0] == ""          # no message
    assert result[1]["display"] == "none"


def test_invalid_outputs_with_error():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    result = form.invalid_outputs({"x": "Too large"})
    assert result[0] == "Too large"
    assert result[1]["display"] == "block"


def test_form_validation_output_is_two_outputs():
    from dash import Output

    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    outputs = form.form_validation_output
    assert len(outputs) == 2
    assert all(isinstance(o, Output) for o in outputs)


def test_form_invalid_output_no_error():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    msg, style = form.form_invalid_output(None)
    assert msg == ""
    assert style["display"] == "none"


def test_form_invalid_output_with_error():
    def fn(x: float = 1.0):
        pass

    form = _form(fn)
    msg, style = form.form_invalid_output("Values conflict")
    assert msg == "Values conflict"
    assert style["display"] == "block"


# ── FnForm.call / call_named ──────────────────────────────────────────────────


def test_call_returns_result_on_success():
    def fn(x: float = 1.0):
        return x * 2

    form = _form(fn)
    result, errors = form.call((3.0,))
    assert result == pytest.approx(6.0)
    assert errors == {}


def test_call_returns_none_and_errors_on_failure():
    def fn(x: float):
        return x

    form = _form(fn)
    result, errors = form.call((None,))
    assert result is None
    assert "x" in errors


def test_call_named_success():
    def fn(x: float = 1.0, y: int = 2):
        return x + y

    form = _form(fn)
    result, errors = form.call_named(x=3.0, y=4)
    assert result == pytest.approx(7.0)
    assert errors == {}


def test_call_named_missing_required():
    def fn(x: float):
        return x

    form = _form(fn)
    result, errors = form.call_named(x=None)
    assert result is None
    assert "x" in errors


# ── build_object ──────────────────────────────────────────────────────────────


def test_build_object_constructs_dataclass():
    from dataclasses import dataclass

    @dataclass
    class Config:
        x: float = 1.0
        y: int = 2

    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn)
    obj = form.build_object((3.0, 5), Config)
    assert isinstance(obj, Config)
    assert obj.x == pytest.approx(3.0)
    assert obj.y == 5


# ── _named_to_values ──────────────────────────────────────────────────────────


def test_named_to_values_basic():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn)
    values = form._named_to_values({"x": 3.0, "y": 5})
    assert values == (3.0, 5)


def test_named_to_values_datetime_emits_two_entries():

    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    values = form._named_to_values({"ts": "2024-06-15", "ts_time": "09:30"})
    assert values == ("2024-06-15", "09:30")


# ── field_id ──────────────────────────────────────────────────────────────────


def test_field_id_format():
    from dash_fn_forms import field_id

    result = field_id("myform", "amplitude")
    assert result == "_dft_field_myform_amplitude"


def test_field_id_matches_form_field_ref():
    from dash_fn_forms import field_id

    def fn(amplitude: float = 1.0):
        pass

    form = _form(fn)
    uid = f"_t_{fn.__name__}_{id(fn)}"
    assert form.amplitude.id == field_id(uid, "amplitude")


# ── FnForm kwarg shorthands ───────────────────────────────────────────────────


def test_range_shorthand():
    def fn(n: int = 5):
        pass

    form = _form(fn, n=range(1, 100, 5))
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.min == 1
    assert inp.max == 100
    assert inp.step == 5


def test_two_tuple_shorthand():
    def fn(n: int = 5):
        pass

    form = _form(fn, n=(1, 100))
    inp = _find(form, dcc.Input)
    assert inp.min == 1
    assert inp.max == 100


def test_invalid_tuple_raises():
    def fn(n: int = 5):
        pass

    with pytest.raises(ValueError, match="tuple must be"):
        _form(fn, n=(1, 2, 3, 4))


def test_list_shorthand_creates_dropdown():
    def fn(mode: str = "a"):
        pass

    form = _form(fn, mode=["a", "b", "c"])
    dd = _find(form, dcc.Dropdown)
    assert dd is not None


def test_dict_shorthand_creates_dropdown():
    def fn(mode: str = "fast"):
        pass

    form = _form(fn, mode={"Fast": "fast", "Slow": "slow"})
    dd = _find(form, dcc.Dropdown)
    assert dd is not None


def test_str_shorthand_sets_label():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x="My Custom Label")
    json_str = str(form.to_plotly_json())
    assert "My Custom Label" in json_str


def test_callable_shorthand_sets_validator():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=lambda v: "Too small" if v < 0 else None)
    _, errors = form.build_kwargs_validated((-1.0,))
    assert "x" in errors


def test_component_shorthand():
    import dash.html as html

    def fn(x: float = 1.0):
        pass

    comp = dcc.Slider(id="tmp", min=0, max=10, value=5)
    form = _form(fn, x=comp)
    assert _find(form, dcc.Slider) is not None


def test_description_from_docstring():
    def fn(x: float = 1.0):
        """Descriptive help text for this function."""

    form = _form(fn)
    json_str = str(form.to_plotly_json())
    assert "Descriptive help text" in json_str


def test_cols_uses_grid_layout():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn, _cols=2)
    json_str = str(form.to_plotly_json())
    assert "grid" in json_str


def test_validator_arg_adds_error_span():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, _validator=lambda kw: None)
    json_str = str(form.to_plotly_json())
    assert "_dft_form_err_" in json_str


def test_initial_values_dict_overrides_default():
    def fn(x: float = 1.0, y: int = 2):
        pass

    form = _form(fn, _initial_values={"x": 99.0})
    inp = _find(form, dcc.Input)
    assert inp is not None
    assert inp.value == 99.0


def test_initial_values_object_overrides_default():
    class Cfg:
        x = 42.0

    def fn(x: float = 1.0):
        pass

    form = _form(fn, _initial_values=Cfg())
    inp = _find(form, dcc.Input)
    assert inp.value == 42.0


def test_include_limits_fields():
    def fn(x: float = 1.0, y: int = 2, z: str = "hi"):
        pass

    form = _form(fn, _include=["x", "z"])
    names = {f.name for f in form._fields}
    assert names == {"x", "z"}
    assert "y" not in names


def test_duplicate_config_id_warns():
    def fn(x: float = 1.0):
        pass

    uid = "_t_dup_warn_unique"
    _form_raw = lambda: FnForm(uid, fn, _field_components="dcc")  # noqa: E731
    _form_raw()  # first registration
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _form_raw()
    assert any("already in use" in str(warning.message) for warning in w)


def test_duplicate_config_id_replace_suppresses_warning():
    def fn(x: float = 1.0):
        pass

    uid = "_t_dup_replace_unique"
    FnForm(uid, fn, _field_components="dcc")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        FnForm(uid, fn, _field_components="dcc", _replace=True)
    assert not any("already in use" in str(warning.message) for warning in w)


# ── named_states branches ─────────────────────────────────────────────────────


def test_named_states_date_field():
    from dash import State

    def fn(d: date | None = None):
        pass

    form = _form(fn)
    ns = form.named_states
    assert "d" in ns
    assert isinstance(ns["d"], State)
    assert ns["d"].component_property == "date"


def test_named_states_custom_component():
    from dash import State

    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(component=dcc.Slider(min=0, max=10, value=5)))
    ns = form.named_states
    assert "x" in ns
    assert isinstance(ns["x"], State)
    assert ns["x"].component_property == "value"


# ── build_kwargs_validated datetime ──────────────────────────────────────────


def test_build_kwargs_validated_datetime_success():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated(("2024-06-15", "09:30"))
    assert errors == {}
    assert kwargs["ts"] == datetime(2024, 6, 15, 9, 30)


def test_build_kwargs_validated_datetime_none_optional():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated((None, None))
    assert errors == {}
    assert kwargs["ts"] is None


def test_build_kwargs_validated_datetime_invalid_time():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    _, errors = form.build_kwargs_validated(("2024-06-15", "bad"))
    assert "ts" in errors


def test_build_kwargs_validated_validator_raises():
    """Validator function that raises an exception → error stored as str."""

    def fn(x: float = 1.0):
        pass

    def exploding_validator(v):
        raise RuntimeError("boom")

    form = _form(fn, x=Field(validator=exploding_validator))
    _, errors = form.build_kwargs_validated((5.0,))
    assert "x" in errors
    assert "boom" in errors["x"]


def test_build_kwargs_validated_form_level_validator():
    def fn(x: float = 1.0, y: float = 1.0):
        pass

    def cross_check(kw):
        return "x must be less than y" if kw["x"] >= kw["y"] else None

    form = FnForm(f"_t_cross_{id(cross_check)}", fn, _validator=cross_check, _field_components="dcc")
    _, errors = form.build_kwargs_validated((5.0, 3.0))
    assert "_form" in errors

    _, errors = form.build_kwargs_validated((1.0, 3.0))
    assert errors == {}


def test_build_kwargs_validated_form_validator_raises():
    def fn(x: float = 1.0):
        pass

    form = FnForm(
        f"_t_fv_raise_{id(fn)}",
        fn,
        _validator=lambda kw: (_ for _ in ()).throw(RuntimeError("oops")),  # type: ignore[misc]
        _field_components="dcc",
    )
    _, errors = form.build_kwargs_validated((1.0,))
    assert "_form" in errors


# ── build_kwargs coerce/validate branches ─────────────────────────────────────


def test_build_kwargs_datetime_none_optional():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs((None, None))
    assert result["ts"] is None


def test_build_kwargs_datetime_short_time():
    """4-char time like '930' should be padded to '09:30'."""

    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs(("2024-06-15", "9:30"))
    assert result["ts"] == datetime(2024, 6, 15, 9, 30)


def test_build_kwargs_tuple_type():
    # tuple[int, int] with typed args — _infer_type sees origin=tuple
    def fn(coords: tuple[int, int] = (0, 0)):
        pass

    form = _form(fn)
    result = form.build_kwargs(("1, 2",))
    assert result["coords"] == (1, 2)


def test_build_kwargs_dict_type():
    def fn(cfg: dict = {}):  # noqa: B006
        pass

    form = _form(fn)
    result = form.build_kwargs(('{"a": 1}',))
    assert result["cfg"] == {"a": 1}


def test_build_kwargs_dict_invalid_json():
    def fn(cfg: dict = {}):  # noqa: B006
        pass

    form = _form(fn)
    result = form.build_kwargs(("not json",))
    assert result["cfg"] == {}  # returns default


def test_build_kwargs_enum_invalid_key():
    def fn(mode: _Mode = _Mode.fast):
        pass

    form = _form(fn)
    result = form.build_kwargs(("nonexistent",))
    assert result["mode"] == _Mode.fast  # returns default


def test_build_kwargs_int_empty_uses_zero():
    def fn(n: int = 5):
        pass

    form = _form(fn)
    result = form.build_kwargs((None,))
    assert result["n"] == 5  # returns default (not None, since not optional)


# ── Field description rendered ────────────────────────────────────────────────


def test_field_description_in_json():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(description="Enter a value between 0 and 10"))
    json_str = str(form.to_plotly_json())
    assert "Enter a value between 0 and 10" in json_str


# ── visible field wrapping ────────────────────────────────────────────────────


def test_visible_field_gets_wrapper_div():
    def fn(mode: str = "basic", x: float = 1.0):
        pass

    form = _form(fn, x=Field(visible=("mode", "==", "advanced")))
    json_str = str(form.to_plotly_json())
    assert "_dft_vis_" in json_str


def test_visible_neq_operator():
    def fn(mode: str = "basic", x: float = 1.0):
        pass

    form = _form(fn, x=Field(visible=("mode", "!=", "hidden")))
    json_str = str(form.to_plotly_json())
    assert "_dft_vis_" in json_str


def test_visible_in_operator():
    def fn(mode: str = "a", x: float = 1.0):
        pass

    form = _form(fn, x=Field(visible=("mode", "in", ["a", "b"])))
    json_str = str(form.to_plotly_json())
    assert "_dft_vis_" in json_str


def test_visible_not_in_operator():
    def fn(mode: str = "a", x: float = 1.0):
        pass

    form = _form(fn, x=Field(visible=("mode", "not in", ["hidden"])))
    json_str = str(form.to_plotly_json())
    assert "_dft_vis_" in json_str


# ── pydantic / annotated-types constraints ────────────────────────────────────


def test_pydantic_field_constraints():
    """_read_constraint_meta reads ge/le from a pydantic FieldInfo."""
    from pydantic import Field as PydanticField

    from dash_fn_forms._forms import _read_constraint_meta

    pyd_field = PydanticField(ge=0.0, le=10.0)
    result = _read_constraint_meta(pyd_field)
    assert result.get("min") == 0.0
    assert result.get("max") == 10.0


def test_annotated_types_constraints():
    """_read_constraint_meta reads Ge/Le from annotated_types metadata."""
    from annotated_types import Ge

    from dash_fn_forms._forms import _read_constraint_meta

    result = _read_constraint_meta(Ge(5.0))
    assert result.get("min") == 5.0
