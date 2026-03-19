# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

from __future__ import annotations

import inspect
import types
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Literal, Union, get_args, get_origin, get_type_hints

import dash
from dash import Input, Output, State, dcc, html

# --- hook protocol ---


class FieldHook:
    """Base class for field hooks.

    Subclass to define fields whose default value and/or submitted value
    are derived from runtime Dash state rather than a static default.

    Override :meth:`required_states` to declare which Dash ``State`` objects
    your hook needs. Their values are passed positionally to :meth:`get_default`
    and :meth:`transform`.
    """

    def required_states(self) -> list[State]:
        """Dash ``State`` objects this hook needs at runtime."""
        return []

    def get_default(self, *state_values: Any) -> Any:
        """Compute the initial field value from resolved state values."""
        return None

    def transform(self, value: Any, *state_values: Any) -> Any:
        """Transform the user-submitted value before it reaches the renderer."""
        return value


class FromComponent(FieldHook):
    """Read a component property as the field default.

    Parameters
    ----------
    component :
        Any Dash component with an ``.id`` attribute.
    prop :
        The component property to read (e.g. ``"value"``, ``"figure"``).
    """

    def __init__(self, component: Any, prop: str):
        self._state = State(component.id, prop)

    def required_states(self) -> list[State]:
        return [self._state]

    def get_default(self, *state_values: Any) -> Any:
        return state_values[0] if state_values else None


# --- field descriptor ---


@dataclass
class _Field:
    name: str
    type: str  # "str"|"bool"|"date"|"datetime"|"int"|"float"|"list"|"tuple"|"literal"
    default: Any
    args: tuple = ()
    optional: bool = False  # True when annotation is Optional[T] / T | None
    hook: FieldHook | None = field(default=None, repr=False)


# --- Config ---


class Config:
    def __init__(
        self,
        div: html.Div,
        states: list[State],
        fields: list[_Field],
        config_id: str,
    ):
        self.div = div
        self.states = states
        self._fields = fields
        self._config_id = config_id

    def build_kwargs(self, values: tuple) -> dict:
        return _build_kwargs(self._fields, values)

    def register_populate_callback(self, open_input: Input) -> None:
        """Register callbacks that populate hooked fields on first open.

        Existing values are preserved — fields are only populated when empty.
        """
        for f in self._fields:
            if f.hook is None:
                continue
            fid = _field_id(self._config_id, f)
            hook = f.hook

            @dash.callback(
                Output(fid, "value"),
                open_input,
                State(fid, "value"),
                *hook.required_states(),
                prevent_initial_call=True,
            )
            def populate(is_open, current_value, *state_values, _hook=hook):
                if not is_open:
                    return dash.no_update
                if current_value not in (None, ""):
                    return dash.no_update  # preserve user edits
                return _hook.get_default(*state_values)

    def register_restore_callback(self, restore_input: Input) -> None:
        """Register a callback that resets all fields to their defaults.

        Hooked fields call ``hook.get_default()``;
        non-hooked fields revert to the static default from the signature.
        """
        # De-duplicated hook states
        seen: set[tuple] = set()
        hook_states: list[State] = []
        for f in self._fields:
            if f.hook:
                for s in f.hook.required_states():
                    key = (s.component_id, s.component_property)
                    if key not in seen:
                        seen.add(key)
                        hook_states.append(s)

        outputs: list[Output] = []
        for f in self._fields:
            fid = _field_id(self._config_id, f)
            if f.type == "datetime":
                outputs.append(Output(fid, "date", allow_duplicate=True))
                outputs.append(
                    Output(
                        _time_field_id(self._config_id, f),
                        "value",
                        allow_duplicate=True,
                    )
                )
            elif f.type == "date":
                outputs.append(Output(fid, "date", allow_duplicate=True))
            else:
                outputs.append(Output(fid, "value", allow_duplicate=True))

        fields = self._fields

        @dash.callback(*outputs, restore_input, *hook_states, prevent_initial_call=True)
        def restore_all(n_clicks, *hook_state_values):
            state_map = {
                (s.component_id, s.component_property): v
                for s, v in zip(hook_states, hook_state_values)
            }
            results: list[Any] = []
            for f in fields:
                if f.hook:
                    hook = f.hook
                    resolved = [
                        state_map[(s.component_id, s.component_property)]
                        for s in hook.required_states()
                    ]
                    val = hook.get_default(*resolved)
                else:
                    val = f.default

                if f.type == "datetime":
                    if isinstance(val, datetime):
                        results.append(val.date().isoformat())
                        results.append(val.strftime("%H:%M"))
                    else:
                        results.append(None)
                        results.append(None)
                elif f.type == "date":
                    results.append(val.isoformat() if isinstance(val, date) else None)
                elif f.type == "bool":
                    results.append([f.name] if val else [])
                elif f.type in ("list", "tuple"):
                    results.append(", ".join(str(v) for v in val) if val else "")
                else:
                    results.append(val if val is not None else "")
            return results


