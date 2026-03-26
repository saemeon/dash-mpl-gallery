"""Low-level patching utilities for binding methods onto matplotlib objects.

This module provides the building blocks used by :mod:`mpl_brandpacker.figure`
and :mod:`mpl_brandpacker.axes`.  Most users should use those higher-level
modules directly.

- ``patch_method()`` — bind a single method from one class onto an instance
- ``MethodProxy`` — access original (unpatched) methods via ``obj.mpl``
"""

from __future__ import annotations

import functools
from typing import Any


def patch_method(target, source, name: str, source_name: str | None = None) -> None:
    """Bind a method from *source* class onto *target* instance.

    Uses the descriptor protocol (``__get__``) to bind the method as if
    it were defined on ``type(target)``.

    Parameters
    ----------
    target :
        Instance to patch (e.g. a Figure or Axes).
    source :
        Class to retrieve the method from (e.g. BrandFigure).
    name :
        Attribute name to set on *target*.
    source_name :
        Method name to retrieve from *source*. Defaults to *name*.
    """
    if source_name is None:
        source_name = name
    setattr(target, name, getattr(source, source_name).__get__(target, type(target)))


class MethodProxy:
    """Proxy that forwards calls to the original class, bypassing patches.

    After patching, ``obj.mpl.<method>()`` calls the original matplotlib
    method instead of the brand override.

    Parameters
    ----------
    instance :
        The patched object.
    cls :
        The original class (e.g. ``matplotlib.figure.Figure``).

    Example::

        fig.mpl.legend()      # original Figure.legend
        ax.mpl.set_xlabel()   # original Axes.set_xlabel
    """

    def __init__(self, instance: object, cls: type) -> None:
        self._instance = instance
        self._cls = cls

    def __getattr__(self, name: str) -> functools.partial[Any]:
        return functools.partial(getattr(self._cls, name), self._instance)
