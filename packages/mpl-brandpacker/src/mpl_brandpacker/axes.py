"""Axes patching: base class + patcher.

``BrandAxes`` is a base class that brand implementations subclass.
Define your custom axes methods, list them in ``_brand_methods``,
and use ``patch_axes()`` to bind them onto plain Axes instances.

Example::

    from mpl_brandpacker.axes import BrandAxes, patch_axes

    class MyAxes(BrandAxes):
        _brand_methods = ["set_xlabel", "legend", "zeroline"]

        def set_xlabel(self, label): ...
        def legend(self, **kw): ...
        def zeroline(self): ...

    patch_axes(ax, MyAxes, style_fn=set_my_style)
    ax.mpl.set_xlabel("raw")  # → original Axes.set_xlabel
"""

from __future__ import annotations

import functools

from mpl_brandpacker.patcher import MethodProxy, patch_method


class BrandAxes:
    """Base class for brand Axes implementations.

    Subclass this and define your brand's axes-level methods.

    Attributes
    ----------
    _brand_methods : list[str]
        Method names to bind onto Axes instances.
        Common choices: ``"set_xlabel"``, ``"set_ylabel"``,
        ``"set_ylabel_side"``, ``"legend"``, ``"zeroline"``,
        ``"set_dateaxis"``, ``"annotated_vline"``.

    Example::

        class MyAxes(BrandAxes):
            _brand_methods = ["set_xlabel", "set_ylabel", "legend"]

            def set_xlabel(self, label, **kw):
                # self is the matplotlib Axes instance
                defaults = {"fontsize": 8}
                defaults.update(kw)
                self.mpl.set_xlabel(label, **defaults)

            def set_ylabel(self, label, **kw):
                self.mpl.set_ylabel(label, rotation="horizontal", **kw)

            def legend(self, **kw):
                # custom horizontal legend below axes
                ...

    After patching:

    - ``ax.set_xlabel("X")`` calls your method
    - ``ax.mpl.set_xlabel("X")`` calls original matplotlib Axes.set_xlabel
    """

    _brand_methods: list[str] = []


def patch_axes(
    ax,
    brand_cls: type,
    *,
    methods: list[str] | None = None,
    style_fn=None,
    extra_patches: dict[str, str] | None = None,
    proxy_attr: str = "mpl",
    marker_attr: str = "_is_branded",
    twinx_fn=None,
    twiny_fn=None,
    patch_legend: bool = True,
    **style_kwargs,
) -> None:
    """Bind brand methods onto a matplotlib Axes.

    Parameters
    ----------
    ax :
        A matplotlib Axes instance.
    brand_cls :
        Subclass of :class:`BrandAxes`.
    methods :
        Method names to patch. Defaults to ``brand_cls._brand_methods``.
    style_fn :
        Optional ``(ax, **kw) -> None`` called after patching.
    extra_patches :
        ``{target_name: source_name}`` for renamed methods.
    proxy_attr :
        Attribute name for :class:`MethodProxy`.
    marker_attr :
        Attribute set to prevent double-patching.
    twinx_fn, twiny_fn :
        Optional replacements for ``ax.twinx()`` / ``ax.twiny()``.
    patch_legend :
        If False, restore original ``legend`` after patching.
    **style_kwargs :
        Passed to *style_fn*.
    """
    from matplotlib.axes import Axes

    if getattr(ax, marker_attr, False):
        return

    setattr(ax, marker_attr, True)
    setattr(ax, proxy_attr, MethodProxy(ax, Axes))

    for name in (methods or getattr(brand_cls, "_brand_methods", [])):
        patch_method(ax, brand_cls, name)

    if extra_patches:
        for target_name, source_name in extra_patches.items():
            patch_method(ax, brand_cls, target_name, source_name)

    if not patch_legend and hasattr(ax, proxy_attr):
        ax.legend = getattr(ax, proxy_attr).legend

    if twinx_fn is not None:
        ax.twinx = functools.partial(twinx_fn, ax)
    if twiny_fn is not None:
        ax.twiny = functools.partial(twiny_fn, ax)

    if style_fn is not None:
        style_fn(ax, **style_kwargs)
