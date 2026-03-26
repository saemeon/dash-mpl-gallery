"""Central configuration for mpl-brandpacker.

One ``configure()`` call wires up everything::

    import mpl_brandpacker

    mpl_brandpacker.configure(
        figure_cls=MyFigure,
        axes_cls=MyAxes,
        style_fn=set_my_style,
        stylesheet=Path(__file__).parent,
        pandas=True,
    )
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_make_fig: Callable | None = None
_make_ax: Callable | None = None
_style_fn: Callable | None = None


def configure(
    figure_cls: type | None = None,
    axes_cls: type | None = None,
    style_fn: Callable | None = None,
    stylesheet: str | Path | None = None,
    pandas: bool = False,
    *,
    make_fig: Callable | None = None,
    make_ax: Callable | None = None,
) -> None:
    """Configure mpl-brandpacker with your brand.

    This is the single entry point. Call it once at import time in your
    brand package.

    Parameters
    ----------
    figure_cls :
        Your BrandFigure subclass (e.g. ``MyFigure``).
        mpl-brandpacker will create a ``make_fig`` function that calls
        ``patch_figure(fig, figure_cls)`` for you.
    axes_cls :
        Your BrandAxes subclass (e.g. ``MyAxes``).
        mpl-brandpacker will create a ``make_ax`` function that calls
        ``patch_axes(ax, axes_cls, style_fn=style_fn)`` for you.
    style_fn :
        Optional ``(ax, **kw) -> None`` applied after axes patching.
        Also used by pandas ``df.plot()`` when ``pandas=True``.
    stylesheet :
        Path to directory containing ``.mplstyle`` file and ``data/fonts/``.
        Calls ``register_stylesheet(path)`` for you.
    pandas :
        If True, also hook ``df.plot()`` so it applies brand styling.
    make_fig :
        Advanced: explicit ``(fig) -> fig`` function instead of ``figure_cls``.
    make_ax :
        Advanced: explicit ``(ax, **kw) -> ax`` function instead of ``axes_cls``.
    """
    global _make_fig, _make_ax, _style_fn

    # --- Warn on double-configure ---
    if is_configured():
        import warnings
        warnings.warn(
            "mpl_brandpacker.configure() called again — overwriting previous config.",
            stacklevel=2,
        )

    # --- Validate _brand_methods ---
    if figure_cls is not None:
        for name in getattr(figure_cls, "_brand_methods", []):
            if not hasattr(figure_cls, name):
                raise ValueError(
                    f"{figure_cls.__name__}._brand_methods lists '{name}' "
                    f"but {figure_cls.__name__}.{name}() is not defined."
                )
    if axes_cls is not None:
        for name in getattr(axes_cls, "_brand_methods", []):
            if not hasattr(axes_cls, name):
                raise ValueError(
                    f"{axes_cls.__name__}._brand_methods lists '{name}' "
                    f"but {axes_cls.__name__}.{name}() is not defined."
                )

    # --- Build make_ax first (needed by make_fig) ---
    if make_ax is not None:
        _make_ax = make_ax
    elif axes_cls is not None:
        from mpl_brandpacker.axes import patch_axes

        def _auto_make_ax(ax, _cls=axes_cls, _style=style_fn, **kw):
            patch_axes(ax, _cls, style_fn=_style, **kw)
            return ax

        _make_ax = _auto_make_ax
    else:
        _make_ax = lambda ax, **kw: ax  # noqa: E731

    _style_fn = style_fn or _make_ax

    # --- Build make_fig (passes make_ax for axes auto-patching) ---
    if make_fig is not None:
        _make_fig = make_fig
    elif figure_cls is not None:
        from mpl_brandpacker.figure import patch_figure

        def _auto_make_fig(fig, _cls=figure_cls, _max=_make_ax):
            patch_figure(fig, _cls, make_ax=_max)
            return fig

        _make_fig = _auto_make_fig
    else:
        _make_fig = lambda fig: fig  # noqa: E731

    # --- Register stylesheet ---
    if stylesheet is not None:
        from mpl_brandpacker.style import register_stylesheet
        register_stylesheet(Path(stylesheet))

    # --- Hook pandas ---
    if pandas:
        from mpl_brandpacker.pandas import use_for_pandas
        use_for_pandas()


def get_make_fig() -> Callable:
    """Return the make_fig hook. Raises if not configured."""
    if _make_fig is None:
        raise RuntimeError(
            "mpl_brandpacker not configured. "
            "Call mpl_brandpacker.configure(...) first."
        )
    return _make_fig


def get_make_ax() -> Callable:
    """Return the make_ax hook. Raises if not configured."""
    if _make_ax is None:
        raise RuntimeError(
            "mpl_brandpacker not configured. "
            "Call mpl_brandpacker.configure(...) first."
        )
    return _make_ax


def get_style_fn() -> Callable:
    """Return the style_fn hook. Raises if not configured."""
    if _style_fn is None:
        raise RuntimeError(
            "mpl_brandpacker not configured. "
            "Call mpl_brandpacker.configure(...) first."
        )
    return _style_fn


def is_configured() -> bool:
    """Return True if configure() has been called."""
    return _make_fig is not None and _make_ax is not None
