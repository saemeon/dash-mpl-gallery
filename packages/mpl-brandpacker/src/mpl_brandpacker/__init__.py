"""mpl-brandpacker — build branded matplotlib packages.

A framework for creating company-specific matplotlib packages. Define
your corporate design (colors, fonts, header/footer, axes styling) as
Python classes, call ``configure()``, and get a branded ``pyplot`` that
works as a drop-in for ``matplotlib.pyplot``.

Quick start
-----------

1. **Subclass** the base classes to define your brand::

    import mpl_brandpacker as mbp

    class MyColors(mbp.ColorsBase):
        primary = "#2563eb"
        accent = "#f59e0b"

    class MySizes(mbp.FigsizesBase):
        half = (3.46, 2.99)
        full = (6.93, 5.14)

    class MyFigure(mbp.BrandFigure):
        '''Common methods: set_title, set_subtitle, set_sources, set_footnote, legend'''
        _brand_methods = ["set_title", "set_sources"]
        def set_title(self, title): ...
        def set_sources(self, sources): ...

    class MyAxes(mbp.BrandAxes):
        '''Common methods: set_xlabel, set_ylabel, legend, zeroline, set_dateaxis'''
        _brand_methods = ["set_xlabel"]
        def set_xlabel(self, label): ...

2. **Configure** once at import time::

    mbp.configure(
        figure_cls=MyFigure,
        axes_cls=MyAxes,
        style_fn=set_my_style,          # optional: (ax, **kw) -> None
        stylesheet=Path(__file__).parent, # optional: dir with .mplstyle + data/fonts/
        pandas=True,                      # optional: also hook df.plot()
    )

3. **Re-export** pyplot as your brand's module::

    # my_brand/pyplot.py
    from mpl_brandpacker.pyplot import *  # noqa

4. **Users** just import your package::

    import my_brand.pyplot as plt
    fig, ax = plt.subplots()   # automatically branded
    fig.set_title("Q4 Revenue")
    fig.mpl.legend()           # access original matplotlib methods via .mpl

Submodules (advanced)
---------------------

- ``mpl_brandpacker.pyplot`` — branded drop-in for matplotlib.pyplot
- ``mpl_brandpacker.pandas`` — ``use_for_pandas()`` for manual df.plot() opt-in
- ``mpl_brandpacker.patcher`` — low-level ``patch_method()``, ``MethodProxy``
- ``mpl_brandpacker.style`` — ``register_stylesheet()``
- ``mpl_brandpacker.utils`` — ``get_text_bbox()``, ``separate_kwargs()``
"""

from mpl_brandpacker._config import configure
from mpl_brandpacker.axes import BrandAxes
from mpl_brandpacker.colors import ColorsBase
from mpl_brandpacker.figsizes import FigsizesBase
from mpl_brandpacker.figure import BrandFigure
from mpl_brandpacker.utils import PrintableEnum

__all__ = [
    "configure",
    "BrandFigure",
    "BrandAxes",
    "ColorsBase",
    "FigsizesBase",
    "PrintableEnum",
]
