# mpl-brandpacker

Package your brand design into a `matplotlib.pyplot` drop-in replacement. Define titles, headers styling, colors, and axes styling as Python classes — mpl-brandpacker handles the patching so `your_brand.pyplot.subplots()` returns fully branded figures and axes.

## Install

```bash
pip install mpl-brandpacker
```

## Quick start

### 1. Define your brand

```python
# my_brand/colors.py
import mpl_brandpacker as mbp

class Colors(mbp.ColorsBase):
    primary = "#1a5276"
    accent = "#e67e22"
    dark = "#2c3e50"

Colors.plot()  # → swatch grid for documentation
```

```python
# my_brand/sizes.py
from mpl_brandpacker.figsizes import MM_TO_INCH

class Sizes(mbp.FigsizesBase):
    half = (88 * MM_TO_INCH, 76 * MM_TO_INCH)
    full = (181 * MM_TO_INCH, 76 * MM_TO_INCH)
```

```python
# my_brand/figure.py
class MyFigure(mbp.BrandFigure):
    _brand_methods = ["set_title", "set_sources"]

    def set_title(self, title, **kw):
        self.mpl.suptitle(title, fontsize=10, weight="bold", x=0.02, ha="left", **kw)

    def set_sources(self, sources, **kw):
        self.text(0.02, 0.02, f"Source: {sources}", fontsize=6.5,
                  color="#888", transform=self.transFigure, **kw)
```

```python
# my_brand/axes.py
class MyAxes(mbp.BrandAxes):
    _brand_methods = ["set_xlabel", "set_ylabel"]

    def set_xlabel(self, label, **kw):
        self.mpl.set_xlabel(label, fontsize=8, **kw)

    def set_ylabel(self, label, **kw):
        self.mpl.set_ylabel(label, fontsize=8, rotation="horizontal", **kw)

def set_style(ax, **kw):
    ax.grid(True, alpha=0.2)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
```

### 2. Configure

```python
# my_brand/__init__.py
import mpl_brandpacker as mbp
from pathlib import Path

mbp.configure(
    figure_cls=MyFigure,
    axes_cls=MyAxes,
    style_fn=set_style,
    stylesheet=Path(__file__).parent,  # dir with .mplstyle + data/fonts/
    pandas=True,                        # also hook df.plot()
)
```

### 3. Re-export pyplot

```python
# my_brand/pyplot.py
import my_brand  # triggers configure()
from mpl_brandpacker.pyplot import *  # noqa
```

### 4. Use it

```python
import my_brand.pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [4, 5, 6])
fig.set_title("Revenue")
fig.set_sources("Bloomberg")
ax.set_xlabel("Quarter")
plt.show()
```

Everything is branded. Original matplotlib methods are accessible via `.mpl`:

```python
fig.mpl.legend()       # original Figure.legend
ax.mpl.set_xlabel()    # original Axes.set_xlabel
```

## What it provides

| Export | Purpose |
|---|---|
| `configure()` | Wire everything up — one call |
| `BrandFigure` | Base class for figure methods |
| `BrandAxes` | Base class for axes methods |
| `ColorsBase` | Hex-validated color enum with `.plot()` |
| `FigsizesBase` | Validated (w,h) size enum with `.plot()` |
| `PrintableEnum` | Generic enum base |

### Submodules (advanced)

| Module | Purpose |
|---|---|
| `mpl_brandpacker.pyplot` | Branded drop-in for `matplotlib.pyplot` |
| `mpl_brandpacker.pandas` | `use_for_pandas()` for `df.plot()` |
| `mpl_brandpacker.patcher` | `patch_method()`, `MethodProxy` |
| `mpl_brandpacker.style` | `register_stylesheet()` |
| `mpl_brandpacker.utils` | `get_text_bbox()`, `separate_kwargs()` |

## How it works

`configure()` builds two functions — `make_fig(fig)` and `make_ax(ax)` — that patch matplotlib objects using Python's descriptor protocol. When you `import my_brand.pyplot as plt`, three pyplot entry points are intercepted:

- `figure()` → patches the new figure + wraps its axes creation methods
- `gcf()` → patches the current figure
- `gca()` → patches the current axes

All other pyplot functions (`subplots`, `show`, `savefig`, etc.) work unchanged because they internally call `figure()` or `gcf()`.

## Template

See [mpl-brandpacker-template](../mpl-brandpacker-template/) for a complete working example.
