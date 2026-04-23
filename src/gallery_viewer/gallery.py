"""Gallery — configurable Dash dashboard for browsing versioned scripts.

Supports multiple named plots, each backed by its own ``StorageBackend``.

Usage::

    from gallery_viewer import Gallery, FileSystemBackend

    # Single plot
    gallery = Gallery(backend=FileSystemBackend("./my_project"))

    # Multiple plots (auto-discovered from subdirectories)
    gallery = Gallery(backends=FileSystemBackend.discover("./all_plots"))

    # From a config file (recommended for multi-plot galleries)
    gallery = Gallery.from_config("gallery.json")

    gallery.run()
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dash_table, dcc, html

from gallery_viewer._types import OutputItem, ScriptSections
from gallery_viewer.backend import FileSystemBackend, StorageBackend
from gallery_viewer.config import (
    add_plot_to_config,
    backends_from_config,
    load_config,
    save_config,
)
from gallery_viewer.params import detect_params

# ---------------------------------------------------------------------------
# Optional: dash-ace for syntax-highlighted editor
# ---------------------------------------------------------------------------

try:
    import dash_ace  # noqa: F401  # type: ignore[import-not-found]  # ty:ignore[unresolved-import]

    _HAS_ACE = True
except ImportError:
    _HAS_ACE = False


# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_MONOSPACE = {"fontFamily": "monospace", "fontSize": "13px"}
_CONSOLE_STYLE = {
    **_MONOSPACE,
    "backgroundColor": "#1a1a1a",
    "color": "#d4d4d4",
    "padding": "10px",
    "borderRadius": "4px",
    "minHeight": "80px",
    "whiteSpace": "pre-wrap",
    "overflowY": "auto",
    "maxHeight": "200px",
}
_SECTION_LABEL = {
    "color": "#888",
    "fontSize": "11px",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "marginBottom": "2px",
    "marginTop": "10px",
}


def _editor_style(height: str = "200px") -> dict:
    return {
        **_MONOSPACE,
        "width": "100%",
        "height": height,
        "backgroundColor": "#1e1e1e",
        "color": "#d4d4d4",
        "border": "1px solid #444",
        "borderRadius": "4px",
        "padding": "10px",
        "resize": "vertical",
    }


def _make_editor(id: str, height: str = "200px") -> Any:
    """Create a code editor — DashAceEditor if available, else dcc.Textarea."""
    if _HAS_ACE:
        return dash_ace.DashAceEditor(
            id=id,
            value="",
            mode="python",
            theme="monokai",
            fontSize=13,
            style={"width": "100%", "height": height},
            enableBasicAutocompletion=False,
            enableLiveAutocompletion=False,
        )
    return dcc.Textarea(id=id, style=_editor_style(height))


# ---------------------------------------------------------------------------
# Sidebar tree helpers
# ---------------------------------------------------------------------------

_MAX_TREE_DEPTH = 4


def _build_sidebar_tree(names: list[str]) -> dict:
    """Parse slash-delimited names into a nested tree.

    Returns a dict where string keys are group names and ``"__leaves__"``
    holds a list of full backend keys that are direct children at that level.

    Example::

        _build_sidebar_tree(["a", "g/x", "g/y", "g/sub/z"])
        # => {"__leaves__": ["a"],
        #     "g": {"__leaves__": ["g/x", "g/y"],
        #            "sub": {"__leaves__": ["g/sub/z"]}}}
    """
    tree: dict = {"__leaves__": []}
    for name in names:
        parts = name.split("/")
        if len(parts) > _MAX_TREE_DEPTH:
            parts = parts[: _MAX_TREE_DEPTH - 1] + ["/".join(parts[_MAX_TREE_DEPTH - 1 :])]
        node = tree
        for segment in parts[:-1]:
            if segment not in node:
                node[segment] = {"__leaves__": []}
            node = node[segment]
        node["__leaves__"].append(name)
    return tree


def _render_tree_node(
    tree: dict,
    collapsed: list[str],
    active_plot: str | None,
    descriptions: dict[str, str],
    depth: int = 0,
    path_prefix: str = "",
) -> list:
    """Recursively render a sidebar tree node into Dash components."""
    children = []
    indent = depth * 14

    # Render sub-groups first, then leaves
    group_keys = [k for k in tree if k != "__leaves__"]
    for group in group_keys:
        group_path = f"{path_prefix}/{group}" if path_prefix else group
        is_collapsed = group_path in collapsed
        chevron = "\u25b8" if is_collapsed else "\u25be"
        children.append(
            html.Div(
                [
                    html.Span(chevron, style={"marginRight": "6px", "fontSize": "10px"}),
                    html.Span(
                        group.replace("_", " ").title(),
                        style={"fontSize": "12px", "color": "#aaa"},
                    ),
                ],
                id={"type": "gv-tree-group", "index": group_path},
                n_clicks=0,
                style={
                    "padding": "5px 8px",
                    "paddingLeft": f"{indent + 8}px",
                    "cursor": "pointer",
                    "userSelect": "none",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.04em",
                    "marginBottom": "2px",
                },
            )
        )
        if not is_collapsed:
            children.extend(
                _render_tree_node(
                    tree[group],
                    collapsed,
                    active_plot,
                    descriptions,
                    depth=depth + 1,
                    path_prefix=group_path,
                )
            )

    # Render leaves
    for name in tree.get("__leaves__", []):
        label = name.rsplit("/", 1)[-1].replace("_", " ").title()
        desc = descriptions.get(name, "")
        is_active = name == active_plot
        children.append(
            html.Div(
                [
                    html.Div(
                        label,
                        style={
                            "fontWeight": "bold",
                            "fontSize": "13px",
                            "color": "#e0e0e0",
                        },
                    ),
                    html.Div(desc, style={"fontSize": "11px", "color": "#888"})
                    if desc
                    else None,
                ],
                id={"type": "gv-nav-item", "index": name},
                n_clicks=0,
                style={
                    "padding": "8px 10px",
                    "paddingLeft": f"{indent + 10}px",
                    "marginBottom": "4px",
                    "borderRadius": "4px",
                    "cursor": "pointer",
                    "backgroundColor": "#3a3a3a" if is_active else "#2a2a2a",
                    "borderLeft": "3px solid #5b9bd5"
                    if is_active
                    else "3px solid transparent",
                },
            )
        )
    return children


# ---------------------------------------------------------------------------
# Gallery
# ---------------------------------------------------------------------------


class Gallery:
    """Configurable gallery dashboard with multi-plot support.

    Provides a Dash UI for browsing, editing, and running versioned scripts.
    Supports multi-output rendering (matplotlib PNGs, Plotly JSON, DataFrames),
    version diff labels showing parameter changes between versions, standalone
    ``.py`` export, author metadata on save, read-only mode via a script
    visibility toggle, and a "New Date" button for data dates lacking scripts.

    Parameters
    ----------
    backend :
        Single storage backend (for one-plot galleries).
    backends :
        Dict of ``{plot_name: StorageBackend}`` for multi-plot galleries.
        Mutually exclusive with ``backend``.
    title :
        Dashboard title shown in the header.
    theme :
        A ``dbc.themes`` constant.  Defaults to ``SLATE`` (dark).
    export_fn :
        Optional ``(bytes) -> bytes`` that post-processes a plot image.
    extra_controls :
        Optional Dash component(s) inserted below the dropdowns.
    """

    def __init__(
        self,
        backend: StorageBackend | None = None,
        backends: dict[str, StorageBackend] | None = None,
        title: str = "Gallery Viewer",
        theme: Any = None,
        export_fn: Callable[[bytes], bytes] | None = None,
        extra_controls: Any = None,
        config_path: str | Path | None = None,
    ):
        if backends is not None:
            self.backends = backends
        elif backend is not None:
            self.backends = {"default": backend}
        else:
            self.backends = {"default": FileSystemBackend(".")}

        self.title = title
        self._config_path = Path(config_path) if config_path else None
        self.theme = theme or dbc.themes.SLATE
        self.export_fn = export_fn
        self.extra_controls = extra_controls
        self._multi = len(self.backends) > 1

        self._app: dash.Dash | None = None

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        export_fn: Callable[[bytes], bytes] | None = None,
        extra_controls: Any = None,
        **backend_kwargs,
    ) -> Gallery:
        """Create a Gallery from a ``gallery.json`` config file.

        Parameters
        ----------
        config_path :
            Path to the JSON config file.
        export_fn :
            Optional post-processing function for exports.
        **backend_kwargs :
            Extra kwargs forwarded to each ``FileSystemBackend()``.
        """
        config_path = Path(config_path)
        config = load_config(config_path)
        base_dir = config_path.parent
        backends = backends_from_config(config, base_dir=base_dir, **backend_kwargs)

        if not backends:
            # Empty config — start with no plots; user adds via dashboard
            pass

        return cls(
            backends=backends or {},
            title=config.get("title", "Gallery Viewer"),
            export_fn=export_fn,
            extra_controls=extra_controls,
            config_path=config_path,
        )

    @property
    def app(self) -> dash.Dash:
        if self._app is None:
            self._app = self._build_app()
        return self._app

    def run(
        self, debug: bool = False, host: str = "127.0.0.1", port: int = 8050, **kwargs
    ):
        self.app.run(debug=debug, host=host, port=port, **kwargs)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_app(self) -> dash.Dash:
        app = dash.Dash(
            __name__,
            external_stylesheets=[self.theme],
            title=self.title,
        )
        app.layout = self._layout()
        self._register_callbacks(app)
        return app

    def _layout(self) -> dbc.Container:
        extra = self.extra_controls or html.Div()
        plot_names = list(self.backends.keys())

        export_btn = []
        if self.export_fn is not None:
            export_btn = [
                dbc.Button(
                    "Export",
                    id="export-btn",
                    color="warning",
                    size="sm",
                    n_clicks=0,
                    style={"marginLeft": "8px"},
                ),
                dcc.Download(id="export-download"),
            ]

        # "Add Plot" button (only when config file is used)
        add_plot_btn = []
        if self._config_path:
            add_plot_btn = [
                dbc.Button(
                    "+ Add Plot",
                    id="gv-add-plot-btn",
                    color="secondary",
                    size="sm",
                    n_clicks=0,
                    style={"width": "100%", "marginTop": "8px", "marginBottom": "8px"},
                ),
                dbc.Modal(
                    [
                        dbc.ModalHeader("Add New Plot"),
                        dbc.ModalBody(
                            [
                                dbc.Label("Plot name"),
                                dbc.Input(
                                    id="gv-add-plot-name",
                                    type="text",
                                    placeholder="e.g. revenue_chart",
                                ),
                                dbc.Label("Description", class_name="mt-2"),
                                dbc.Input(
                                    id="gv-add-plot-desc",
                                    type="text",
                                    placeholder="Optional description",
                                ),
                            ]
                        ),
                        dbc.ModalFooter(
                            [
                                dbc.Button(
                                    "Create",
                                    id="gv-add-plot-submit",
                                    color="primary",
                                    size="sm",
                                ),
                                dbc.Button(
                                    "Cancel",
                                    id="gv-add-plot-cancel",
                                    color="secondary",
                                    size="sm",
                                ),
                            ]
                        ),
                    ],
                    id="gv-add-plot-modal",
                    is_open=False,
                ),
                html.Div(
                    id="gv-add-plot-feedback",
                    style={"fontSize": "12px", "color": "#aaa"},
                ),
            ]

        return dbc.Container(
            fluid=True,
            style={"padding": "16px"},
            children=[
                dbc.Row(
                    dbc.Col(
                        html.H3(
                            self.title,
                            style={"color": "#e0e0e0", "marginBottom": "12px"},
                        ),
                    )
                ),
                dbc.Row(
                    [
                        # ── GALLERY SIDEBAR ───────────────────────────────
                        dbc.Col(
                            width=2,
                            children=[
                                html.Label(
                                    "Plots",
                                    style={
                                        "color": "#aaa",
                                        "fontSize": "12px",
                                        "textTransform": "uppercase",
                                        "letterSpacing": "0.06em",
                                        "marginBottom": "8px",
                                    },
                                ),
                                dcc.Input(
                                    id="gv-search",
                                    type="text",
                                    placeholder="Filter...",
                                    debounce=False,
                                    style={
                                        "width": "100%",
                                        "marginBottom": "8px",
                                        "backgroundColor": "#3a3a3a",
                                        "color": "#d4d4d4",
                                        "border": "1px solid #555",
                                        "borderRadius": "4px",
                                        "padding": "4px 8px",
                                        "fontSize": "12px",
                                    },
                                ),
                                html.Div(
                                    id="gv-gallery-sidebar",
                                    style={
                                        "overflowY": "auto",
                                        "maxHeight": "calc(100vh - 220px)",
                                        "paddingRight": "4px",
                                    },
                                ),
                                *add_plot_btn,
                                # Hidden store for selected plot name
                                dcc.Store(
                                    id="gv-plot-select",
                                    data=plot_names[0] if plot_names else None,
                                ),
                                dcc.Store(id="gv-gallery-items"),
                                dcc.Store(id="gv-sidebar-collapsed", data=[]),
                            ],
                        ),
                        # ── EDITOR ────────────────────────────────────────
                        dbc.Col(
                            width=4,
                            children=[
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            width=5,
                                            children=[
                                                html.Label(
                                                    "Date",
                                                    style={
                                                        "color": "#aaa",
                                                        "fontSize": "12px",
                                                    },
                                                ),
                                                dcc.Dropdown(
                                                    id="gv-date",
                                                    placeholder="Select date...",
                                                    clearable=False,
                                                    style={"marginBottom": "6px"},
                                                ),
                                            ],
                                        ),
                                        dbc.Col(
                                            width=5,
                                            children=[
                                                html.Label(
                                                    "Version",
                                                    style={
                                                        "color": "#aaa",
                                                        "fontSize": "12px",
                                                    },
                                                ),
                                                dcc.Dropdown(
                                                    id="gv-version",
                                                    clearable=False,
                                                    style={"marginBottom": "6px"},
                                                ),
                                            ],
                                        ),
                                        dbc.Col(
                                            width=1,
                                            children=[
                                                html.Label(
                                                    "\u00a0", style={"fontSize": "12px"}
                                                ),
                                                dbc.Button(
                                                    "\u21bb",
                                                    id="gv-refresh-btn",
                                                    color="secondary",
                                                    size="sm",
                                                    n_clicks=0,
                                                    style={
                                                        "width": "100%",
                                                        "fontSize": "16px",
                                                        "padding": "4px",
                                                    },
                                                    title="Refresh dates & versions",
                                                ),
                                            ],
                                        ),
                                        dbc.Col(
                                            width=1,
                                            children=[
                                                html.Label(
                                                    "\u00a0", style={"fontSize": "12px"}
                                                ),
                                                dbc.Button(
                                                    "+",
                                                    id="gv-new-date-btn",
                                                    color="secondary",
                                                    size="sm",
                                                    n_clicks=0,
                                                    style={
                                                        "width": "100%",
                                                        "fontSize": "16px",
                                                        "padding": "4px",
                                                    },
                                                    title="Start chart for new data date",
                                                ),
                                            ],
                                        ),
                                    ]
                                ),
                                extra,
                                html.Div(
                                    id="gv-param-fields", style={"marginBottom": "4px"}
                                ),
                                html.Div(
                                    id="gv-update-script-row",
                                    style={"marginBottom": "4px"},
                                ),
                                html.Div(
                                    id="gv-version-diff",
                                    style={
                                        "fontSize": "11px",
                                        "color": "#8cb4d5",
                                        "marginBottom": "4px",
                                        "fontFamily": "monospace",
                                    },
                                ),
                                html.Div(
                                    [
                                        html.Span(
                                            "Script",
                                            style={
                                                **_SECTION_LABEL,
                                                "display": "inline",
                                                "marginTop": "0",
                                            },
                                        ),
                                        dbc.Switch(
                                            id="gv-show-script",
                                            label="",
                                            value=False,
                                            style={
                                                "display": "inline-block",
                                                "marginLeft": "8px",
                                                "verticalAlign": "middle",
                                            },
                                        ),
                                    ],
                                    style={
                                        "display": "flex",
                                        "alignItems": "center",
                                        "marginBottom": "2px",
                                    },
                                ),
                                html.Div(
                                    _make_editor("gv-editor-script", "500px"),
                                    id="gv-editor-wrapper",
                                    style={"display": "none"},
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            dbc.Button(
                                                [
                                                    dbc.Spinner(
                                                        size="sm",
                                                        spinner_style={
                                                            "marginRight": "6px"
                                                        },
                                                        id="gv-run-spinner",
                                                    ),
                                                    "RUN",
                                                ],
                                                id="gv-run-btn",
                                                color="success",
                                                size="sm",
                                                n_clicks=0,
                                                style={"width": "100%"},
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Update Script",
                                                id="gv-update-script-btn",
                                                color="secondary",
                                                size="sm",
                                                n_clicks=0,
                                                style={"width": "100%"},
                                                title="Write current parameter values into the script",
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Save Version",
                                                id="gv-save-btn",
                                                color="primary",
                                                size="sm",
                                                n_clicks=0,
                                                style={"width": "100%"},
                                            ),
                                            width=3,
                                        ),
                                        dbc.Col(
                                            dbc.Button(
                                                "Export .py",
                                                id="gv-export-script-btn",
                                                color="info",
                                                size="sm",
                                                n_clicks=0,
                                                outline=True,
                                                style={"width": "100%"},
                                                title="Download as standalone Python script",
                                            ),
                                            width=3,
                                        ),
                                    ],
                                    style={"marginTop": "8px", "marginBottom": "6px"},
                                ),
                                html.Label(
                                    "Console",
                                    style={"color": "#aaa", "fontSize": "12px"},
                                ),
                                html.Div(id="gv-console", style=_CONSOLE_STYLE),
                                dbc.Modal(
                                    [
                                        dbc.ModalHeader("Save New Version"),
                                        dbc.ModalBody(
                                            [
                                                html.P(
                                                    "The script and plot will be saved to disk.",
                                                    style={"marginBottom": "8px"},
                                                ),
                                                dbc.Label(
                                                    "Author (optional)",
                                                    style={"fontSize": "12px"},
                                                ),
                                                dbc.Input(
                                                    id="gv-save-author",
                                                    type="text",
                                                    placeholder="e.g. Alice",
                                                    size="sm",
                                                ),
                                            ]
                                        ),
                                        dbc.ModalFooter(
                                            [
                                                dbc.Button(
                                                    "Save",
                                                    id="gv-confirm-save-ok",
                                                    color="primary",
                                                    size="sm",
                                                ),
                                                dbc.Button(
                                                    "Cancel",
                                                    id="gv-confirm-save-cancel",
                                                    color="secondary",
                                                    size="sm",
                                                ),
                                            ]
                                        ),
                                    ],
                                    id="gv-save-modal",
                                    is_open=False,
                                ),
                            ],
                        ),
                        # ── PREVIEW ───────────────────────────────────────
                        dbc.Col(
                            width=6,
                            children=[
                                html.Div(
                                    [
                                        html.Label(
                                            "Plot",
                                            style={"color": "#aaa", "fontSize": "12px"},
                                        ),
                                        *export_btn,
                                    ],
                                    style={
                                        "display": "flex",
                                        "alignItems": "center",
                                        "marginBottom": "4px",
                                    },
                                ),
                                dcc.Loading(
                                    type="circle",
                                    color="#aaa",
                                    children=html.Div(
                                        id="gv-plot-panel",
                                        style={
                                            "backgroundColor": "#2a2a2a",
                                            "borderRadius": "4px",
                                            "padding": "8px",
                                            "minHeight": "300px",
                                            "display": "flex",
                                            "alignItems": "center",
                                            "justifyContent": "center",
                                            "marginBottom": "12px",
                                        },
                                        children=_no_plot(),
                                    ),
                                ),
                                html.Label(
                                    "Data (first 50 rows)",
                                    style={"color": "#aaa", "fontSize": "12px"},
                                ),
                                html.Div(
                                    id="gv-data-panel",
                                    style={
                                        "overflowX": "auto",
                                        "maxHeight": "300px",
                                        "overflowY": "auto",
                                    },
                                    children=_no_data(),
                                ),
                            ],
                        ),
                    ]
                ),
                dcc.Store(id="gv-plot-bytes-store"),
                # Track the last-loaded script text for dirty detection
                dcc.Store(id="gv-clean-script-store"),
                dcc.ConfirmDialog(
                    id="gv-confirm-navigate",
                    message="You have unsaved changes. Continue without saving?",
                ),
                # Export standalone script
                dcc.Download(id="gv-export-script-download"),
            ],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_backend(self, plot_name: str | None) -> StorageBackend:
        """Resolve plot name to backend, fallback to first."""
        if plot_name and plot_name in self.backends:
            return self.backends[plot_name]
        return next(iter(self.backends.values()))

    def _build_plot_names(self) -> list[str]:
        """Return current plot names."""
        return list(self.backends.keys())

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _register_callbacks(self, app: dash.Dash):
        # -- Render sidebar nav list (tree-aware) --
        @app.callback(
            Output("gv-gallery-sidebar", "children"),
            Input("gv-gallery-items", "data"),
            Input("gv-search", "value"),
            Input("gv-plot-select", "data"),
            Input("gv-sidebar-collapsed", "data"),
        )
        def render_sidebar(_, search, active_plot, collapsed):
            names = self._build_plot_names()
            if search and search.strip():
                q = search.lower()
                names = [n for n in names if q in n.lower()]
            if not names:
                return html.Span("No plots", style={"color": "#666"})
            # Build description lookup
            descriptions: dict[str, str] = {}
            if self._config_path:
                config = load_config(self._config_path)
                plots_cfg = config.get("plots", {})
                for name in names:
                    desc = plots_cfg.get(name, {}).get("description", "")
                    if desc:
                        descriptions[name] = desc
            tree = _build_sidebar_tree(names)
            return _render_tree_node(
                tree, collapsed or [], active_plot, descriptions
            )

        # -- Toggle group collapse/expand --
        @app.callback(
            Output("gv-sidebar-collapsed", "data"),
            Input({"type": "gv-tree-group", "index": ALL}, "n_clicks"),
            State("gv-sidebar-collapsed", "data"),
            prevent_initial_call=True,
        )
        def toggle_group(n_clicks_list, collapsed):
            if not any(n_clicks_list):
                return dash.no_update
            triggered = ctx.triggered_id
            if triggered is None:
                return dash.no_update
            group_path = triggered["index"]
            collapsed = list(collapsed or [])
            if group_path in collapsed:
                collapsed.remove(group_path)
            else:
                collapsed.append(group_path)
            return collapsed

        # -- Click nav item → select plot, load its dates --
        @app.callback(
            Output("gv-plot-select", "data", allow_duplicate=True),
            Output("gv-date", "options"),
            Output("gv-date", "value"),
            Input({"type": "gv-nav-item", "index": dash.ALL}, "n_clicks"),
            prevent_initial_call=True,
        )
        def nav_click(n_clicks_list):
            if not any(n_clicks_list):
                return dash.no_update, dash.no_update, dash.no_update
            triggered = ctx.triggered_id
            if triggered is None:
                return dash.no_update, dash.no_update, dash.no_update
            plot_name = triggered["index"]
            backend = self._get_backend(plot_name)
            dates = backend.list_dates()
            opts = [{"label": d, "value": d} for d in dates]
            return plot_name, opts, (dates[0] if dates else None)

        # -- Also load dates on initial plot select --
        @app.callback(
            Output("gv-date", "options", allow_duplicate=True),
            Output("gv-date", "value", allow_duplicate=True),
            Input("gv-plot-select", "data"),
            prevent_initial_call="initial_duplicate",
        )
        def init_dates_for_plot(plot_name):
            if not plot_name:
                return [], None
            backend = self._get_backend(plot_name)
            dates = backend.list_dates()
            opts = [{"label": d, "value": d} for d in dates]
            return opts, (dates[0] if dates else None)

        # -- Refresh button → reload dates + versions for current plot --
        @app.callback(
            Output("gv-date", "options", allow_duplicate=True),
            Output("gv-date", "value", allow_duplicate=True),
            Output("gv-version", "options", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Input("gv-refresh-btn", "n_clicks"),
            State("gv-plot-select", "data"),
            State("gv-date", "value"),
            prevent_initial_call=True,
        )
        def refresh_dates(n_clicks, plot_name, current_date):
            if not plot_name:
                return [], None, [], None
            backend = self._get_backend(plot_name)
            dates = backend.list_dates()
            date_opts = [{"label": d, "value": d} for d in dates]
            # Keep current date if it still exists, otherwise pick newest
            date_val = (
                current_date if current_date in dates else (dates[0] if dates else None)
            )
            versions = backend.list_versions(date_val) if date_val else []
            ver_opts = [{"label": f"v{v}", "value": v} for v in versions]
            ver_val = versions[-1] if versions else None
            return date_opts, date_val, ver_opts, ver_val

        # -- Update version dropdown when date changes --
        @app.callback(
            Output("gv-version", "options"),
            Output("gv-version", "value", allow_duplicate=True),
            Input("gv-date", "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def update_versions(date, plot_name):
            if not date:
                return [], None
            backend = self._get_backend(plot_name)
            versions = backend.list_versions(date)
            opts = [{"label": f"v{v}", "value": v} for v in versions]
            return opts, versions[-1] if versions else None

        # -- Load script + data + plot + detect params --
        @app.callback(
            Output("gv-editor-script", "value"),
            Output("gv-param-fields", "children"),
            Output("gv-data-panel", "children"),
            Output("gv-plot-panel", "children"),
            Output("gv-plot-bytes-store", "data"),
            Output("gv-clean-script-store", "data"),
            Input("gv-date", "value"),
            Input("gv-version", "value"),
            State("gv-plot-select", "data"),
        )
        def load_version(date, version, plot_name):
            if not date or not version:
                return (*(dash.no_update,) * 6,)
            backend = self._get_backend(plot_name)
            version = str(version)
            sections = backend.load_script(date, str(version))
            script_text = sections.to_text()

            # Detect configurable params from the Configurator section
            param_fields = _build_param_fields(sections.configurator)

            data_children = _data_table(backend.load_data(date))
            plot_bytes = backend.load_plot(date, str(version))
            plot_children = _plot_img(plot_bytes)
            b64 = base64.b64encode(plot_bytes).decode() if plot_bytes else None
            return script_text, param_fields, data_children, plot_children, b64, script_text

        # -- RUN button --
        @app.callback(
            Output("gv-console", "children"),
            Output("gv-plot-panel", "children", allow_duplicate=True),
            Output("gv-plot-bytes-store", "data", allow_duplicate=True),
            Input("gv-run-btn", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def run_script(n_clicks, script_code, param_values, plot_name):
            if not script_code:
                return "Nothing to run.", _no_plot(), None
            backend = self._get_backend(plot_name)
            sections = ScriptSections.from_text(script_code)

            # Build injection vars from param form fields
            inject = _param_values_to_inject(sections.configurator, param_values)

            result = backend.run_preview(sections, inject_vars=inject)
            console = result.output
            if not result.success:
                console += f"\n--- ERROR ---\n{result.error}"
            plot_children = _render_outputs(result.items)
            b64 = (
                base64.b64encode(result.plot_bytes).decode()
                if result.plot_bytes
                else None
            )
            return console or "(no output)", plot_children, b64

        # -- SAVE: step 1 — open modal --
        @app.callback(
            Output("gv-save-modal", "is_open"),
            Input("gv-save-btn", "n_clicks"),
            Input("gv-confirm-save-ok", "n_clicks"),
            Input("gv-confirm-save-cancel", "n_clicks"),
            State("gv-save-modal", "is_open"),
            prevent_initial_call=True,
        )
        def toggle_save_modal(n_save, n_ok, n_cancel, is_open):
            trigger = ctx.triggered_id
            if trigger == "gv-save-btn":
                return True
            return False

        # -- SAVE: step 2 — actual save + refresh gallery --
        @app.callback(
            Output("gv-console", "children", allow_duplicate=True),
            Output("gv-plot-panel", "children", allow_duplicate=True),
            Output("gv-gallery-items", "data", allow_duplicate=True),
            Output("gv-date", "options", allow_duplicate=True),
            Output("gv-date", "value", allow_duplicate=True),
            Output("gv-version", "options", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Output("gv-editor-script", "value", allow_duplicate=True),
            Output("gv-clean-script-store", "data", allow_duplicate=True),
            Input("gv-confirm-save-ok", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            State("gv-plot-select", "data"),
            State("gv-date", "value"),
            State("gv-save-author", "value"),
            prevent_initial_call=True,
        )
        def save_version(n_clicks, script_code, param_values, plot_name, selected_date, author):
            if not script_code:
                return (
                    "Nothing to save.",
                    _no_plot(),
                    *(dash.no_update,) * 7,
                )

            from datetime import date as _date

            # Use selected date, fall back to today
            save_date = selected_date or _date.today().strftime("%Y%m%d")
            backend = self._get_backend(plot_name)

            sections = ScriptSections.from_text(script_code)

            # Apply form field values to the CONFIGURATOR section
            # so the saved script reflects the reviewer's changes
            if param_values:
                sections = _inject_params(sections, param_values)

            # Add author comment if provided
            if author and author.strip():
                sections = _add_author_comment(sections, author.strip())

            new_version = backend.save_version(save_date, sections)

            console = (
                f"Saved v{new_version}\n"
                f"  scripts/script_{save_date}_v{new_version}.py\n"
                f"  plots/plot_{save_date}_v{new_version}.png"
            )

            dates = backend.list_dates()
            date_opts = [{"label": d, "value": d} for d in dates]
            versions = backend.list_versions(save_date)
            ver_opts = [{"label": f"v{v}", "value": v} for v in versions]

            plot_bytes = backend.load_plot(save_date, str(new_version))
            plot_children = _plot_img(plot_bytes)

            # Update editor to show the saved script (with form values applied)
            updated_script = sections.to_text()

            # gallery-items triggers sidebar rebuild
            return (
                console,
                plot_children,
                self._build_plot_names(),
                date_opts,
                save_date,
                ver_opts,
                new_version,
                updated_script,
                updated_script,  # update clean-script-store too
            )

        # -- Update Script from Parameters --
        @app.callback(
            Output("gv-editor-script", "value", allow_duplicate=True),
            Input("gv-update-script-btn", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            prevent_initial_call=True,
        )
        def update_script_from_params(n_clicks, script_code, param_values):
            if not script_code or not param_values:
                return dash.no_update
            sections = ScriptSections.from_text(script_code)
            sections = _inject_params(sections, param_values)
            return sections.to_text()

        # -- Show/hide Update Script button based on param fields --
        @app.callback(
            Output("gv-update-script-row", "children"),
            Input("gv-param-fields", "children"),
        )
        def toggle_update_script_visibility(param_fields):
            if param_fields:
                return html.Div(
                    "Use form fields above to tweak parameters, "
                    "then RUN to preview or Save Version to persist.",
                    style={"fontSize": "11px", "color": "#777", "marginTop": "2px"},
                )
            return None

        # -- Feature 1: Toggle script editor visibility --
        @app.callback(
            Output("gv-editor-wrapper", "style"),
            Input("gv-show-script", "value"),
        )
        def toggle_editor(show):
            if show:
                return {"display": "block"}
            return {"display": "none"}

        # -- Feature 2: Version diff label --
        @app.callback(
            Output("gv-version-diff", "children"),
            Input("gv-version", "value"),
            State("gv-date", "value"),
            State("gv-plot-select", "data"),
        )
        def show_version_diff(version, date, plot_name):
            if not date or not version:
                return ""
            version = str(version)
            if version == "1":
                return html.Span("v1 — initial version", style={"color": "#777"})
            backend = self._get_backend(plot_name)
            prev_version = str(int(version) - 1)
            current = backend.load_script(date, version)
            previous = backend.load_script(date, prev_version)
            diff = _diff_configurator(previous.configurator, current.configurator)
            if not diff:
                return html.Span(
                    f"v{version} — no parameter changes from v{prev_version}",
                    style={"color": "#777"},
                )
            return html.Span(
                f"v{version} — " + ", ".join(diff),
                style={"color": "#8cb4d5"},
            )

        # -- Feature 3: New Date button (detect uncharted data) --
        @app.callback(
            Output("gv-date", "options", allow_duplicate=True),
            Output("gv-date", "value", allow_duplicate=True),
            Output("gv-version", "options", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Output("gv-editor-script", "value", allow_duplicate=True),
            Output("gv-param-fields", "children", allow_duplicate=True),
            Output("gv-console", "children", allow_duplicate=True),
            Output("gv-clean-script-store", "data", allow_duplicate=True),
            Input("gv-new-date-btn", "n_clicks"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def new_date_from_data(n_clicks, plot_name):
            if not plot_name:
                return (*(dash.no_update,) * 8,)
            backend = self._get_backend(plot_name)
            uncharted = _find_uncharted_dates(backend)
            if not uncharted:
                return (
                    *(dash.no_update,) * 6,
                    "No new data dates found without scripts.",
                    dash.no_update,
                )
            new_date = uncharted[0]  # newest uncharted date
            # Use copy-from-version (feature 4): latest version of most recent date
            template = _template_from_latest(backend, new_date)
            script_text = template.to_text()
            param_fields = _build_param_fields(template.configurator)
            dates = backend.list_dates() + [new_date]
            dates = sorted(set(dates), reverse=True)
            date_opts = [{"label": d, "value": d} for d in dates]
            return (
                date_opts,
                new_date,
                [{"label": "v1 (new)", "value": "1"}],
                "1",
                script_text,
                param_fields,
                f"New date {new_date} — edit and Save Version to create v1.",
                script_text,
            )

        # -- Feature 5: Dirty flag — store clean script on load --
        # (The clean-script-store is also updated in save_version above)

        # -- Feature 5: Confirm before navigating with unsaved changes --
        # We intercept nav_click and date/version changes via a clientside check.
        # For simplicity, we use a Store-based approach: compare editor vs clean store.

        # -- Feature 8: Export standalone script --
        @app.callback(
            Output("gv-export-script-download", "data"),
            Input("gv-export-script-btn", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            State("gv-date", "value"),
            State("gv-version", "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def export_standalone(n_clicks, script_code, param_values, date, version, plot_name):
            if not script_code:
                return dash.no_update
            sections = ScriptSections.from_text(script_code)
            backend = self._get_backend(plot_name)
            # Build inject vars: params + date/version/paths
            inject = _param_values_to_inject(sections.configurator, param_values) or {}
            inject["date"] = date or "unknown"
            inject["version"] = int(version) if version else 0
            if hasattr(backend, "base_dir"):
                inject["BASE_DIR"] = str(backend.base_dir)  # type: ignore[union-attr]
                inject["PLOT_OUTPUT_PATH"] = str(
                    backend.plots_dir / f"plot_{date}_v{version}.png"  # type: ignore[union-attr]
                )
            standalone = sections.to_full(inject_vars=inject)
            filename = f"script_{date}_v{version}.py" if date and version else "script.py"
            return dcc.send_string(standalone, filename)

        # -- Export (only if export_fn provided) --
        if self.export_fn is not None:

            @app.callback(
                Output("export-download", "data"),
                Input("export-btn", "n_clicks"),
                State("gv-plot-bytes-store", "data"),
                prevent_initial_call=True,
            )
            def export_plot(n_clicks, b64_data):
                if not b64_data:
                    return dash.no_update
                raw_bytes = base64.b64decode(b64_data)
                exported = self.export_fn(raw_bytes)  # type: ignore[misc]  # ty:ignore[call-non-callable]
                return dcc.send_bytes(exported, "exported_chart.png")

        # -- Add Plot (only if config file is used) --
        if self._config_path:

            @app.callback(
                Output("gv-add-plot-modal", "is_open"),
                Input("gv-add-plot-btn", "n_clicks"),
                Input("gv-add-plot-cancel", "n_clicks"),
                Input("gv-add-plot-submit", "n_clicks"),
                State("gv-add-plot-modal", "is_open"),
                prevent_initial_call=True,
            )
            def toggle_add_plot_modal(n_open, n_cancel, n_submit, is_open):
                trigger = ctx.triggered_id
                return trigger == "gv-add-plot-btn"

            @app.callback(
                Output("gv-add-plot-feedback", "children"),
                Output("gv-plot-select", "data", allow_duplicate=True),
                Output("gv-gallery-items", "data", allow_duplicate=True),
                Input("gv-add-plot-submit", "n_clicks"),
                State("gv-add-plot-name", "value"),
                State("gv-add-plot-desc", "value"),
                prevent_initial_call=True,
            )
            def create_plot(n_clicks, name, desc):
                if not name or not name.strip():
                    return ("Please enter a plot name.", dash.no_update, dash.no_update)

                name = name.strip().replace(" ", "_").lower()
                config = load_config(self._config_path)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
                if name in config.get("plots", {}):
                    return (
                        f"Plot '{name}' already exists.",
                        dash.no_update,
                        dash.no_update,
                    )

                # Create directory + update config
                base = self._config_path.parent  # type: ignore[union-attr]  # ty:ignore[unresolved-attribute]
                plot_path = base / name
                add_plot_to_config(config, name, str(plot_path), description=desc or "")
                save_config(config, self._config_path)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]

                # Register new backend
                self.backends[name] = FileSystemBackend(plot_path)
                self._multi = len(self.backends) > 1

                # Trigger sidebar rebuild by updating gallery-items
                return f"Created '{name}'", name, self._build_plot_names()


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _inject_params(sections: ScriptSections, param_values: list) -> ScriptSections:
    """Inject parameter field values back into the Configurator section.

    Replaces the default values of typed assignments with the values
    from the UI input fields.
    """
    import re as _re

    params = detect_params(sections.configurator)
    if not params:
        return sections

    param_names = list(params.keys())
    new_lines = []
    for line in sections.configurator.splitlines():
        replaced = False
        for i, name in enumerate(param_names):
            if i < len(param_values) and param_values[i] is not None:
                # Match pattern: name: type = value
                pattern = _re.compile(rf"^({_re.escape(name)}\s*:\s*\w+\s*=\s*)(.+)$")
                m = pattern.match(line.strip())
                if m:
                    val = param_values[i]
                    if isinstance(val, str):
                        new_lines.append(f'{m.group(1)}"{val}"')
                    elif isinstance(val, bool):
                        new_lines.append(f"{m.group(1)}{val}")
                    else:
                        new_lines.append(f"{m.group(1)}{val}")
                    replaced = True
                    break
        if not replaced:
            new_lines.append(line)

    return ScriptSections(
        configurator="\n".join(new_lines),
        code=sections.code,
        save=sections.save,
    )


def _param_values_to_inject(
    configurator_source: str, param_values: list
) -> dict[str, object] | None:
    """Convert form field values to a dict for execution-time injection.

    Returns ``None`` if there are no params or no values to inject.
    """
    params = detect_params(configurator_source)
    if not params or not param_values:
        return None
    param_names = list(params.keys())
    inject: dict[str, object] = {}
    for i, name in enumerate(param_names):
        if i < len(param_values) and param_values[i] is not None:
            inject[name] = param_values[i]
    return inject or None


def _build_param_fields(configurator_source: str) -> list:
    """Detect typed params and build input fields for them."""
    params = detect_params(configurator_source)
    if not params:
        return []

    fields = []
    for name, spec in params.items():
        label = name.replace("_", " ").title()
        if spec.annotation is bool:
            field = dbc.Checkbox(
                id={"type": "gv-param", "name": name},
                label=label,
                value=bool(spec.default),
                style={"marginBottom": "4px"},
            )
        elif spec.annotation in (int, float):
            field = html.Div(
                [
                    html.Label(label, style={"color": "#aaa", "fontSize": "11px"}),
                    dbc.Input(
                        id={"type": "gv-param", "name": name},
                        type="number",
                        value=spec.default,
                        size="sm",
                        style={"marginBottom": "4px"},
                    ),
                ]
            )
        else:
            field = html.Div(
                [
                    html.Label(label, style={"color": "#aaa", "fontSize": "11px"}),
                    dbc.Input(
                        id={"type": "gv-param", "name": name},
                        type="text",
                        value=str(spec.default),
                        size="sm",
                        style={"marginBottom": "4px"},
                    ),
                ]
            )
        fields.append(field)

    if fields:
        fields.insert(0, html.Div("Parameters", style=_SECTION_LABEL))
    return fields


def _diff_configurator(old_source: str, new_source: str) -> list[str]:
    """Diff two CONFIGURATOR sections and return human-readable change strings.

    Compares detected parameters by name: reports added (``+name``),
    removed (``-name``), and changed (``name: old -> new``) values.
    """
    old_params = detect_params(old_source)
    new_params = detect_params(new_source)
    changes = []
    all_names = list(dict.fromkeys(list(old_params.keys()) + list(new_params.keys())))
    for name in all_names:
        old_val = old_params.get(name)
        new_val = new_params.get(name)
        if old_val is None and new_val is not None:
            changes.append(f"+{name}={new_val.default!r}")
        elif old_val is not None and new_val is None:
            changes.append(f"-{name}")
        elif old_val is not None and new_val is not None and old_val.default != new_val.default:
            changes.append(f"{name}: {old_val.default!r} \u2192 {new_val.default!r}")
    return changes


def _find_uncharted_dates(backend: StorageBackend) -> list[str]:
    """Find data dates that have no scripts yet (newest first)."""
    if not isinstance(backend, FileSystemBackend):
        return []
    data_dates: set[str] = set()
    if backend.data_dir.exists():
        for f in backend.data_dir.iterdir():
            m = backend._data_re.match(f.name)
            if m:
                data_dates.add(m.group("date"))
    script_dates: set[str] = set()
    if backend.scripts_dir.exists():
        for f in backend.scripts_dir.iterdir():
            m = backend._script_re.match(f.name)
            if m:
                script_dates.add(m.group("date"))
    uncharted = data_dates - script_dates
    return sorted(uncharted, reverse=True)


def _template_from_latest(backend: StorageBackend, new_date: str) -> ScriptSections:
    """Create a template for a new date by copying the latest version of the most recent date.

    Falls back to the starter template if no previous versions exist.
    """
    dates = backend.list_dates()
    for prev_date in dates:
        versions = backend.list_versions(prev_date)
        if versions and versions != ["1"]:
            # Has real scripts — use the latest
            sections = backend.load_script(prev_date, versions[-1])
            # Update the data loading date reference in CODE
            return ScriptSections(
                configurator=sections.configurator,
                code=sections.code.replace(f'"{prev_date}"', f'"{new_date}"'),
                save=sections.save,
            )
        elif versions == ["1"]:
            sections = backend.load_script(prev_date, "1")
            return ScriptSections(
                configurator=sections.configurator,
                code=sections.code.replace(f'"{prev_date}"', f'"{new_date}"'),
                save=sections.save,
            )
    return backend.starter_template(new_date)


def _add_author_comment(sections: ScriptSections, author: str) -> ScriptSections:
    """Add a '# Saved by: ...' comment at the top of the CONFIGURATOR or CODE section."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    comment = f"# Saved by: {author} ({timestamp})"
    if sections.configurator:
        return ScriptSections(
            configurator=comment + "\n" + sections.configurator,
            code=sections.code,
            save=sections.save,
        )
    return ScriptSections(
        configurator=sections.configurator,
        code=comment + "\n" + sections.code,
        save=sections.save,
    )