# --- public ---


def build_config(config_id: str, fn: Callable) -> Config:
    """Introspect *fn*'s signature and return a :class:`Config`.

    Parameters
    ----------
    config_id :
        Unique namespace for component IDs.
    fn :
        Callable whose parameters define the fields.
        Parameters whose names start with ``_`` are skipped.
        Parameters whose default is a :class:`FieldHook` get their initial
        value populated at runtime via :meth:`Config.register_populate_callback`.

    Returns
    -------
    Config
        ``.div`` — ``html.Div`` with stacked labeled inputs ready to embed anywhere.
        ``.states`` — ``list[State]`` matching the fields (pass to a callback).
        ``.build_kwargs(values)`` — reconstruct a ``dict`` from callback values.
        ``.register_populate_callback(open_input)`` — wire hook defaults on open.
    """
    fields = _get_fields(fn)
    states = _build_states(config_id, fields)
    div = html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
        children=[_build_field(config_id, f) for f in fields],
    )
    return Config(div, states, fields, config_id)


# --- internals ---


def _field_id(config_id: str, field: _Field) -> str:
    return f"_s5ndt_field_{config_id}_{field.name}"


def _time_field_id(config_id: str, field: _Field) -> str:
    return f"_s5ndt_field_{config_id}_{field.name}_time"


def _infer_type(annotation: Any, default: Any) -> tuple[str, tuple, bool]:
    """Return (field_type, args, optional) from a parameter annotation + default."""
    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[T] == Union[T, None]  |  T | None (Python 3.10+)
    if origin is Union or isinstance(annotation, types.UnionType):
        all_args = args if origin is Union else get_args(annotation)
        non_none = [a for a in all_args if a is not type(None)]
        if len(non_none) == 1:
            field_type, inner_args, _ = _infer_type(non_none[0], default)
            return field_type, inner_args, True
        return "str", (), False

    if annotation is bool or isinstance(default, bool):
        return "bool", (), False
    # datetime must be checked before date (datetime is a subclass of date)
    if annotation is datetime or isinstance(default, datetime):
        return "datetime", (), False
    if annotation is date or isinstance(default, date):
        return "date", (), False
    if annotation is int or (
        isinstance(default, int) and not isinstance(default, bool)
    ):
        return "int", (), False
    if annotation is float or isinstance(default, float):
        return "float", (), False
    if origin is list:
        return "list", args, False
    if origin is tuple:
        return "tuple", args, False
    if origin is Literal:
        return "literal", args, False
    return "str", (), False


def _get_fields(fn: Callable) -> list[_Field]:
    """Introspect fn's signature, skipping parameters whose names start with ``_``."""
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    fields = []
    params = inspect.signature(fn).parameters.values()
    for param in params:
        if param.name.startswith("_"):
            continue
        raw_default = (
            param.default if param.default is not inspect.Parameter.empty else None
        )
        hook = None
        if isinstance(raw_default, FieldHook):
            hook = raw_default
            raw_default = None
        annotation = hints.get(param.name, param.annotation)
        field_type, args, optional = _infer_type(annotation, raw_default)
        fields.append(
            _Field(
                name=param.name,
                type=field_type,
                default=raw_default,
                args=args,
                optional=optional,
                hook=hook,
            )
        )

    return fields


