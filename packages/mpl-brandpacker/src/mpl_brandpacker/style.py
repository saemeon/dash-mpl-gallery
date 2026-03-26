"""Module providing stylesheet loading machinery for corporate-design packages.

This module provides utilities for registering stylesheets and fonts with
matplotlib. Concrete implementations should call register_stylesheet() with
their own package path to make their .mplstyle files available.

To use in a concrete implementation::

    import mcd.style
    mcd.style.register_stylesheet(Path(__file__).parent.resolve())
    mcd.style.use("my_stylesheet_name")
"""

from pathlib import Path

import matplotlib.style.core
from matplotlib import font_manager
from matplotlib.style import (
    available,  # noqa F401
    context,  # noqa F401
    library,  # noqa F401
    reload_library,  # noqa F401
    use,  # noqa F401
)


def register_stylesheet(packagepath: Path) -> None:
    """Register stylesheets and fonts from a package directory.

    Looks for:
    - ``<packagepath>/data/fonts/`` — font files to add to matplotlib
    - ``<packagepath>/`` — .mplstyle files to add to the style library

    Parameters
    ----------
    packagepath : Path
        Root path of the package whose styles and fonts should be registered.
    """
    font_dirs = [Path(packagepath, "data", "fonts")]
    font_files = font_manager.findSystemFonts(fontpaths=font_dirs)
    for font_file in font_files:
        font_manager.fontManager.addfont(font_file)

    matplotlib.style.core.USER_LIBRARY_PATHS += [packagepath]
    matplotlib.style.core.reload_library()
