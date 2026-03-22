# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for _validate, _coerce, _to_widget_value, _check_visible, _has_error_span,
and related internal helpers — exercised through the public FnForm API."""

from __future__ import annotations

import pathlib
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

import pytest
from dash_fn_forms import Field, FnForm
from dash_fn_forms._forms import Form, _check_visible


class _Color(Enum):
    red = "red"
    green = "green"


def _form(fn, **kwargs):
    uid = f"_t_cv_{fn.__name__}_{id(fn)}"
    kwargs.setdefault("_field_components", "dcc")
    return FnForm(uid, fn, **kwargs)


# ── _validate: non-validatable type returns None (no error) ───────────────────


def test_validate_enum_is_not_validatable():
    """Enum is not in _VALIDATABLE — _validate returns None, no error span."""

    def fn(c: _Color = _Color.red):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated(("red",))
    assert "c" not in errors


def test_validate_literal_not_in_validatable():
    def fn(mode: Literal["a", "b"] = "a"):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated(("a",))
    assert errors == {}


# ── _validate: list with min_length / max_length ─────────────────────────────


def test_validate_list_min_length():
    def fn(tags: list[str] | None = None):
        pass

    form = FnForm(
        f"_t_minlen_{id(fn)}",
        fn,
        tags=Field(min_length=2),
        _field_components="dcc",
    )
    _, errors = form.build_kwargs_validated(("a",))
    assert "tags" in errors
    assert "Minimum" in errors["tags"]


def test_validate_list_max_length():
    def fn(tags: list[str] | None = None):
        pass

    form = FnForm(
        f"_t_maxlen_{id(fn)}",
        fn,
        tags=Field(max_length=1),
        _field_components="dcc",
    )
    _, errors = form.build_kwargs_validated(("a, b, c",))
    assert "tags" in errors
    assert "Maximum" in errors["tags"]


def test_validate_list_invalid_element_type():
    def fn(vals: list[int] | None = None):
        pass

    form = _form(fn)
    _, errors = form.build_kwargs_validated(("a, b",))
    assert "vals" in errors
    assert errors["vals"] == "Invalid value"


# ── _validate: str constraints ────────────────────────────────────────────────


def test_validate_str_min_length():
    def fn(name: str = ""):
        pass

    form = FnForm(
        f"_t_str_min_{id(fn)}",
        fn,
        name=Field(min_length=3),
        _field_components="dcc",
    )
    _, errors = form.build_kwargs_validated(("ab",))
    assert "name" in errors
    assert "Minimum" in errors["name"]


def test_validate_str_max_length():
    def fn(name: str = ""):
        pass

    form = FnForm(
        f"_t_str_max_{id(fn)}",
        fn,
        name=Field(max_length=3),
        _field_components="dcc",
    )
    _, errors = form.build_kwargs_validated(("abcdef",))
    assert "name" in errors
    assert "Maximum" in errors["name"]


def test_validate_str_pattern():
    def fn(code: str = ""):
        pass

    form = FnForm(
        f"_t_str_pat_{id(fn)}",
        fn,
        code=Field(pattern=r"\d{3}"),
        _field_components="dcc",
    )
    _, errors = form.build_kwargs_validated(("abc",))
    assert "code" in errors
    assert "Must match" in errors["code"]

    _, errors = form.build_kwargs_validated(("123",))
    assert errors == {}


# ── _validate: tuple ──────────────────────────────────────────────────────────


def test_validate_tuple_valid():
    def fn(coords: tuple[int, int] = (0, 0)):
        pass

    form = _form(fn)
    kwargs, errors = form.build_kwargs_validated(("1, 2",))
    assert errors == {}
    assert kwargs["coords"] == (1, 2)


# ── _coerce: empty with no default for int/float ─────────────────────────────


def test_coerce_int_empty_required_returns_zero():
    """Required int with None input and no default → 0."""

    def fn(n: int):
        pass

    form = _form(fn)
    result = form.build_kwargs((None,))
    assert result["n"] == 0


def test_coerce_float_empty_required_returns_zero():
    def fn(x: float):
        pass

    form = _form(fn)
    result = form.build_kwargs((None,))
    assert result["x"] == 0.0


# ── _coerce: list[Literal] ─────────────────────────────────────────────────────


def test_coerce_list_literal_passthrough():
    """list[Literal] values come back as-is (multi-select returns a list)."""

    def fn(tags: list[Literal["a", "b", "c"]] | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs((["a", "c"],))
    assert result["tags"] == ["a", "c"]


def test_coerce_list_literal_non_list_fallback():
    def fn(tags: list[Literal["a", "b", "c"]] | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs(("a",))  # string instead of list
    assert result["tags"] == []


# ── _coerce: tuple with/without args ─────────────────────────────────────────


def test_coerce_tuple_without_args():
    def fn(coords: tuple = ()):
        pass

    # bare `tuple` is inferred as "str" (no origin) → falls through
    # use tuple[int, int] instead which has args
    def fn2(coords: tuple[int, int] = (0, 0)):
        pass

    form = _form(fn2)
    result = form.build_kwargs(("3, 4",))
    assert result["coords"] == (3, 4)


def test_coerce_tuple_invalid_raises_returns_default():
    def fn(coords: tuple[int, int] = (0, 0)):
        pass

    form = _form(fn)
    result = form.build_kwargs(("a, b",))  # can't convert to int
    assert result["coords"] == (0, 0)  # returns default


# ── _coerce: dict ─────────────────────────────────────────────────────────────


def test_coerce_dict_valid_json():
    def fn(cfg: dict = {}):  # noqa: B006
        pass

    form = _form(fn)
    result = form.build_kwargs(('{"x": 1}',))
    assert result["cfg"] == {"x": 1}


def test_coerce_dict_invalid_json_returns_default():
    def fn(cfg: dict = {"default": True}):  # noqa: B006
        pass

    form = _form(fn)
    result = form.build_kwargs(("not-json",))
    assert result["cfg"] == {"default": True}


# ── _coerce: path ─────────────────────────────────────────────────────────────


def test_coerce_path():
    def fn(p: pathlib.Path = pathlib.Path(".")):
        pass

    form = _form(fn)
    result = form.build_kwargs(("/tmp/out",))
    assert result["p"] == pathlib.Path("/tmp/out")


# ── _to_widget_value via _apply_restore ───────────────────────────────────────


def test_apply_restore_datetime_with_value():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    form._fields[0].default = datetime(2024, 6, 15, 9, 30)
    results = Form._apply_restore(form._fields, [], [])
    assert results == ["2024-06-15", "09:30"]


def test_apply_restore_datetime_none():
    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    results = Form._apply_restore(form._fields, [], [])
    assert results == [None, None]


def test_apply_restore_date_with_value():
    def fn(d: date | None = None):
        pass

    form = _form(fn)
    form._fields[0].default = date(2024, 6, 15)
    results = Form._apply_restore(form._fields, [], [])
    assert results == ["2024-06-15"]


def test_apply_restore_date_none():
    def fn(d: date | None = None):
        pass

    form = _form(fn)
    results = Form._apply_restore(form._fields, [], [])
    assert results == [None]


def test_apply_restore_enum():
    def fn(c: _Color = _Color.red):
        pass

    form = _form(fn)
    results = Form._apply_restore(form._fields, [], [])
    assert results == ["red"]


def test_apply_restore_dict():
    def fn(cfg: dict = {}):  # noqa: B006
        pass

    form = _form(fn)
    form._fields[0].default = {"key": "val"}
    results = Form._apply_restore(form._fields, [], [])
    assert '"key"' in results[0]


def test_apply_restore_path():
    def fn(p: pathlib.Path = pathlib.Path(".")):
        pass

    form = _form(fn)
    results = Form._apply_restore(form._fields, [], [])
    assert results == ["."]


def test_apply_restore_list_literal():
    def fn(tags: list[Literal["a", "b"]] | None = None):
        pass

    form = _form(fn)
    form._fields[0].default = ["a"]
    results = Form._apply_restore(form._fields, [], [])
    assert results == [["a"]]


def test_apply_restore_list_non_literal():
    def fn(vals: list[float] | None = None):
        pass

    form = _form(fn)
    form._fields[0].default = [1.0, 2.0]
    results = Form._apply_restore(form._fields, [], [])
    assert results == ["1.0, 2.0"]


# ── _check_visible: all operators ────────────────────────────────────────────


def test_check_visible_eq():
    assert _check_visible("a", "==", "a") is True
    assert _check_visible("a", "==", "b") is False


def test_check_visible_neq():
    assert _check_visible("a", "!=", "b") is True
    assert _check_visible("a", "!=", "a") is False


def test_check_visible_in():
    assert _check_visible("a", "in", ["a", "b"]) is True
    assert _check_visible("c", "in", ["a", "b"]) is False


def test_check_visible_not_in():
    assert _check_visible("c", "not in", ["a", "b"]) is True
    assert _check_visible("a", "not in", ["a", "b"]) is False


def test_check_visible_unknown_op_returns_true():
    assert _check_visible("x", "???", "y") is True


# ── col_span > 1 in _build_field ─────────────────────────────────────────────


def test_col_span_gt_1_sets_grid_column():
    def fn(x: float = 1.0):
        pass

    form = _form(fn, x=Field(col_span=2))
    json_str = str(form.to_plotly_json())
    assert "span 2" in json_str


# ── Field(description=...) rendered ──────────────────────────────────────────


def test_custom_component_with_description():
    from dash import dcc as _dcc

    comp = _dcc.Slider(min=0, max=10, value=5)

    def fn(x: float = 1.0):
        pass

    form = FnForm(
        f"_t_comp_desc_{id(fn)}",
        fn,
        x=Field(component=comp, description="Drag to adjust"),
        _field_components="dcc",
    )
    json_str = str(form.to_plotly_json())
    assert "Drag to adjust" in json_str


# ── _get_fields: reserved params skipped ─────────────────────────────────────


def test_reserved_param_skipped():
    """Parameters in the _exclude list are excluded from fields."""

    def fn(x: float = 1.0, y: float = 2.0):
        pass

    form = FnForm(
        f"_t_excl_{id(fn)}",
        fn,
        _exclude=["y"],
        _field_components="dcc",
    )
    names = {f.name for f in form._fields}
    assert "y" not in names
    assert "x" in names


# ── _get_fields: FieldHook as default value ───────────────────────────────────


def test_field_hook_as_default():
    """FieldHook passed as default value creates Field(hook=...)."""
    from dash_fn_forms._spec import FieldHook

    class ConstHook(FieldHook):
        def get_default(self, *args):
            return 7.0

    def fn(x: float = ConstHook()):  # type: ignore[assignment]
        pass

    form = _form(fn)
    assert len(form._fields) == 1
    f = form._fields[0]
    assert f.spec is not None
    assert f.spec.hook is not None


# ── _get_fields: annotated with Field + bare validator merged ─────────────────


def test_annotated_field_and_bare_validator_merged():
    """Annotated[T, Field(label=...), validator] merges validator into spec."""

    def fn(
        x: Annotated[float, Field(label="Speed"), lambda v: "Too big" if v > 100 else None] = 1.0,
    ):
        pass

    form = _form(fn)
    f = form._fields[0]
    assert f.spec is not None
    assert f.spec.label == "Speed"
    assert f.spec.validator is not None


# ── _build_kwargs: short 4-char datetime time ─────────────────────────────────


def test_build_kwargs_datetime_4char_time():
    """Time string '930' (4 chars) should be left-padded to '09:30'."""

    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs(("2024-01-15", "9:30"))
    assert result["ts"] == datetime(2024, 1, 15, 9, 30)


def test_build_kwargs_datetime_invalid_iso():
    """Invalid date+time combination falls back to default."""

    def fn(ts: datetime | None = None):
        pass

    form = _form(fn)
    result = form.build_kwargs(("2024-01-15", "not-a-time"))
    assert result["ts"] is None


# ── _resolve_spec: FieldHook external spec ────────────────────────────────────


def test_field_hook_as_kwarg():
    """Passing a FieldHook directly as a kwarg creates Field(hook=...)."""
    from dash_fn_forms._spec import FieldHook

    class ConstHook2(FieldHook):
        def get_default(self, *args):
            return 3.14

    def fn(x: float = 1.0):
        pass

    form = FnForm(f"_t_hook_kwarg_{id(fn)}", fn, x=ConstHook2(), _field_components="dcc")
    f = form._fields[0]
    assert f.spec is not None
    assert f.spec.hook is not None


# ── _resolve_spec: styles / class_names dicts ─────────────────────────────────


def test_styles_dict_applied_to_field_type():
    def fn(x: float = 1.0):
        pass

    form = FnForm(
        f"_t_styles_{id(fn)}",
        fn,
        _styles={"float": {"color": "red"}},
        _field_components="dcc",
    )
    f = form._fields[0]
    assert f.spec is not None
    assert f.spec.style == {"color": "red"}


def test_class_names_dict_applied_to_field_type():
    def fn(x: float = 1.0):
        pass

    form = FnForm(
        f"_t_cls_{id(fn)}",
        fn,
        _class_names={"float": "my-float-class"},
        _field_components="dcc",
    )
    f = form._fields[0]
    assert f.spec is not None
    assert f.spec.class_name == "my-float-class"


# ── _infer_type: multi-union (Union[int, str]) → str ─────────────────────────


def test_multi_union_falls_back_to_str():
    """Union[int, str] (non-optional) → inferred as 'str'."""
    from typing import Union

    def fn(x: Union[int, str] = "hi"):  # noqa: UP007
        pass

    form = _form(fn)
    f = form._fields[0]
    assert f.type == "str"
