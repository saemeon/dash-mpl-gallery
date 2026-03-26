"""Figure patching: base class + patcher.

``BrandFigure`` defines your brand's figure-level methods (header, footer,
legend). ``patch_figure()`` binds them onto a plain matplotlib Figure and
optionally wraps axes-creation methods so new axes are auto-patched too.

Example::

    from mpl_brandpacker.figure import BrandFigure, patch_figure

    class MyFigure(BrandFigure):
        _brand_methods = ["set_title", "set_sources", "legend"]

        def set_title(self, title, **kw): ...
        def set_sources(self, sources, **kw): ...
        def legend(self, *a, **kw): ...

    def make_fig(fig):
        patch_figure(fig, MyFigure, make_ax=make_ax)
        return fig
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from mpl_brandpacker.patcher import MethodProxy, patch_method


class BrandFigure:
    """Base class for brand Figure implementations.

    Subclass this and define your brand's figure-level methods.

    Attributes
    ----------
    _brand_methods : list[str]
        Method names to bind onto Figure instances.
        Common choices: ``"set_title"``, ``"set_subtitle"``,
        ``"set_sources"``, ``"set_footnote"``, ``"legend"``,
        ``"add_extraspace_header"``, ``"add_extraspace_footer"``.

    Example::

        class MyFigure(BrandFigure):
            _brand_methods = ["set_title", "set_sources", "legend"]

            def set_title(self, title, **kw):
                # self is the matplotlib Figure instance
                _add_header(self, title=title, **kw)

            def set_sources(self, sources, **kw):
                _add_footer(self, sources=sources, **kw)

    After patching:

    - ``fig.set_title("Q4")`` calls your method
    - ``fig.mpl.legend()`` calls original matplotlib Figure.legend
    """

    _brand_methods: list[str] = []


def patch_figure(
    fig,
    brand_cls: type,
    *,
    make_ax: Callable | None = None,
    methods: list[str] | None = None,
    extra_patches: dict[str, str] | None = None,
    proxy_attr: str = "mpl",
    marker_attr: str = "_is_branded",
) -> None:
    """Bind brand methods onto a matplotlib Figure.

    Parameters
    ----------
    fig :
        A matplotlib Figure instance.
    brand_cls :
        Subclass of :class:`BrandFigure`.
    make_ax :
        Optional ``(ax, **kw) -> ax`` that patches axes. When provided,
        ``subplots()``, ``add_subplot()``, ``add_axes()``, and
        ``subplot_mosaic()`` are wrapped so every new axes is auto-patched.
    methods :
        Method names to patch. Defaults to ``brand_cls._brand_methods``.
    extra_patches :
        ``{target_name: source_name}`` for renamed methods
        (e.g. ``{"suptitle": "set_title"}``).
    proxy_attr :
        Attribute name for :class:`MethodProxy` (default ``"mpl"``).
    marker_attr :
        Attribute set to prevent double-patching.
    """
    from matplotlib.figure import Figure

    if getattr(fig, marker_attr, False):
        return

    setattr(fig, marker_attr, True)
    setattr(fig, proxy_attr, MethodProxy(fig, Figure))

    for name in (methods or getattr(brand_cls, "_brand_methods", [])):
        patch_method(fig, brand_cls, name)

    if extra_patches:
        for target_name, source_name in extra_patches.items():
            patch_method(fig, brand_cls, target_name, source_name)

    if make_ax is not None:
        _wrap_axes_creation(fig, make_ax, proxy_attr)


def _wrap_axes_creation(fig, make_ax: Callable, proxy_attr: str = "mpl") -> None:
    """Wrap axes-creation methods on *fig* to auto-patch new axes."""
    proxy = getattr(fig, proxy_attr)

    _orig_subplots = proxy.subplots

    def _subplots(*args, **kwargs):
        axes = _orig_subplots(*args, **kwargs)
        for ax in np.array(axes).flatten():
            make_ax(ax)
        return axes

    fig.subplots = _subplots

    _orig_add_subplot = proxy.add_subplot

    def _add_subplot(*args, **kwargs):
        ax = _orig_add_subplot(*args, **kwargs)
        make_ax(ax)
        return ax

    fig.add_subplot = _add_subplot

    _orig_add_axes = proxy.add_axes

    def _add_axes(*args, **kwargs):
        ax = _orig_add_axes(*args, **kwargs)
        make_ax(ax)
        return ax

    fig.add_axes = _add_axes

    _orig_subplot_mosaic = proxy.subplot_mosaic

    def _subplot_mosaic(*args, **kwargs):
        axes_dict = _orig_subplot_mosaic(*args, **kwargs)
        for ax in axes_dict.values():
            make_ax(ax)
        return axes_dict

    fig.subplot_mosaic = _subplot_mosaic
