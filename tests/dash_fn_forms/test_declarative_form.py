# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for the declarative Form subclass pattern (Form._collect_fields)."""

from __future__ import annotations

from typing import Annotated, Literal

import pytest
from dash import State
from dash_fn_forms import Field
from dash_fn_forms._forms import Form
from dash_fn_forms._spec import FieldHook  # noqa: E402

# ── basic field collection ─────────────────────────────────────────────────────


class SimpleForm(Form):
    x: float = 1.0
    y: int = 2
    name: str = "Alice"


def _make_simple():
    return SimpleForm("_t_simple", _field_components="dcc")


def test_form_subclass_has_correct_field_count():
    form = _make_simple()
    assert len(form._fields) == 3


def test_form_subclass_field_names():
    form = _make_simple()
    names = {f.name for f in form._fields}
    assert names == {"x", "y", "name"}


def test_form_subclass_field_defaults():
    form = _make_simple()
    defaults = {f.name: f.default for f in form._fields}
    assert defaults["x"] == 1.0
    assert defaults["y"] == 2
    assert defaults["name"] == "Alice"


def test_form_subclass_states_length():
    form = _make_simple()
    assert len(form.states) == 3


def test_form_subclass_states_are_state_objects():
    form = _make_simple()
    for s in form.states:
        assert isinstance(s, State)


# ── build_kwargs ───────────────────────────────────────────────────────────────


def test_form_subclass_build_kwargs():
    form = _make_simple()
    result = form.build_kwargs((3.0, 5, "Bob"))
    assert result == {"x": 3.0, "y": 5, "name": "Bob"}


def test_form_subclass_build_kwargs_coerces_types():
    form = _make_simple()
    result = form.build_kwargs(("2.5", "7", "Carol"))
    assert result["x"] == pytest.approx(2.5)
    assert isinstance(result["x"], float)
    assert result["y"] == 7
    assert isinstance(result["y"], int)


# ── annotated Field spec ───────────────────────────────────────────────────────


class AnnotatedForm(Form):
    x: Annotated[float, Field(ge=0.0, le=10.0, label="Speed")] = 1.0
    mode: Literal["fast", "slow"] = "fast"


def _make_annotated():
    return AnnotatedForm("_t_annotated", _field_components="dcc")


def test_annotated_form_field_spec_present():
    form = _make_annotated()
    x_field = next(f for f in form._fields if f.name == "x")
    assert x_field.spec is not None
    assert x_field.spec.min == 0.0
    assert x_field.spec.max == 10.0


def test_annotated_form_label_in_json():
    form = _make_annotated()
    json_str = str(form.to_plotly_json())
    assert "Speed" in json_str


def test_annotated_form_literal_produces_dropdown():
    from dash import dcc

    form = _make_annotated()

    def _all(comp):
        yield comp
        for ch in getattr(comp, "children", None) or []:
            if hasattr(ch, "_type"):
                yield from _all(ch)

    dd = next((c for c in _all(form) if isinstance(c, dcc.Dropdown)), None)
    assert dd is not None


# ── Field as default value ─────────────────────────────────────────────────────


class FieldDefaultForm(Form):
    x: float = Field(ge=0.0, le=5.0, default=2.0)  # type: ignore[assignment]


def test_field_as_default_value():
    form = FieldDefaultForm("_t_field_default", _field_components="dcc")
    assert len(form._fields) == 1
    f = form._fields[0]
    assert f.name == "x"
    assert f.default == 2.0
    assert f.spec is not None
    assert f.spec.min == 0.0


# ── private attrs not collected ────────────────────────────────────────────────


class PrivateForm(Form):
    x: float = 1.0
    _private: str = "ignored"  # type: ignore[assignment]


def test_private_attrs_not_collected():
    form = PrivateForm("_t_private", _field_components="dcc")
    names = {f.name for f in form._fields}
    assert "_private" not in names
    assert "x" in names


# ── _apply_restore ─────────────────────────────────────────────────────────────


def test_apply_restore_returns_defaults():
    form = _make_simple()
    results = Form._apply_restore(form._fields, [], [])
    # No hooks → returns widget values for defaults: 1.0, 2, "Alice"
    assert len(results) == 3
    assert results[0] == 1.0
    assert results[1] == 2
    assert results[2] == "Alice"


# ── _apply_populate ────────────────────────────────────────────────────────────


class _EchoHook(FieldHook):
    """Returns a fixed default of 42.0."""

    def get_default(self, *state_values):
        return 42.0


class _HookedForm(Form):
    x: Annotated[float, Field(hook=_EchoHook())] = 0.0  # type: ignore[assignment]


class _HookedForm2(Form):
    x: Annotated[float, Field(hook=_EchoHook())] = 0.0  # type: ignore[assignment]


def test_apply_populate_empty_current_fills_defaults():
    form = _HookedForm("_t_populate", _field_components="dcc")
    hooked = [f for f in form._fields if f.spec and f.spec.hook is not None]
    current_values = [None]  # field is empty
    results = Form._apply_populate(hooked, [], current_values, [])
    assert results[0] == 42.0


def test_apply_populate_non_empty_current_preserved():
    import dash

    form = _HookedForm2("_t_populate2", _field_components="dcc")
    hooked = [f for f in form._fields if f.spec and f.spec.hook is not None]
    current_values = [5.0]  # field already has a value
    results = Form._apply_populate(hooked, [], current_values, [])
    assert results[0] is dash.no_update
