# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Page — ordered collection of interact panels assembled into a Dash app."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from dash import Dash, html

from dash_fn_interact._interact import interact as _interact

_THIS_MODULES = {"dash_fn_interact._page", "dash_fn_interact.page"}


def _caller_name() -> str:
    """Walk the call stack to find the first frame outside this library."""
    for info in inspect.stack():
        mod = info.frame.f_globals.get("__name__", "")
        if mod and mod not in _THIS_MODULES:
            return mod
    return "__main__"


def _in_jupyter() -> bool:
    """Return True when running inside a Jupyter kernel."""
    try:
        from IPython import get_ipython  # noqa: PLC0415
        return get_ipython().__class__.__name__ == "ZMQInteractiveShell"
    except (ImportError, AttributeError):
        return False


class Page:
    """Ordered collection of interact panels assembled into a Dash app.

    Build a multi-panel app by calling :meth:`interact` and :meth:`add` in
    order, then call :meth:`run` to launch — no manual ``app.layout`` wiring
    needed.

    Parameters
    ----------
    max_width :
        CSS ``max-width`` of the outer ``html.Div`` in pixels.  Defaults to 960.
    manual :
        Default value for the ``_manual`` argument of every :meth:`interact`
        call on this page.  ``True`` adds an *Apply* button to every panel.

    Examples
    --------
    ::

        page = Page(manual=True)

        page.H1("My App")

        @page.interact
        def sine_wave(amplitude: float = 1.0, frequency: float = 2.0):
            ...

        page.Hr()
        page.H2("Histogram")

        @page.interact(amplitude=(0.0, 3.0, 0.1))
        def histogram(n_samples: int = 500):
            ...

        page.run(debug=True)
    """

    def __init__(
        self,
        *,
        max_width: int = 960,
        manual: bool = False,
    ) -> None:
        self._max_width = max_width
        self._manual = manual
        self._divs: list[Any] = []

    # ------------------------------------------------------------------
    # Building blocks

    def interact(
        self,
        fn: Callable | None = None,
        *,
        _manual: bool | None = None,
        **kwargs: Any,
    ) -> html.Div | Callable:
        """Add an interact panel to the page.

        Identical signature to :func:`~dash_fn_interact.interact`.  Can be
        used as a direct call or as a decorator (with or without arguments).
        The resulting panel is appended to the page in call order.

        Parameters
        ----------
        fn :
            Callable whose signature drives the form.  When omitted a
            decorator is returned — useful for ``@page.interact(...)`` syntax.
        _manual :
            Override the page-level ``manual`` default for this panel only.
        **kwargs :
            Per-field shorthands forwarded to :func:`~dash_fn_interact.interact`.
        """
        effective_manual = self._manual if _manual is None else _manual

        if fn is None:
            def decorator(f: Callable) -> html.Div:
                return self.interact(f, _manual=_manual, **kwargs)
            return decorator

        panel = _interact(fn, _manual=effective_manual, **kwargs)
        self._divs.append(panel)
        return panel

    def add(self, *components: Any) -> None:
        """Append arbitrary Dash components to the page.

        Example::

            page.add(html.H2("Section"), html.Hr())
        """
        self._divs.extend(components)

    def __getattr__(self, name: str) -> Any:
        """Forward PascalCase attribute access to ``dash.html``.

        Allows ``page.H1("title")`` as shorthand for
        ``page.add(html.H1("title"))``.  Only fires when normal attribute
        lookup fails, so existing methods are never shadowed.
        """
        component_cls = getattr(html, name, None)
        if component_cls is not None:
            def _add(*args: Any, **kwargs: Any) -> None:
                self.add(component_cls(*args, **kwargs))
            return _add
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    # ------------------------------------------------------------------
    # Assembly

    def build_app(self, *, name: str | None = None) -> Dash:
        """Assemble and return a configured :class:`~dash.Dash` app.

        Parameters
        ----------
        name :
            Passed to ``Dash(name)``.  Defaults to the caller's ``__name__``
            resolved via the call stack.
        """
        if name is None:
            name = _caller_name()

        app = Dash(name)
        app.layout = html.Div(
            self._divs,
            style={
                "fontFamily": "sans-serif",
                "padding": "32px",
                "maxWidth": f"{self._max_width}px",
                "backgroundColor": "#ffffff",
                "color": "#1a1a1a",
            },
        )
        return app

    def _ipython_display_(self, **_: Any) -> None:
        """Auto-display the app when the page is the last expression in a cell."""
        self.run()

    def run(self, *, name: str | None = None, **kwargs: Any) -> None:
        """Build the app and start the Dash development server.

        When called inside a Jupyter notebook, ``jupyter_mode`` defaults to
        ``"inline"`` so the app renders as an iframe in the cell output.
        Pass ``jupyter_mode="external"`` or ``jupyter_mode="tab"`` to
        override.  Outside Jupyter, ``jupyter_mode`` is ignored.

        Parameters
        ----------
        name :
            Forwarded to :meth:`build_app`.
        **kwargs :
            Forwarded to ``app.run()`` (e.g. ``debug=True``, ``port=8050``,
            ``jupyter_mode="external"``).
        """
        if name is None:
            name = _caller_name()
        if _in_jupyter():
            kwargs.setdefault("jupyter_mode", "inline")
        self.build_app(name=name).run(**kwargs)