def _no_plot():
    return html.Span("No plot available", style={"color": "#666"})


def _no_data():
    return html.Span("No data loaded", style={"color": "#666"})


def _render_outputs(items: list[OutputItem]):
    """Render OutputItem list as Dash components.

    Maps each item by MIME type: ``image/png`` to ``html.Img``,
    ``application/vnd.plotly+json`` to ``dcc.Graph``, and ``text/csv``
    to ``dash_table.DataTable``.  Multiple outputs are stacked vertically.
    """
    if not items:
        return _no_plot()
    children = []
    for item in items:
        if item.mime == "image/png":
            b64 = base64.b64encode(item.data).decode()
            children.append(
                html.Img(
                    src=f"data:image/png;base64,{b64}",
                    style={"maxWidth": "100%", "maxHeight": "500px"},
                )
            )
        elif item.mime == "application/vnd.plotly+json":
            try:
                import plotly.io as pio  # type: ignore[import-not-found]  # ty:ignore[unresolved-import]

                fig = pio.from_json(item.data.decode())
                children.append(
                    dcc.Graph(
                        figure=fig,
                        style={"maxHeight": "500px"},
                        config={"displayModeBar": True},
                    )
                )
            except ImportError:
                children.append(
                    html.Pre(
                        "Plotly not installed — cannot render interactive figure.",
                        style={"color": "#e84133"},
                    )
                )
        elif item.mime == "text/csv":
            import io

            import pandas as pd

            df = pd.read_csv(io.BytesIO(item.data))
            children.append(_data_table(df))
    if not children:
        return _no_plot()
    if len(children) == 1:
        return children[0]
    return html.Div(children, style={"display": "flex", "flexDirection": "column", "gap": "12px"})


def _plot_img(plot_bytes: bytes | None):
    if not plot_bytes:
        return _no_plot()
    b64 = base64.b64encode(plot_bytes).decode()
    return html.Img(
        src=f"data:image/png;base64,{b64}",
        style={"maxWidth": "100%", "maxHeight": "500px"},
    )


def _data_table(df):
    if df is None:
        return _no_data()
    df = df.head(50)
    return dash_table.DataTable(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "#3a3a3a",
            "color": "#e0e0e0",
            "fontWeight": "bold",
            "fontFamily": "monospace",
            "fontSize": "12px",
        },
        style_cell={
            "backgroundColor": "#2a2a2a",
            "color": "#d4d4d4",
            "fontFamily": "monospace",
            "fontSize": "12px",
            "border": "1px solid #444",
            "padding": "4px 8px",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#252525"},
        ],
        page_size=50,
    )
