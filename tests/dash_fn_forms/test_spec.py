# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for Field, FieldHook, FromComponent, fixed, _FieldFixed."""

from __future__ import annotations

from dash import State, dcc
from dash_fn_forms import Field, FnForm, fixed
from dash_fn_forms._spec import FieldHook, FromComponent, _FieldFixed

# ── fixed ─────────────────────────────────────────────────────────────────────


def test_fixed_returns_field_fixed():
    result = fixed(42)
    assert isinstance(result, _FieldFixed)


def test_fixed_stores_value():
    result = fixed("hello")
    assert result.value == "hello"


def test_fixed_none_value():
    result = fixed(None)
    assert result.value is None


# ── FieldHook base class ───────────────────────────────────────────────────────


def test_field_hook_required_states_default():
    hook = FieldHook()
    assert hook.required_states() == []


def test_field_hook_get_default_default():
    hook = FieldHook()
    assert hook.get_default() is None


def test_field_hook_transform_passthrough():
    hook = FieldHook()
    assert hook.transform("value") == "value"
    assert hook.transform(42, "extra_state") == 42


def test_field_hook_subclass():
    class MyHook(FieldHook):
        def get_default(self, *state_values):
            return state_values[0] * 2 if state_values else 0

    hook = MyHook()
    assert hook.get_default(5) == 10
    assert hook.get_default() == 0


# ── FromComponent ─────────────────────────────────────────────────────────────


def test_from_component_required_states():
    comp = dcc.Input(id="my-input", value="hello")
    hook = FromComponent(comp, "value")
    states = hook.required_states()
    assert len(states) == 1
    assert isinstance(states[0], State)
    assert states[0].component_id == "my-input"
    assert states[0].component_property == "value"


def test_from_component_get_default_returns_first_value():
    comp = dcc.Dropdown(id="my-dropdown", value="opt1")
    hook = FromComponent(comp, "value")
    assert hook.get_default("opt1") == "opt1"


def test_from_component_get_default_no_values():
    comp = dcc.Input(id="inp2", value="x")
    hook = FromComponent(comp, "value")
    assert hook.get_default() is None


# ── Field aliases ─────────────────────────────────────────────────────────────


def test_field_ge_sets_min():
    f = Field(ge=0.0, le=10.0)
    assert f.min == 0.0


def test_field_le_sets_max():
    f = Field(ge=0.0, le=10.0)
    assert f.max == 10.0


def test_field_gt_sets_min():
    f = Field(gt=0)
    assert f.min == 0


def test_field_lt_sets_max():
    f = Field(lt=100)
    assert f.max == 100


def test_field_min_wins_over_ge():
    # canonical min wins; ge only fills in when min is None
    f = Field(min=1.0, ge=2.0)
    assert f.min == 1.0


def test_field_max_wins_over_le():
    f = Field(max=9.0, le=8.0)
    assert f.max == 9.0


# ── Field properties ──────────────────────────────────────────────────────────


def test_field_label():
    f = Field(label="My Label")
    assert f.label == "My Label"


def test_field_description():
    f = Field(description="Some help text")
    assert f.description == "Some help text"


def test_field_persist_default_false():
    f = Field()
    assert f.persist is False


def test_field_persist_true():
    f = Field(persist=True)
    assert f.persist is True


def test_field_widget_slider():
    f = Field(widget="slider")
    assert f.widget == "slider"


def test_field_col_span():
    f = Field(col_span=2)
    assert f.col_span == 2


def test_field_validator():
    def validator(v):
        return None if v > 0 else "Must be positive"

    f = Field(validator=validator)
    assert f.validator is validator


def test_field_visible_tuple():
    f = Field(visible=("mode", "==", "advanced"))
    assert f.visible == ("mode", "==", "advanced")


def test_field_step():
    f = Field(step=0.5)
    assert f.step == 0.5


def test_field_component_override():
    comp = dcc.RadioItems(options=["a", "b"], value="a")
    f = Field(component=comp)
    assert f.component is comp


def test_field_component_prop_default():
    f = Field()
    assert f.component_prop == "value"


def test_field_component_prop_custom():
    f = Field(component_prop="figure")
    assert f.component_prop == "figure"


# ── Field in FnForm ───────────────────────────────────────────────────────────


def test_field_with_slider_creates_slider_widget():
    """widget='slider' in Field is stored and used by FnForm."""

    def fn(x: float = 1.0):
        pass

    uid = f"_t_field_slider_{id(fn)}"
    form = FnForm(uid, fn, x=Field(ge=0.0, le=10.0, step=0.5, widget="slider"))
    json_str = str(form.to_plotly_json())
    assert "Slider" in json_str


def test_field_persist_adds_store_to_form():

    def fn(x: float = 1.0):
        pass

    uid = f"_t_field_persist_{id(fn)}"
    form = FnForm(uid, fn, x=Field(ge=0.0, le=5.0, step=0.1, persist=True))
    json_str = str(form.to_plotly_json())
    assert "Store" in json_str
