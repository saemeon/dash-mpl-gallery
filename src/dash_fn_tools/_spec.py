# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Public types: FieldHook, FromComponent, FieldSpec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dash import State

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


# --- FieldSpec ---


@dataclass
class FieldSpec:
    """Per-field configuration for :func:`~dash_fn_tools.build_config`.

    Can be supplied in three ways (highest priority wins):

    1. **In-signature** via ``Annotated[T, FieldSpec(...)]`` — for functions
       you own.
    2. **External** via ``field_specs={"name": FieldSpec(...)}`` on
       :func:`~dash_fn_tools.build_config` — for functions you don't own.
    3. Type-level ``styles`` / ``class_names`` dicts on
       :func:`~dash_fn_tools.build_config` fill in any visual properties
       not set by the above.

    A :class:`FieldHook` instance may also be passed directly as a
    ``field_specs`` value and is treated as ``FieldSpec(hook=hook)``.
    """

    # --- label / help ---
    label: str | None = None
    """Override the auto-generated label (default: param name in title case)."""
    description: str | None = None
    """Help text rendered below the component."""

    # --- layout ---
    col_span: int = 1
    """Column span in a multi-column grid (see ``cols`` on :func:`build_config`)."""

    # --- styling ---
    style: dict | None = None
    """CSS dict applied to the component (not the wrapper div)."""
    class_name: str = ""
    """CSS class applied to the component."""

    # --- component override ---
    component: Any = None
    """Replace the auto-generated component entirely. ``id`` is set internally."""
    component_prop: str = "value"
    """Property to read back from a custom ``component`` (default: ``"value"``)."""

    # --- numeric constraints (int / float only) ---
    min: float | None = None
    """Minimum value. Only applied to ``int`` / ``float`` fields."""
    max: float | None = None
    """Maximum value. Only applied to ``int`` / ``float`` fields."""
    step: float | int | str | None = None
    """Step size. Only applied to ``int`` / ``float`` fields."""

    # --- runtime default ---
    hook: FieldHook | None = None
    """Runtime hook that derives the field's default from Dash state."""

    # --- interactivity ---
    visible: tuple | None = None
    """Conditional visibility rule: ``("other_field", "==", value)``."""
