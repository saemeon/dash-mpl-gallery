"""Parameter detection for gallery scripts.

Configurable parameters are declared as type-annotated assignments in the
Configurator section::

    # In the Configurator section:
    title: str = "Q4 Revenue"
    dpi: int = 150

These produce a ``dict[str, ParamSpec]`` that the Gallery uses to
auto-generate form fields.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class ParamSpec:
    """A detected parameter with its type and default value."""

    name: str
    annotation: type | None = None
    default: Any = None

    @property
    def type_name(self) -> str:
        if self.annotation is None:
            return "str"
        if hasattr(self.annotation, "__name__"):
            return self.annotation.__name__
        return str(self.annotation)


# ---------------------------------------------------------------------------
# Convention approach — parse typed assignments from source code
# ---------------------------------------------------------------------------

_SUPPORTED_TYPES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
}


def parse_typed_assignments(source: str) -> dict[str, ParamSpec]:
    """Extract ``name: type = value`` assignments from Python source.

    Only supports simple types (str, int, float, bool) and literal defaults.

    Parameters
    ----------
    source :
        Python source code to parse.

    Returns
    -------
    dict :
        Mapping of parameter name to ParamSpec.
    """
    params: dict[str, ParamSpec] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return params

    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        name = node.target.id

        # Skip private/dunder names
        if name.startswith("_"):
            continue

        # Get type annotation
        ann_type = None
        if isinstance(node.annotation, ast.Name):
            ann_type = _SUPPORTED_TYPES.get(node.annotation.id)
        if isinstance(node.annotation, ast.Attribute):
            # e.g. typing.Optional — skip complex types
            continue

        if ann_type is None:
            continue

        # Get default value
        default = ""
        if node.value is not None:
            try:
                default = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue

        params[name] = ParamSpec(name=name, annotation=ann_type, default=default)

    return params


def diff_configurator(old_source: str, new_source: str) -> list[str]:
    """Diff two CONFIGURATOR sections, return human-readable change strings.

    Reports added (``+name=val``), removed (``-name``), and changed
    (``name: old → new``) parameters by comparing detected params by name.
    """
    old_params = parse_typed_assignments(old_source)
    new_params = parse_typed_assignments(new_source)
    changes = []
    all_names = list(dict.fromkeys(list(old_params.keys()) + list(new_params.keys())))
    for name in all_names:
        old_val = old_params.get(name)
        new_val = new_params.get(name)
        if old_val is None and new_val is not None:
            changes.append(f"+{name}={new_val.default!r}")
        elif old_val is not None and new_val is None:
            changes.append(f"-{name}")
        elif old_val is not None and new_val is not None and old_val.default != new_val.default:
            changes.append(f"{name}: {old_val.default!r} → {new_val.default!r}")
    return changes


def detect_params(configurator_source: str) -> dict[str, ParamSpec]:
    """Detect parameters from a Configurator section.

    Parses ``name: type = value`` typed assignments (str, int, float, bool).

    Parameters
    ----------
    configurator_source :
        The source code of the Configurator section.

    Returns
    -------
    dict :
        Mapping of parameter name to ParamSpec.
    """
    return parse_typed_assignments(configurator_source)
