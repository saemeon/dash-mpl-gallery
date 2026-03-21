# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Component backends for dash-fn-interact.

Pass ``_backend`` to :func:`~dash_fn_interact.build_config` as a string
shorthand or a :class:`ComponentBackend` instance.  When omitted, ``"auto"``
is used: :class:`DMCBackend` if ``dash-mantine-components`` is installed,
otherwise :class:`DCCBackend` as a fallback.

String shorthands::

    cfg = build_config("id", fn, _backend="dmc")   # Mantine
    cfg = build_config("id", fn, _backend="dbc")   # Bootstrap
    cfg = build_config("id", fn, _backend="dcc")   # plain dcc (explicit fallback)
    cfg = build_config("id", fn, _backend="auto")  # DMC if available, else dcc

Instance (for custom subclasses)::

    from dash_fn_interact.backends import DMCBackend
    cfg = build_config("id", fn, _backend=DMCBackend())
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from dash import dcc, html

from dash_fn_interact._spec import Field


def _debounce(spec: Field) -> bool:
    """Resolve effective debounce setting (default: True)."""
    return True if spec.debounce is None else spec.debounce


class ComponentBackend:
    """Abstract base class for component backends.

    Subclass to swap out the Dash components used for each field type.
    Only :meth:`make` is required; the rest of the build pipeline
    (introspection, validation, states, callbacks) is backend-agnostic.
    """

    def make(self, config_id: str, f: Any, spec: Field, fid: str) -> Any:
        """Return a Dash component for *f* with the given *fid* as its ``id``.

        Parameters
        ----------
        config_id :
            The config namespace (used for composite components like datetime).
        f :
            The ``_Field`` descriptor (type, default, args, optional, spec).
        spec :
            The resolved ``Field`` for this field.
        fid :
            The Dash component ID to assign.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Default backend — plain dcc/html, no extra deps
# ---------------------------------------------------------------------------


class DCCBackend(ComponentBackend):
    """Fallback backend using plain ``dcc``/``html`` (no extra dependencies).

    Used automatically when ``dash-mantine-components`` is not installed.
    """

    def make(self, config_id: str, f: Any, spec: Field, fid: str) -> Any:
        if f.type == "bool":
            return dcc.Checklist(
                id=fid,
                options=[{"label": "", "value": f.name}],
                value=[f.name] if f.default else [],
                style=spec.style,
                className=spec.class_name,
            )
        if f.type == "date":
            return dcc.DatePickerSingle(
                id=fid,
                date=f.default.isoformat() if isinstance(f.default, date) else None,
                style=spec.style,
                className=spec.class_name,
            )
        if f.type == "datetime":
            default_date = (
                f.default.date().isoformat()
                if isinstance(f.default, datetime)
                else None
            )
            default_time = (
                f.default.strftime("%H:%M") if isinstance(f.default, datetime) else None
            )
            time_fid = f"_dft_field_{config_id}_{f.name}_time"
            return html.Div(
                style={"display": "flex", "gap": "8px", "alignItems": "center"},
                children=[
                    dcc.DatePickerSingle(
                        id=fid,
                        date=default_date,
                        style=spec.style,
                        className=spec.class_name,
                    ),
                    dcc.Input(
                        id=time_fid,
                        type="text",
                        placeholder="HH:MM",
                        value=default_time,
                        debounce=_debounce(spec),
                        style={"width": "70px", **(spec.style or {})},
                        className=spec.class_name,
                    ),
                ],
            )
        if f.type in ("int", "float"):
            step: Any = spec.step
            if step is None:
                step = 1 if f.type == "int" else "any"
            return dcc.Input(
                id=fid,
                type="number",
                step=step,
                value=f.default,
                min=spec.min,
                max=spec.max,
                debounce=_debounce(spec),
                style=spec.style,
                className=spec.class_name,
            )
        if f.type in ("list", "tuple"):
            if f.type == "tuple":
                placeholder = ", ".join(t.__name__ for t in f.args)
            else:
                elem = f.args[0].__name__ if f.args else "value"
                placeholder = f"{elem}, ..."
            return dcc.Input(
                id=fid,
                type="text",
                value=", ".join(str(v) for v in f.default) if f.default else "",
                placeholder=placeholder,
                debounce=_debounce(spec),
                style=spec.style,
                className=spec.class_name,
            )
        if f.type == "literal":
            return dcc.Dropdown(
                id=fid,
                options=list(f.args),
                value=f.default if f.default in f.args else f.args[0],
                style=spec.style,
                className=spec.class_name,
            )
        if f.type == "enum":
            enum_cls = f.args[0]
            members = list(enum_cls)
            default_name = (
                f.default.name if isinstance(f.default, enum_cls) else members[0].name
            )
            return dcc.Dropdown(
                id=fid,
                options=[{"label": m.name, "value": m.name} for m in members],
                value=default_name,
                style=spec.style,
                className=spec.class_name,
            )
        if f.type == "dict":
            default_str = json.dumps(f.default, indent=2) if f.default else ""
            return dcc.Textarea(
                id=fid,
                value=default_str,
                placeholder='{"key": "value"}',
                style={
                    "fontFamily": "monospace",
                    "width": "100%",
                    **(spec.style or {}),
                },
                className=spec.class_name,
            )
        if f.type == "path":
            return dcc.Input(
                id=fid,
                type="text",
                value=str(f.default) if f.default is not None else "",
                placeholder="/path/to/file",
                debounce=_debounce(spec),
                minLength=spec.min_length,
                maxLength=spec.max_length,
                style=spec.style,
                className=spec.class_name,
            )
        # str (fallback)
        return dcc.Input(
            id=fid,
            type="text",
            value=str(f.default) if f.default is not None else "",
            placeholder="",
            debounce=_debounce(spec),
            minLength=spec.min_length,
            maxLength=spec.max_length,
            style=spec.style,
            className=spec.class_name,
        )


_default = DCCBackend()


def _auto_backend() -> ComponentBackend:
    """Return DMCBackend if dash-mantine-components is installed, else DCCBackend."""
    try:
        import dash_mantine_components  # noqa: F401

        return DMCBackend()
    except ImportError:
        return _default


def _resolve_backend(backend: Any) -> ComponentBackend:
    """Resolve a backend argument to a :class:`ComponentBackend` instance.

    Accepts a string shorthand or an existing instance:

    * ``None`` / ``"auto"`` → :class:`DMCBackend` if available, else :class:`DCCBackend`
    * ``"dcc"`` → :class:`DCCBackend` (explicit fallback)
    * ``"dmc"`` → :class:`DMCBackend`
    * ``"dbc"`` → :class:`DBCBackend`
    * :class:`ComponentBackend` instance → returned as-is
    """
    if backend is None or backend == "auto":
        return _auto_backend()
    if backend == "dcc":
        return _default
    if backend == "dmc":
        return DMCBackend()
    if backend == "dbc":
        return DBCBackend()
    if backend == "auto":
        return _auto_backend()
    if isinstance(backend, ComponentBackend):
        return backend
    raise ValueError(
        f"Unknown backend {backend!r}. "
        "Use 'dcc', 'dmc', 'dbc', 'auto', or a ComponentBackend instance."
    )


# ---------------------------------------------------------------------------
# DMC backend — dash-mantine-components
# ---------------------------------------------------------------------------


class DMCBackend(ComponentBackend):
    """Backend using `dash-mantine-components <https://www.dash-mantine.com/>`_.

    Requires ``pip install dash-mantine-components``.

    Provides richer components for numeric and text fields.  Date / datetime
    fields fall back to :class:`DefaultBackend` for API compatibility.
    Bool fields keep ``dcc.Checklist`` to preserve the ``value`` prop used
    by :attr:`~dash_fn_interact.Config.states`.
    """

    def make(self, config_id: str, f: Any, spec: Field, fid: str) -> Any:
        try:
            import dash_mantine_components as dmc
        except ImportError as exc:
            raise ImportError(
                "dash-mantine-components is required for DMCBackend. "
                "Install it with: pip install dash-mantine-components"
            ) from exc

        # date / datetime — fall back to default (DMC DatePicker has a different API)
        if f.type in ("date", "datetime"):
            return _default.make(config_id, f, spec, fid)

        # bool — keep dcc.Checklist for value-prop compatibility
        if f.type == "bool":
            return _default.make(config_id, f, spec, fid)

        if f.type in ("int", "float"):
            step = spec.step
            if step is None:
                step = 1 if f.type == "int" else 0.01
            return dmc.NumberInput(
                id=fid,
                value=f.default if f.default is not None else "",
                min=spec.min,
                max=spec.max,
                step=step,
                style=spec.style,
                className=spec.class_name,
            )

        if f.type == "literal":
            # dmc.Select requires string values
            if all(isinstance(v, str) for v in f.args):
                return dmc.Select(
                    id=fid,
                    data=list(f.args),
                    value=f.default if f.default in f.args else f.args[0],
                    style=spec.style,
                    className=spec.class_name,
                )
            return _default.make(config_id, f, spec, fid)

        if f.type == "enum":
            enum_cls = f.args[0]
            members = list(enum_cls)
            default_name = (
                f.default.name if isinstance(f.default, enum_cls) else members[0].name
            )
            return dmc.Select(
                id=fid,
                data=[{"label": m.name, "value": m.name} for m in members],
                value=default_name,
                style=spec.style,
                className=spec.class_name,
            )

        if f.type == "dict":
            default_str = json.dumps(f.default, indent=2) if f.default else ""
            return dmc.Textarea(
                id=fid,
                value=default_str,
                placeholder='{"key": "value"}',
                style={
                    "fontFamily": "monospace",
                    "width": "100%",
                    **(spec.style or {}),
                },
                className=spec.class_name,
            )

        # str, path, list, tuple — text input
        return dmc.TextInput(
            id=fid,
            value=str(f.default) if f.default is not None else "",
            style=spec.style,
            className=spec.class_name,
        )


# ---------------------------------------------------------------------------
# DBC backend — dash-bootstrap-components
# ---------------------------------------------------------------------------


class DBCBackend(ComponentBackend):
    """Backend using `dash-bootstrap-components <https://dash-bootstrap-components.opensource.faculty.ai/>`_.

    Requires ``pip install dash-bootstrap-components``.

    Date / datetime fields fall back to :class:`DefaultBackend` (DBC has no
    date picker).  Bool fields use ``dbc.Checklist`` which shares the same
    ``value`` prop as ``dcc.Checklist``.
    """

    def make(self, config_id: str, f: Any, spec: Field, fid: str) -> Any:
        try:
            import dash_bootstrap_components as dbc
        except ImportError as exc:
            raise ImportError(
                "dash-bootstrap-components is required for DBCBackend. "
                "Install it with: pip install dash-bootstrap-components"
            ) from exc

        # date / datetime — fall back to default (DBC has no date picker)
        if f.type in ("date", "datetime"):
            return _default.make(config_id, f, spec, fid)

        if f.type == "bool":
            return dbc.Checklist(
                id=fid,
                options=[{"label": "", "value": f.name}],
                value=[f.name] if f.default else [],
                style=spec.style,
                className=spec.class_name,
            )

        if f.type in ("int", "float"):
            step = spec.step
            if step is None:
                step = 1 if f.type == "int" else None
            return dbc.Input(
                id=fid,
                type="number",
                value=f.default,
                min=spec.min,
                max=spec.max,
                step=step,
                debounce=_debounce(spec),
                style=spec.style,
                className=spec.class_name,
            )

        if f.type == "literal":
            options = [{"label": str(v), "value": v} for v in f.args]
            return dbc.Select(
                id=fid,
                options=options,
                value=f.default if f.default in f.args else f.args[0],
                style=spec.style,
                className=spec.class_name,
            )

        if f.type == "enum":
            enum_cls = f.args[0]
            members = list(enum_cls)
            default_name = (
                f.default.name if isinstance(f.default, enum_cls) else members[0].name
            )
            return dbc.Select(
                id=fid,
                options=[{"label": m.name, "value": m.name} for m in members],
                value=default_name,
                style=spec.style,
                className=spec.class_name,
            )

        if f.type == "dict":
            default_str = json.dumps(f.default, indent=2) if f.default else ""
            return dbc.Textarea(
                id=fid,
                value=default_str,
                placeholder='{"key": "value"}',
                style={
                    "fontFamily": "monospace",
                    "width": "100%",
                    **(spec.style or {}),
                },
                className=spec.class_name,
            )

        if f.type in ("list", "tuple"):
            if f.type == "tuple":
                placeholder = ", ".join(t.__name__ for t in f.args)
            else:
                elem = f.args[0].__name__ if f.args else "value"
                placeholder = f"{elem}, ..."
            return dbc.Input(
                id=fid,
                type="text",
                value=", ".join(str(v) for v in f.default) if f.default else "",
                placeholder=placeholder,
                debounce=_debounce(spec),
                style=spec.style,
                className=spec.class_name,
            )

        # str, path
        return dbc.Input(
            id=fid,
            type="text",
            value=str(f.default) if f.default is not None else "",
            placeholder="",
            debounce=_debounce(spec),
            style=spec.style,
            className=spec.class_name,
        )
