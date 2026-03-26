"""Utility functions for mpl-brandpacker.

Provides reusable helpers that brand packages can use:

- ``PrintableEnum`` — Enum with nice repr listing all members
- ``get_text_bbox`` — measure rendered text dimensions in inches
- ``separate_kwargs`` — route pooled kwargs to multiple functions
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from enum import Enum, EnumMeta
from typing import Any

from matplotlib.figure import Figure
from matplotlib.text import Text
from matplotlib.transforms import Bbox

# ---------------------------------------------------------------------------
# Enum helpers
# ---------------------------------------------------------------------------


class PrintableEnumMeta(EnumMeta):
    """Metaclass that makes enum repr list all members."""

    def __repr__(cls) -> str:
        return cls.__doc__ + "\n" + "\n".join(cls.__members__.keys())

    def __getitem__(cls, item: str):
        item = item.replace("-", "_")
        try:
            return cls._member_map_[item]
        except KeyError:
            raise KeyError(
                f"'{item}' is not a member of {cls.__name__}. "
                f"Available: {', '.join(cls.__members__.keys())}"
            )


class PrintableEnum(Enum, metaclass=PrintableEnumMeta):
    """Enum base class with nice repr. Inherit from this instead of Enum."""

    ...


# ---------------------------------------------------------------------------
# Text measurement
# ---------------------------------------------------------------------------


class ExtendedBbox(Bbox):
    """Bbox with ``width_inch`` and ``height_inch`` attributes."""

    width_inch: float
    height_inch: float


def get_text_bbox(
    text: str | Text | None = None,
    fig: Figure | None = None,
    fontsize: float = 8,
    **kwargs,
) -> ExtendedBbox:
    """Measure the rendered bounding box of text.

    Returns a Bbox extended with ``width_inch`` and ``height_inch``.

    Parameters
    ----------
    text :
        String to measure, existing Text artist, or None (zero bbox).
    fig :
        Figure for rendering context. Created if not provided.
    fontsize :
        Font size in points.
    """
    if text is None:
        box = Bbox([[0, 0], [0, 0]])
        box.width_inch = 0
        box.height_inch = 0
        return box

    if isinstance(text, Text):
        text_el = text
        fig = text_el.figure
        remove = False
    else:
        fig = fig or Figure()
        text_el = fig.text(0.5, 0.5, text, fontsize=fontsize, **kwargs)
        remove = True

    try:
        renderer = fig.canvas.get_renderer() if fig.canvas else None
    except Exception:
        renderer = None

    box = text_el.get_window_extent(renderer=renderer)
    if remove:
        text_el.remove()
    box.width_inch = box.width / fig.get_dpi()
    box.height_inch = box.height / fig.get_dpi()
    return box


# ---------------------------------------------------------------------------
# Kwargs routing
# ---------------------------------------------------------------------------


def available_kw(fn: Callable) -> list[str]:
    """Get parameter names a function accepts."""
    return list(inspect.signature(fn).parameters)


def filter_kw(kw_list: list[str], **kwargs) -> dict[str, Any]:
    """Filter kwargs to only keys in kw_list."""
    return {k: kwargs[k] for k in kw_list if k in kwargs}


def separate_kwargs(
    functions: list[Callable],
    **kwargs,
) -> tuple[dict[str, Any], ...]:
    """Route pooled kwargs to the functions that accept them.

    Returns one dict per function + a rest dict for unmatched kwargs.

    Example::

        style_kw, rest = separate_kwargs([set_style], title="Q4", dpi=150)
    """
    separated = []
    used_keys: set[str] = set()
    for fn in functions:
        fn_kw = filter_kw(available_kw(fn), **kwargs)
        separated.append(fn_kw)
        used_keys.update(fn_kw.keys())

    rest = {k: v for k, v in kwargs.items() if k not in used_keys}
    return *separated, rest