def _build_states(config_id: str, fields: list[_Field]) -> list[State]:
    """Build the State list. datetime emits two States (date + time)."""
    states = []
    for f in fields:
        if f.type == "datetime":
            states.append(State(_field_id(config_id, f), "date"))
            states.append(State(_time_field_id(config_id, f), "value"))
        elif f.type == "date":
            states.append(State(_field_id(config_id, f), "date"))
        else:
            states.append(State(_field_id(config_id, f), "value"))
    return states


def _build_field(config_id: str, field: _Field) -> html.Div:
    """Build a labeled input component for a single field."""
    fid = _field_id(config_id, field)
    label = html.Label(field.name.replace("_", " ").title())

    if field.type == "bool":
        component = dcc.Checklist(
            id=fid,
            options=[{"label": "", "value": field.name}],
            value=[field.name] if field.default else [],
        )
    elif field.type == "date":
        component = dcc.DatePickerSingle(
            id=fid,
            date=field.default.isoformat() if isinstance(field.default, date) else None,
        )
    elif field.type == "datetime":
        default_date = (
            field.default.date().isoformat()
            if isinstance(field.default, datetime)
            else None
        )
        default_time = (
            field.default.strftime("%H:%M")
            if isinstance(field.default, datetime)
            else None
        )
        component = html.Div(
            style={"display": "flex", "gap": "8px", "alignItems": "center"},
            children=[
                dcc.DatePickerSingle(id=fid, date=default_date),
                dcc.Input(
                    id=_time_field_id(config_id, field),
                    type="text",
                    placeholder="HH:MM",
                    value=default_time,
                    debounce=True,
                    style={"width": "70px"},
                ),
            ],
        )
    elif field.type in ("int", "float"):
        component = dcc.Input(
            id=fid,
            type="number",
            step=1 if field.type == "int" else "any",
            value=field.default,
            debounce=True,
        )
    elif field.type in ("list", "tuple"):
        if field.type == "tuple":
            placeholder = ", ".join(t.__name__ for t in field.args)
        else:
            elem = field.args[0].__name__ if field.args else "value"
            placeholder = f"{elem}, ..."
        component = dcc.Input(
            id=fid,
            type="text",
            value=", ".join(str(v) for v in field.default) if field.default else "",
            placeholder=placeholder,
            debounce=True,
        )
    elif field.type == "literal":
        component = dcc.Dropdown(
            id=fid,
            options=list(field.args),
            value=field.default if field.default in field.args else field.args[0],
        )
    else:
        component = dcc.Input(
            id=fid,
            type="text",
            value=str(field.default) if field.default is not None else "",
            placeholder="",
            debounce=True,
        )

    return html.Div([label, component])


def _coerce(field: _Field, value: Any) -> Any:
    """Coerce a raw widget value to the field's Python type."""
    if field.type == "bool":
        return bool(value)

    empty = value is None or value == "" or value == []
    if empty:
        return None if field.optional else field.default

    try:
        if field.type == "date":
            return date.fromisoformat(value)
        if field.type == "int":
            return int(value)
        if field.type == "float":
            return float(value)
        if field.type == "list":
            elem_type = field.args[0] if field.args else str
            return [elem_type(x.strip()) for x in value.split(",")]
        if field.type == "tuple":
            parts = [x.strip() for x in value.split(",")]
            if field.args:
                return tuple(t(v) for t, v in zip(field.args, parts))
            return tuple(parts)
    except (ValueError, TypeError):
        return field.default
    if field.type == "literal":
        return value
    return value or ""


def _build_kwargs(fields: list[_Field], values: tuple) -> dict:
    """Consume values with an iterator — datetime fields consume two (date + time)."""
    it = iter(values)
    kwargs = {}
    for f in fields:
        if f.type == "datetime":
            date_val = next(it)
            time_val = next(it)
            if date_val is None:
                kwargs[f.name] = None if f.optional else f.default
            else:
                kwargs[f.name] = datetime.fromisoformat(
                    f"{date_val}T{time_val or '00:00'}"
                )
        else:
            kwargs[f.name] = _coerce(f, next(it))
    return kwargs
