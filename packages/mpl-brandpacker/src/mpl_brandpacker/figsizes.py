"""Base class for brand figsize enums.

Enforces (width, height) tuples in inches at class definition time.

Example::

    from mpl_brandpacker.figsizes import FigsizesBase, MM_TO_INCH

    class Figsizes(FigsizesBase):
        publication_half = (88 * MM_TO_INCH, 76 * MM_TO_INCH)
        presentation_full = (314 * MM_TO_INCH, 130 * MM_TO_INCH)
        # bad = 42  # → ValueError

    Figsizes.plot()  # → visual comparison
"""

from __future__ import annotations

from mpl_brandpacker.utils import PrintableEnum

MM_TO_INCH = 1 / 25.4
"""Multiply mm values by this to get inches."""


class FigsizesBase(tuple, PrintableEnum):
    """Base class for brand figure size palettes. All values must be (width, height) in inches.

    Call ``MySizes.plot()`` to display a visual comparison of all sizes.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, member in cls.__members__.items():
            val = member.value
            if (
                not isinstance(val, tuple)
                or len(val) != 2
                or not all(isinstance(v, (int, float)) for v in val)
            ):
                raise ValueError(
                    f"{cls.__name__}.{name} = {val!r} must be a (width, height) "
                    f"tuple of numbers in inches (e.g. (6.0, 4.0))."
                )

    @classmethod
    def plot(cls, figsize=None):
        """Display a visual comparison of all figure sizes.

        Shows each size as a scaled rectangle with dimensions labeled.

        Parameters
        ----------
        figsize :
            Figure size. Auto-computed if None.
        """
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches

        names = list(cls.__members__.keys())
        sizes = [cls[n].value for n in names]

        max_w = max(w for w, h in sizes)
        max_h = max(h for w, h in sizes)
        scale = 1.0  # 1 inch in data = 1 inch on screen

        if figsize is None:
            fig_w = max_w * scale + 3  # room for labels
            fig_h = len(names) * (max_h * scale * 0.3 + 0.4) + 0.5
            figsize = (fig_w, fig_h)

        fig, ax = plt.subplots(figsize=figsize)
        ax.set_title(cls.__name__, fontsize=12, weight="bold", loc="left")
        ax.axis("off")

        y = 0
        for name, (w, h) in zip(names, sizes):
            sw = w * scale * 0.25  # scale down for display
            sh = h * scale * 0.25

            rect = patches.Rectangle(
                (0.1, y), sw, sh,
                facecolor="#e8e8e8", edgecolor="#888", linewidth=0.8,
            )
            ax.add_patch(rect)
            ax.text(
                sw + 0.3, y + sh / 2,
                f"{name}  ({w:.1f} × {h:.1f} in)",
                fontsize=8, va="center",
            )
            y += sh + 0.15

        ax.set_xlim(-0.1, max_w * scale * 0.25 + 5)
        ax.set_ylim(-0.1, y + 0.1)
        fig.tight_layout()
        return fig
