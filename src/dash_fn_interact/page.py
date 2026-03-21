# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Implicit (Streamlit-style) convenience layer over :class:`~dash_fn_interact.Page`.

Inspired by ``matplotlib.pyplot``: a module-level singleton accumulates panels
in call order; :func:`run` renders everything — no ``Page`` object needed.

Usage::

    from dash_fn_interact.page import interact, add, run
    from dash import html

    add(html.H1("My App"))

    @interact
    def sine_wave(amplitude: float = 1.0, frequency: float = 2.0):
        ...

    run(debug=True)

For power users, :func:`get_page` exposes the current singleton (analogous to
``plt.gcf()``) and :func:`new_page` starts a fresh one (analogous to
``plt.figure()``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dash_fn_interact._page import Page

_current: Page = Page()


def _register_post_execute_hook() -> None:
    """Register an IPython post_execute hook that auto-displays the page.

    Fires after every cell.  If the current page has accumulated panels, it
    runs the app and resets to a fresh page — exactly like matplotlib's inline
    backend calling ``plt.show()`` automatically after each cell.

    Safe to call multiple times; the hook is registered at most once.
    """
    try:
        from IPython import get_ipython  # noqa: PLC0415
        ip = get_ipython()
        if ip is None or ip.__class__.__name__ != "ZMQInteractiveShell":
            return

        def _auto_display() -> None:
            if _current._divs:
                _current.run()
                new_page()

        ip.events.register("post_execute", _auto_display)
    except (ImportError, AttributeError):
        pass


_register_post_execute_hook()


# -- pyplot-style helpers --------------------------------------------------


def get_page() -> Page:
    """Return the current default :class:`~dash_fn_interact.Page` singleton.

    Analogous to ``matplotlib.pyplot.gcf()``.  Useful when you need to call
    a :class:`~dash_fn_interact.Page` method not exposed at module level.
    """
    return _current


def new_page(*, max_width: int = 960, manual: bool = False) -> Page:
    """Replace the default page with a fresh one and return it.

    Analogous to ``matplotlib.pyplot.figure()``.  Use this to start a new
    page in the same process (e.g. in tests or notebooks) without discarding
    the old one.

    Parameters
    ----------
    max_width, manual :
        Forwarded to :class:`~dash_fn_interact.Page`.
    """
    global _current
    _current = Page(max_width=max_width, manual=manual)
    return _current


# -- convenience wrappers --------------------------------------------------


def _attach_display(result: Any) -> Any:
    """Attach ``_ipython_display_`` to a panel or wrap a decorator to do so.

    When ``interact()`` is used as ``@interact(...)`` it returns a decorator
    rather than a panel — we wrap that decorator so the final panel also gets
    ``_ipython_display_`` attached.

    After displaying, the current page is replaced with a fresh one (analogous
    to matplotlib resetting ``plt.gcf()`` after ``plt.show()``), so the next
    cell's ``@interact`` calls start with a clean slate automatically.
    """
    if callable(result) and not hasattr(result, "_type"):
        # It's a decorator (the @interact(kwargs) case) — wrap it.
        def _wrapped(f: Callable) -> Any:
            return _attach_display(result(f))
        return _wrapped

    # It's a panel (html.Div) — run the page then reset to a fresh one.
    def _display_and_reset(**_: Any) -> None:
        _current.run()
        new_page()

    result._ipython_display_ = _display_and_reset
    return result


def interact(
    fn: Callable | None = None,
    *,
    _manual: bool | None = None,
    **kwargs: Any,
) -> Any:
    """Add an interact panel to the default page.

    In a Jupyter notebook the returned panel auto-displays the full page when
    it is the last expression in a cell — no ``run()`` call needed.

    See :meth:`~dash_fn_interact.Page.interact` for full documentation.
    """
    return _attach_display(_current.interact(fn, _manual=_manual, **kwargs))


def add(*components: Any) -> None:
    """Append arbitrary Dash components to the default page.

    See :meth:`~dash_fn_interact.Page.add` for full documentation.
    """
    _current.add(*components)


def run(**kwargs: Any) -> None:
    """Build and run the default page as a Dash app.

    See :meth:`~dash_fn_interact.Page.run` for full documentation.
    """
    _current.run(**kwargs)
