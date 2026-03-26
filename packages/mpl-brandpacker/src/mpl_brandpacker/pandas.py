"""Generic hook into pandas df.plot() for brand styling.

Patches ``pandas.plotting._matplotlib.core.MPLPlot.generate`` to apply
the brand's make_fig/make_ax/style hooks (from :func:`mpl_brandpacker.configure`)
after pandas creates the plot.

Usage::

    import mpl_brandpacker
    mpl_brandpacker.configure(make_fig=..., make_ax=..., style_fn=...)

    from mpl_brandpacker.pandas import use_for_pandas
    use_for_pandas()
    # Now df.plot() applies brand styling automatically
"""

from __future__ import annotations

import copy
import logging

import pandas.plotting._matplotlib as pd_mpl

from mpl_brandpacker._config import (
    get_make_ax,
    get_make_fig,
    get_style_fn,
    is_configured,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patched generate function
# ---------------------------------------------------------------------------


def _patched_generate(self: pd_mpl.core.MPLPlot) -> None:
    """Replacement for MPLPlot.generate that applies brand styling."""
    from mpl_brandpacker.utils import separate_kwargs

    make_fig = get_make_fig()
    make_ax = get_make_ax()
    style_fn = get_style_fn()

    # --- pandas internals, part 1 ---
    self._args_adjust()
    self._compute_plot_data()
    self._setup_subplots()

    # Separate brand kwargs from pandas kwargs
    style_kw, self.kwds = separate_kwargs(
        functions=[style_fn],
        **self.kwds,
    )

    # Patch fig/ax
    make_fig(self.fig)
    patch_legend = len(self.axes) == 1
    for ax in self.axes:
        make_ax(ax, patch_legend=patch_legend)

    # --- pandas internals, part 2 ---
    self._make_plot()
    self._add_table()
    if self.legend and patch_legend:
        for ax in self.axes:
            ax.legend()
    else:
        self._make_legend()
    self._adorn_subplots()

    # --- apply brand style to each axes ---
    for ax in self.axes:
        style_fn(ax, **style_kw)


# Store original for reset
_mpl_generate = copy.deepcopy(pd_mpl.core.MPLPlot.generate)


def use_for_pandas() -> None:
    """Activate brand styling for ``df.plot()``.

    Requires :func:`mpl_brandpacker.configure` to be called first.
    """
    if not is_configured():
        raise RuntimeError(
            "mpl_brandpacker has not been configured. "
            "Call mpl_brandpacker.configure(make_fig=..., make_ax=...) first."
        )
    logger.warning(
        "This changes the global pandas df.plot() behaviour.\n"
        "To revert, call mpl_brandpacker.pandas.reset_pandas()"
    )
    pd_mpl.core.MPLPlot.generate = _patched_generate


def reset_pandas() -> None:
    """Reset pandas df.plot() to default behaviour."""
    pd_mpl.core.MPLPlot.generate = _mpl_generate
