"""Base class for brand color enums.

Enforces hex color format at class definition time.

Example::

    from mpl_brandpacker.colors import ColorsBase

    class Colors(ColorsBase):
        primary = "#2563eb"
        secondary = "#64748b"
        accent = "#f59e0b"
        # bad = "red"  # → ValueError

    Colors.plot()  # → swatch grid
"""

from __future__ import annotations

import re

from mpl_brandpacker.utils import PrintableEnum

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ColorsBase(str, PrintableEnum):
    """Base class for brand color palettes. All values must be '#RRGGBB'.

    Call ``MyColors.plot()`` to display a swatch grid of all colors.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, member in cls.__members__.items():
            if not _HEX_RE.match(member.value):
                raise ValueError(
                    f"{cls.__name__}.{name} = {member.value!r} is not a valid "
                    f"hex color. Use '#RRGGBB' format (e.g. '#2563eb')."
                )

    @classmethod
    def plot(cls, figsize=None, columns=4):
        """Display a swatch grid of all colors.

        Parameters
        ----------
        figsize :
            Figure size. Auto-computed if None.
        columns :
            Number of columns in the grid.
        """
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches

        names = list(cls.__members__.keys())
        n = len(names)
        rows = (n + columns - 1) // columns

        if figsize is None:
            figsize = (columns * 2.2, rows * 0.6)

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_xlim(0, columns)
        ax.set_ylim(0, rows)
        ax.axis("off")
        ax.set_title(cls.__name__, fontsize=12, weight="bold", loc="left")

        for i, name in enumerate(names):
            col = i % columns
            row = rows - 1 - i // columns
            color = cls[name].value

            rect = patches.FancyBboxPatch(
                (col + 0.05, row + 0.1), 0.4, 0.4,
                boxstyle="round,pad=0.02",
                facecolor=color, edgecolor="#ddd", linewidth=0.5,
            )
            ax.add_patch(rect)
            ax.text(col + 0.55, row + 0.35, name, fontsize=8, va="center")
            ax.text(col + 0.55, row + 0.15, color, fontsize=6.5,
                    va="center", color="#888")

        fig.tight_layout()
        return fig
