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
from datetime import datetime
from pathlib import Path
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dash_table, dcc, html

from gallery_viewer._types import OutputItem, RunResult, ScriptSections
from gallery_viewer.backend import FileSystemBackend, StorageBackend
from gallery_viewer.config import (
    add_plot_to_config,
    backends_from_config,
    load_config,
    save_config,
)
from gallery_viewer.params import detect_params, diff_configurator

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


# Conventional tag colors. Anything not listed falls back to "secondary"
# (grey). ``frozen`` reads as a warning even though it's purely informational
# — Save always creates a new version, so there's nothing to enforce.
_TAG_COLORS = {
    "published": "success",  # green
    "final": "primary",  # blue
    "frozen": "danger",  # red
    "draft": "secondary",  # grey
    "wip": "secondary",  # grey
}


def _tag_badge(tag: str) -> Any:
    """Render a single tag as a dbc.Badge with conventional color."""
    return dbc.Badge(
        tag,
        color=_TAG_COLORS.get(tag, "secondary"),
        pill=True,
        style={"marginRight": "4px", "fontSize": "10px"},
    )


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
            parts = parts[: _MAX_TREE_DEPTH - 1] + [
                "/".join(parts[_MAX_TREE_DEPTH - 1 :])
            ]
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
                    html.Span(
                        chevron, style={"marginRight": "6px", "fontSize": "10px"}
                    ),
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
# Gallery view (branch click → cards of direct leaves + subfolder drill-ins)
# ---------------------------------------------------------------------------


def _descend_to_group(tree: dict, group_path: str) -> dict | None:
    """Walk *tree* by the slash-delimited *group_path*; return the subtree.

    ``group_path == ""`` returns the root tree. Returns ``None`` if any
    segment along the path is missing.
    """
    if not group_path:
        return tree
    node: dict = tree
    for segment in group_path.split("/"):
        nxt = node.get(segment)
        if not isinstance(nxt, dict):
            return None
        node = nxt
    return node


def _count_descendant_leaves(node: dict) -> int:
    """Total number of leaves in *node* and all its sub-groups."""
    total = len(node.get("__leaves__", []))
    for k, v in node.items():
        if k == "__leaves__":
            continue
        if isinstance(v, dict):
            total += _count_descendant_leaves(v)
    return total


def _gallery_card_style() -> dict:
    return {
        "backgroundColor": "#2a2a2a",
        "border": "1px solid #444",
        "borderRadius": "6px",
        "padding": "12px",
        "cursor": "pointer",
        "userSelect": "none",
        "display": "flex",
        "flexDirection": "column",
        "gap": "6px",
        "minHeight": "120px",
    }


def _leaf_card(name: str, description: str) -> Any:
    """Render a leaf as a clickable gallery card.

    Reuses ``gv-nav-item`` ids so the existing leaf-click callback handles
    drilling into the script detail view — no extra wiring required.
    """
    label = name.rsplit("/", 1)[-1].replace("_", " ").title()
    return html.Div(
        [
            html.Div(
                "\U0001f4c4",  # page glyph (placeholder; mosaic thumbs deferred)
                style={"fontSize": "28px", "color": "#888"},
            ),
            html.Div(
                label,
                style={
                    "fontWeight": "bold",
                    "fontSize": "13px",
                    "color": "#e0e0e0",
                },
            ),
            html.Div(
                description or "",
                style={"fontSize": "11px", "color": "#888"},
            ),
        ],
        id={"type": "gv-nav-item", "index": name},
        n_clicks=0,
        style=_gallery_card_style(),
    )


def _subfolder_card(group_path: str, leaf_count: int) -> Any:
    """Render a sub-group as a clickable card showing its leaf count.

    Reuses ``gv-tree-group`` ids so the existing group-click callback drives
    the drill-down (setting the new active group and showing its gallery).
    """
    label = group_path.rsplit("/", 1)[-1].replace("_", " ").title()
    return html.Div(
        [
            html.Div("\U0001f4c1", style={"fontSize": "28px"}),  # folder glyph
            html.Div(
                label,
                style={
                    "fontWeight": "bold",
                    "fontSize": "13px",
                    "color": "#e0e0e0",
                },
            ),
            html.Div(
                f"{leaf_count} item{'s' if leaf_count != 1 else ''}",
                style={"fontSize": "11px", "color": "#888"},
            ),
        ],
        id={"type": "gv-tree-group", "index": group_path},
        n_clicks=0,
        style=_gallery_card_style(),
    )


def _render_gallery_view(
    tree: dict, group_path: str, descriptions: dict[str, str]
) -> Any:
    """Render the gallery (subfolder cards + leaf cards) for *group_path*.

    Returns a ``html.Div`` of cards, or a placeholder if the group is empty
    or missing.
    """
    node = _descend_to_group(tree, group_path)
    if node is None:
        return html.Span(
            f"Group not found: {group_path}", style={"color": "#888"}
        )

    cards: list = []
    sub_keys = [k for k in node if k != "__leaves__"]
    for sub in sub_keys:
        sub_path = f"{group_path}/{sub}" if group_path else sub
        cards.append(_subfolder_card(sub_path, _count_descendant_leaves(node[sub])))
    for leaf in node.get("__leaves__", []):
        cards.append(_leaf_card(leaf, descriptions.get(leaf, "")))

    if not cards:
        return html.Span("Empty group", style={"color": "#666"})

    title = group_path.replace("_", " ").replace("/", " / ").title() or "All"
    return html.Div(
        [
            html.Div(
                title,
                style={
                    "color": "#aaa",
                    "fontSize": "12px",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.06em",
                    "marginBottom": "8px",
                },
            ),
            html.Div(
                cards,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fill, minmax(180px, 1fr))",
                    "gap": "12px",
                },
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Gallery
# ---------------------------------------------------------------------------


class Gallery:
    """Configurable gallery dashboard with multi-plot support.

    Provides a Dash UI for browsing, editing, and running versioned scripts.
    Supports multi-output rendering (matplotlib PNGs, Plotly JSON, DataFrames),
    version diff labels showing parameter changes between versions, standalone
    ``.py`` export, author metadata on save, read-only mode via a script
    visibility toggle, and a "New Group" button for data groups lacking scripts.

    Parameters
    ----------
    backend :
        Single storage backend (for one-plot galleries).
    backends :
        Dict of ``{item_id: StorageBackend}`` for multi-plot galleries.
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
        context: dict[str, str] | None = None,
        track_packages: list[str] | None = None,
        item_label: str = "Item",
        group_label: str = "Group",
        version_label: str = "Version",
        item_url_key: str = "id",
        group_url_key: str = "group",
        version_url_key: str = "version",
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

        # User-facing vocabulary — defaults are domain-neutral. Override
        # per-gallery for friendlier labels (e.g. ``item_label="Plot"``,
        # ``group_label="Date"`` recovers the previous chart-flavoured UI).
        # URL keys stay neutral by default to keep deep-links stable across
        # vocabulary changes — see CLAUDE.md "URL deep-linking — design notes".
        self.item_label = item_label
        self.group_label = group_label
        self.version_label = version_label
        self.item_url_key = item_url_key
        self.group_url_key = group_url_key
        self.version_url_key = version_url_key

        self.context: dict[str, str] = dict(context) if context else {}
        """Ambient key-value pairs stamped into every saved version's metadata.
        Captures who/where/how: ``{"author": "Alice", "env": "prod"}``.
        Seeds the per-session ``gv-context`` Store at app build time — Dash
        deployments can override it per-session via a login callback:
            Output("gv-context", "data") <- {"author": logged_in_user}
        """

        self.track_packages = list(track_packages) if track_packages else []
        """Package names whose installed version should be stamped into the
        script frontmatter at save time, alongside the always-on data hash
        and Python version. Example: ``["mpl_brandpacker", "matplotlib"]``."""

        self._app: dash.Dash | None = None

    # -- Pure views of in-memory state --------------------------------------

    @property
    def plot_names(self) -> list[str]:
        """Names of all configured plots (backend keys), in insertion order."""
        return list(self.backends.keys())

    @property
    def is_multi(self) -> bool:
        """True when the gallery has more than one configured backend."""
        return len(self.backends) > 1

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
        self._register_render_route(app)
        return app

    def _register_render_route(self, app: dash.Dash) -> None:
        """Mount ``/render`` returning the saved artifact bytes for a version.

        Read-only lookup — serves what's already on disk via
        :meth:`load_artifact`. Does not run scripts. The (more expensive)
        live-run variant is documented as a future extension in CLAUDE.md.
        """
        from flask import Response, abort, request

        @app.server.route("/render")
        def render_artifact():  # type: ignore[unused-ignore]
            item = request.args.get(self.item_url_key)
            group = request.args.get(self.group_url_key)
            version = request.args.get(self.version_url_key)
            if not (item and group and version):
                abort(
                    400,
                    f"{self.item_url_key}, {self.group_url_key}, "
                    f"{self.version_url_key} are required",
                )
            try:
                data = self.load_artifact(item, group, version)
            except (FileNotFoundError, KeyError):
                abort(404)
            if not data:
                abort(404)
            return Response(data, mimetype="image/png")

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

        # "Add <item>" button (only when config file is used)
        add_plot_btn = []
        if self._config_path:
            add_plot_btn = [
                dbc.Button(
                    f"+ Add {self.item_label}",
                    id="gv-add-plot-btn",
                    color="secondary",
                    size="sm",
                    n_clicks=0,
                    style={"width": "100%", "marginTop": "8px", "marginBottom": "8px"},
                ),
                dbc.Modal(
                    [
                        dbc.ModalHeader(f"Add New {self.item_label}"),
                        dbc.ModalBody(
                            [
                                dbc.Label(f"{self.item_label} name"),
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
                                    f"{self.item_label}s",
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
                                # Active gallery branch — "" means "no
                                # branch active, show the leaf detail view".
                                # Set when a tree group / subfolder card is
                                # clicked; cleared when a leaf is clicked.
                                dcc.Store(id="gv-active-group", data=""),
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
                                                    self.group_label,
                                                    style={
                                                        "color": "#aaa",
                                                        "fontSize": "12px",
                                                    },
                                                ),
                                                dcc.Dropdown(
                                                    id="gv-group",
                                                    placeholder=f"Select {self.group_label.lower()}...",
                                                    clearable=False,
                                                    style={"marginBottom": "6px"},
                                                ),
                                            ],
                                        ),
                                        dbc.Col(
                                            width=5,
                                            children=[
                                                html.Label(
                                                    self.version_label,
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
                                                    title=(
                                                        f"Refresh {self.group_label.lower()}s "
                                                        f"& {self.version_label.lower()}s"
                                                    ),
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
                                                    id="gv-new-group-btn",
                                                    color="secondary",
                                                    size="sm",
                                                    n_clicks=0,
                                                    style={
                                                        "width": "100%",
                                                        "fontSize": "16px",
                                                        "padding": "4px",
                                                    },
                                                    title=(
                                                        f"Start new {self.group_label.lower()} "
                                                        "from uncharted data"
                                                    ),
                                                ),
                                            ],
                                        ),
                                    ]
                                ),
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            width=5,
                                            children=[
                                                html.Label(
                                                    "Filter",
                                                    style={
                                                        "color": "#aaa",
                                                        "fontSize": "12px",
                                                    },
                                                ),
                                                dcc.Dropdown(
                                                    id="gv-tag-filter",
                                                    placeholder="All versions",
                                                    clearable=True,
                                                    style={"marginBottom": "6px"},
                                                ),
                                            ],
                                        ),
                                        dbc.Col(
                                            width=5,
                                            children=[
                                                html.Label(
                                                    "Tags",
                                                    style={
                                                        "color": "#aaa",
                                                        "fontSize": "12px",
                                                    },
                                                ),
                                                html.Div(
                                                    id="gv-tags-row",
                                                    style={
                                                        "marginBottom": "6px",
                                                        "minHeight": "24px",
                                                    },
                                                ),
                                            ],
                                        ),
                                        dbc.Col(
                                            width=2,
                                            children=[
                                                html.Label(
                                                    " ", style={"fontSize": "12px"}
                                                ),
                                                dbc.Button(
                                                    "Edit",
                                                    id="gv-edit-tags-btn",
                                                    color="secondary",
                                                    size="sm",
                                                    n_clicks=0,
                                                    style={"width": "100%"},
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
                                                dbc.Label(
                                                    "What changed? (optional)",
                                                    style={
                                                        "fontSize": "12px",
                                                        "marginTop": "8px",
                                                    },
                                                ),
                                                dbc.Textarea(
                                                    id="gv-save-description",
                                                    placeholder=(
                                                        "Why this version exists — "
                                                        "e.g. switched to log scale "
                                                        "because small categories "
                                                        "were buried."
                                                    ),
                                                    rows=3,
                                                    style={"fontSize": "12px"},
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
                                dbc.Modal(
                                    [
                                        dbc.ModalHeader("Edit Tags"),
                                        dbc.ModalBody(
                                            [
                                                html.P(
                                                    "Add or remove tags for this version.",
                                                    style={"marginBottom": "8px"},
                                                ),
                                                html.Div(
                                                    id="gv-edit-tags-current",
                                                    style={"marginBottom": "12px"},
                                                ),
                                                dbc.Label(
                                                    "Add tag",
                                                    style={"fontSize": "12px"},
                                                ),
                                                dbc.InputGroup(
                                                    [
                                                        dbc.Input(
                                                            id="gv-new-tag-input",
                                                            type="text",
                                                            placeholder="e.g. published, final",
                                                            size="sm",
                                                        ),
                                                        dbc.Button(
                                                            "+",
                                                            id="gv-add-tag-btn",
                                                            color="primary",
                                                            size="sm",
                                                        ),
                                                    ]
                                                ),
                                            ]
                                        ),
                                        dbc.ModalFooter(
                                            [
                                                dbc.Button(
                                                    "Done",
                                                    id="gv-edit-tags-done",
                                                    color="primary",
                                                    size="sm",
                                                ),
                                            ]
                                        ),
                                    ],
                                    id="gv-edit-tags-modal",
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
                                            "Output",
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
                                        id="gv-output-panel",
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
                # URL deep-linking — selectors + configurator param overrides
                dcc.Location(id="gv-url", refresh=False),
                dcc.Store(id="gv-url-overrides"),
                # Per-session context — seeded from Gallery(context=...) at
                # init. Multi-user deployments override via a login callback:
                #     Output("gv-context", "data") <- {"author": username, ...}
                dcc.Store(
                    id="gv-context",
                    storage_type="session",
                    data=self.context,
                ),
                dcc.ConfirmDialog(
                    id="gv-confirm-navigate",
                    message="You have unsaved changes. Continue without saving?",
                ),
                # Export standalone script
                dcc.Download(id="gv-export-script-download"),
            ],
        )

    # ------------------------------------------------------------------
    # Public headless API
    # ------------------------------------------------------------------

    def run_script(
        self,
        item_id: str | None,
        sections: ScriptSections,
        inject_vars: dict[str, Any] | None = None,
    ) -> RunResult:
        """Run *sections* against *item_id*'s backend, return ``RunResult``.

        Usable without a browser — no Dash state involved.
        """
        return self._get_backend(item_id).run_preview(
            sections, inject_vars=inject_vars
        )

    def _provenance_metadata(self, item_id: str | None, group: str) -> dict[str, str]:
        """Build the provenance metadata dict for stamping at save time.

        Always includes:
            * ``data_hash`` — sha256 of the data file (if the backend has one)
            * ``python`` — running interpreter version

        Plus, for every name in :attr:`track_packages` that is importable, a
        ``<package>`` entry with its installed version (resolved via
        :func:`importlib.metadata.version`).

        All keys are lowercase / snake_case to match the rest of the
        ``# === METADATA ===`` block.
        """
        import sys
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _pkg_version

        meta: dict[str, str] = {}

        data_hash = self._get_backend(item_id).data_hash(group)
        if data_hash:
            meta["data_hash"] = data_hash

        meta["python"] = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

        for pkg in self.track_packages:
            try:
                meta[pkg] = _pkg_version(pkg)
            except PackageNotFoundError:
                # Silently skip packages that aren't installed — the user
                # asked us to track them but they're absent in this env.
                continue

        return meta

    def save_script(
        self,
        item_id: str | None,
        group: str,
        sections: ScriptSections,
        author: str | None = None,
        change_note: str | None = None,
    ) -> str:
        """Persist *sections* for *group* under *item_id*'s backend.

        Stamps a ``# === METADATA ===`` block at the top of the script:

        - ``author`` — from *author* (falls back to ``self.context["author"]``)
        - ``saved`` — current timestamp
        - ``change`` — from *change_note* (free-form rationale: "what changed
          in this version?")
        - all other ``self.context`` keys — stamped after the above
        - provenance keys — data hash, Python + tracked package versions

        Returns the new version string.  Usable without a browser.
        """
        resolved_author = (author and author.strip()) or self.context.get("author", "")
        meta: dict[str, str] = {}
        if resolved_author:
            meta["author"] = resolved_author
            meta["saved"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if change_note and change_note.strip():
            meta["change"] = change_note.strip()
        # Remaining context keys (env, team, via, …) stamped after human fields.
        for k, v in self.context.items():
            if k != "author" and k not in meta and v:
                meta[k] = v
        # Provenance: data hash, Python version, tracked package versions.
        # Stamped after the human-facing fields so the file reads top-down:
        # who, why, then what-environment.
        meta.update(self._provenance_metadata(item_id, group))
        if meta:
            sections = sections.with_metadata(meta)
        return self._get_backend(item_id).save_version(group, sections)

    def list_groups(self, item_id: str | None = None) -> list[str]:
        """Return available groups for *item_id*, newest first."""
        return self._get_backend(item_id).list_groups()

    def list_versions(self, item_id: str | None, group: str) -> list[str]:
        """Return available versions for *group* under *item_id*, ascending."""
        return self._get_backend(item_id).list_versions(group)

    def load_script(
        self, item_id: str | None, group: str, version: str
    ) -> ScriptSections:
        """Load script sections for *group*/*version* under *item_id*."""
        return self._get_backend(item_id).load_script(group, version)

    def load_data(self, item_id: str | None, group: str):
        """Load a data preview DataFrame for *group* under *item_id*."""
        return self._get_backend(item_id).load_data(group)

    def load_artifact(
        self, item_id: str | None, group: str, version: str
    ) -> bytes | None:
        """Load saved artifact bytes for *group*/*version* under *item_id*."""
        return self._get_backend(item_id).load_artifact(group, version)

    def template_for_group(self, item_id: str | None, group: str) -> ScriptSections:
        """Return a starter template for *group*, seeded from the latest existing version."""
        return self._get_backend(item_id).template_for_group(group)

    def list_uncharted_groups(self, item_id: str | None = None) -> list[str]:
        """Return data groups that have no scripts yet, newest first."""
        return self._get_backend(item_id).list_uncharted_groups()

    def export_inject_vars(
        self, item_id: str | None, group: str, version: str
    ) -> dict[str, str]:
        """Return path-related inject vars for a standalone export script.

        Delegates to the backend — ``FileSystemBackend`` returns ``BASE_DIR``
        and ``OUTPUT_PATH``; other backends may return ``{}``.
        """
        return self._get_backend(item_id).export_inject_vars(group, version)

    def parse_url_state(self, search: str) -> dict:
        """Parse a URL query string into selectors and configurator overrides.

        Recognised keys (key names are configurable via ``item_url_key``,
        ``group_url_key``, ``version_url_key``; defaults are ``id``,
        ``group``, ``version``):

        * selectors — any may be missing; they propagate through to the UI
          as ``no_update``.
        * ``script_<name>`` — configurator parameter override. Looked up
          against the chosen item/group/version's detected params and
          coerced to the declared type. Unknown names and bad casts are
          silently dropped (URLs are user-supplied; never raise).

        Returned shape uses the *internal* axis names (``item``, ``group``,
        ``version``) regardless of URL key configuration, so callers don't
        need to track which key was used.
        """
        from urllib.parse import parse_qs

        flat = {k: v[0] for k, v in parse_qs(search.lstrip("?")).items() if v}
        item = flat.get(self.item_url_key)
        group = flat.get(self.group_url_key)
        version = flat.get(self.version_url_key)

        overrides: dict[str, Any] = {}
        if item and group and version:
            try:
                sections = self.load_script(item, group, version)
            except (FileNotFoundError, KeyError):
                sections = None
            if sections is not None:
                specs = detect_params(sections.configurator)
                prefix = "script_"
                for k, raw in flat.items():
                    if not k.startswith(prefix):
                        continue
                    name = k[len(prefix) :]
                    spec = specs.get(name)
                    if spec is None or spec.annotation is None:
                        continue
                    try:
                        if spec.annotation is bool:
                            overrides[name] = raw.lower() in ("1", "true", "yes")
                        else:
                            overrides[name] = spec.annotation(raw)
                    except (ValueError, TypeError):
                        pass
        return {
            "item": item,
            "group": group,
            "version": version,
            "param_overrides": overrides,
        }

    def apply_params_to_script(
        self, script_text: str, param_values: list | None
    ) -> ScriptSections:
        """Parse ``script_text`` and apply ``param_values`` to its configurator.

        Used by callbacks that need to splice the user's current form values
        into the configurator before running, saving, or exporting. Returns a
        ``ScriptSections`` whose configurator has been updated; the code and
        save sections are untouched. If there are no params or no values, the
        original sections are returned.
        """
        sections = ScriptSections.from_text(script_text)
        inject = _param_values_to_inject(sections.configurator, param_values)
        if inject:
            sections = sections.with_params(inject)
        return sections

    def version_diff(self, item_id: str | None, group: str, version: str) -> list[str]:
        """Return human-readable parameter changes between *version* and the one before it.

        Returns an empty list for v1 (no predecessor) or when nothing changed.
        """
        if version == "1":
            return []
        prev = str(int(version) - 1)
        current = self.load_script(item_id, group, version)
        previous = self.load_script(item_id, group, prev)
        return diff_configurator(previous.configurator, current.configurator)

    def version_diff_label(
        self, item_id: str | None, group: str, version: str
    ) -> tuple[str, str]:
        """Return ``(text, color)`` describing the diff between *version* and v_{n-1}.

        Pure data — no Dash dependencies. The caller wraps the text in whatever
        UI element it likes (``html.Span``, badge, plain text, …) and applies
        the color hint as styling.

        Returns:
            * ``("v1 — initial version", "#777")`` for v1
            * ``("v{n} — no parameter changes from v{n-1}", "#777")`` for unchanged
            * ``("v{n} — <comma-joined diff>", "#8cb4d5")`` for changed
        """
        version = str(version)
        if version == "1":
            return ("v1 — initial version", "#777")
        prev_version = str(int(version) - 1)
        diff = self.version_diff(item_id, group, version)
        if not diff:
            return (f"v{version} — no parameter changes from v{prev_version}", "#777")
        return (f"v{version} — " + ", ".join(diff), "#8cb4d5")

    def change_note(self, item_id: str | None, group: str, version: str) -> str | None:
        """Return the ``change`` metadata field for *version*, if any.

        This is the per-version "what changed in this save?" rationale (the
        intent-capture field surfaced in the Save modal as
        ``gv-save-description``).  Returns ``None`` when the script has no
        change note (e.g. v1, or a version saved without one).
        """
        sections = self.load_script(item_id, group, version)
        note = sections.metadata.get("change")
        return note or None

    def author(self, item_id: str | None, group: str, version: str) -> str | None:
        """Return the ``author`` metadata field for *version*, if any."""
        sections = self.load_script(item_id, group, version)
        return sections.metadata.get("author") or None

    # -- Tag facade ----------------------------------------------------------
    #
    # Tags are the only mutation that touches an existing saved version in
    # place — Save always creates a new version. Conventional tag names with
    # special UI rendering: ``published`` (green), ``final`` (blue),
    # ``frozen`` (red), ``draft`` / ``wip`` (grey). ``frozen`` is purely
    # informational — the save path always creates a new version by
    # construction, so there's nothing to enforce.

    def list_tags(self, item_id: str | None, group: str, version: str) -> list[str]:
        """Return tags attached to *group*/*version* under *item_id*."""
        return self._get_backend(item_id).list_tags(group, version)

    def add_tag(
        self, item_id: str | None, group: str, version: str, tag: str
    ) -> list[str]:
        """Attach *tag* to *group*/*version* in place. Returns new tag list."""
        return self._get_backend(item_id).add_tag(group, version, tag)

    def remove_tag(
        self, item_id: str | None, group: str, version: str, tag: str
    ) -> list[str]:
        """Remove *tag* from *group*/*version* in place. Returns new tag list."""
        return self._get_backend(item_id).remove_tag(group, version, tag)

    def versions_with_tag(
        self, item_id: str | None, group: str, tag: str
    ) -> list[str]:
        """Return versions of *group* carrying *tag*, ascending."""
        return self._get_backend(item_id).versions_with_tag(group, tag)

    def all_tags(self, item_id: str | None, group: str) -> list[str]:
        """Return the union of tags across all versions of *group*, sorted.

        Used to populate the tag-filter dropdown — only tags that actually
        exist on disk show up.
        """
        backend = self._get_backend(item_id)
        seen: list[str] = []
        for v in backend.list_versions(group):
            for t in backend.list_tags(group, v):
                if t not in seen:
                    seen.append(t)
        return sorted(seen)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_backend(self, item_id: str | None) -> StorageBackend:
        """Resolve plot name to backend, fallback to first."""
        if item_id and item_id in self.backends:
            return self.backends[item_id]
        return next(iter(self.backends.values()))

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
            names = self.plot_names
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
            return _render_tree_node(tree, collapsed or [], active_plot, descriptions)

        # -- Tree-group click: toggle collapse AND mark group active --
        # Active-group state drives the gallery view in the right panel
        # (see render_gallery_panel below). Subfolder cards inside the
        # gallery share the same id type, so drilling in works for free.
        @app.callback(
            Output("gv-sidebar-collapsed", "data"),
            Output("gv-active-group", "data", allow_duplicate=True),
            Input({"type": "gv-tree-group", "index": ALL}, "n_clicks"),
            State("gv-sidebar-collapsed", "data"),
            prevent_initial_call=True,
        )
        def toggle_group(n_clicks_list, collapsed):
            if not any(n_clicks_list):
                return dash.no_update, dash.no_update
            triggered = ctx.triggered_id
            if triggered is None:
                return dash.no_update, dash.no_update
            group_path = triggered["index"]
            collapsed = list(collapsed or [])
            if group_path in collapsed:
                collapsed.remove(group_path)
            else:
                collapsed.append(group_path)
            return collapsed, group_path

        # -- Render gallery view in the right panel when a branch is active --
        # Empty active_group means "show leaf detail" — let load_version
        # drive the panel as before.
        @app.callback(
            Output("gv-output-panel", "children", allow_duplicate=True),
            Output("gv-data-panel", "children", allow_duplicate=True),
            Input("gv-active-group", "data"),
            prevent_initial_call=True,
        )
        def render_gallery_panel(active_group):
            if not active_group:
                return dash.no_update, dash.no_update
            descriptions: dict[str, str] = {}
            if self._config_path:
                config = load_config(self._config_path)
                plots_cfg = config.get("plots", {})
                for name, cfg in plots_cfg.items():
                    desc = cfg.get("description", "")
                    if desc:
                        descriptions[name] = desc
            tree = _build_sidebar_tree(self.plot_names)
            return _render_gallery_view(tree, active_group, descriptions), _no_data()

        # -- Click nav item → select plot, load its groups, exit gallery --
        # Clearing gv-active-group restores the leaf detail view in the
        # right panel (see render_gallery_panel below).
        @app.callback(
            Output("gv-plot-select", "data", allow_duplicate=True),
            Output("gv-group", "options"),
            Output("gv-group", "value"),
            Output("gv-active-group", "data", allow_duplicate=True),
            Input({"type": "gv-nav-item", "index": dash.ALL}, "n_clicks"),
            prevent_initial_call=True,
        )
        def nav_click(n_clicks_list):
            if not any(n_clicks_list):
                return (dash.no_update,) * 4
            triggered = ctx.triggered_id
            if triggered is None:
                return (dash.no_update,) * 4
            item_id = triggered["index"]
            groups = self.list_groups(item_id)
            opts = [{"label": d, "value": d} for d in groups]
            return item_id, opts, (groups[0] if groups else None), ""

        # -- Also load groups on initial plot select --
        @app.callback(
            Output("gv-group", "options", allow_duplicate=True),
            Output("gv-group", "value", allow_duplicate=True),
            Input("gv-plot-select", "data"),
            prevent_initial_call="initial_duplicate",
        )
        def init_groups_for_plot(item_id):
            if not item_id:
                return [], None
            groups = self.list_groups(item_id)
            opts = [{"label": d, "value": d} for d in groups]
            return opts, (groups[0] if groups else None)

        # -- Refresh button → reload groups + versions for current plot --
        @app.callback(
            Output("gv-group", "options", allow_duplicate=True),
            Output("gv-group", "value", allow_duplicate=True),
            Output("gv-version", "options", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Input("gv-refresh-btn", "n_clicks"),
            State("gv-plot-select", "data"),
            State("gv-group", "value"),
            prevent_initial_call=True,
        )
        def refresh_groups(n_clicks, item_id, current_group):
            if not item_id:
                return [], None, [], None
            groups = self.list_groups(item_id)
            group_opts = [{"label": d, "value": d} for d in groups]
            group_val = (
                current_group if current_group in groups else (groups[0] if groups else None)
            )
            versions = self.list_versions(item_id, group_val) if group_val else []
            ver_opts = [{"label": f"v{v}", "value": v} for v in versions]
            ver_val = versions[-1] if versions else None
            return group_opts, group_val, ver_opts, ver_val

        # -- Update version dropdown when group changes --
        @app.callback(
            Output("gv-version", "options"),
            Output("gv-version", "value", allow_duplicate=True),
            Input("gv-group", "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def update_versions(group, item_id):
            if not group:
                return [], None
            versions = self.list_versions(item_id, group)
            opts = [{"label": f"v{v}", "value": v} for v in versions]
            return opts, versions[-1] if versions else None

        # -- URL deep-link → selectors + override store (initial load + nav) --
        @app.callback(
            Output("gv-plot-select", "data", allow_duplicate=True),
            Output("gv-group", "value", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Output("gv-url-overrides", "data"),
            Input("gv-url", "search"),
            prevent_initial_call="initial_duplicate",
        )
        def apply_url(search):
            state = self.parse_url_state(search or "")
            return (
                state["item"] or dash.no_update,
                state["group"] or dash.no_update,
                state["version"] or dash.no_update,
                state["param_overrides"] or None,
            )

        # -- Load script + data + plot + detect params --
        @app.callback(
            Output("gv-editor-script", "value"),
            Output("gv-param-fields", "children"),
            Output("gv-data-panel", "children"),
            Output("gv-output-panel", "children"),
            Output("gv-plot-bytes-store", "data"),
            Output("gv-clean-script-store", "data"),
            Input("gv-group", "value"),
            Input("gv-version", "value"),
            State("gv-plot-select", "data"),
            State("gv-url-overrides", "data"),
        )
        def load_version(group, version, item_id, url_overrides):
            if not group or not version:
                return (*(dash.no_update,) * 6,)
            version = str(version)
            sections = self.load_script(item_id, group, version)
            script_text = sections.to_text()
            param_fields = _build_param_fields(
                sections.configurator, overrides=url_overrides
            )
            data_children = _data_table(self.load_data(item_id, group))
            plot_bytes = self.load_artifact(item_id, group, version)
            plot_children = _plot_img(plot_bytes)
            b64 = base64.b64encode(plot_bytes).decode() if plot_bytes else None
            return (
                script_text,
                param_fields,
                data_children,
                plot_children,
                b64,
                script_text,
            )

        # -- RUN button --
        @app.callback(
            Output("gv-console", "children"),
            Output("gv-output-panel", "children", allow_duplicate=True),
            Output("gv-plot-bytes-store", "data", allow_duplicate=True),
            Input("gv-run-btn", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def run_script(n_clicks, script_code, param_values, item_id):
            if not script_code:
                return "Nothing to run.", _no_plot(), None
            sections = ScriptSections.from_text(script_code)
            inject = _param_values_to_inject(sections.configurator, param_values)
            result = self.run_script(item_id, sections, inject_vars=inject)
            console = result.output
            if not result.success:
                console += f"\n--- ERROR ---\n{result.error}"
            b64 = (
                base64.b64encode(result.image_bytes).decode()
                if result.image_bytes
                else None
            )
            return console or "(no output)", _render_outputs(result.items), b64

        # -- TAGS: update tag row when version changes --
        @app.callback(
            Output("gv-tags-row", "children"),
            Output("gv-tag-filter", "options"),
            Input("gv-version", "value"),
            State("gv-group", "value"),
            State("gv-plot-select", "data"),
        )
        def update_tags_row(version, group, item_id):
            if not group or not version:
                return [], []
            tags = self.list_tags(item_id, group, version)
            all_tags = self.all_tags(item_id, group)
            tag_badges = [_tag_badge(t) for t in tags]
            tag_options = [{"label": t, "value": t} for t in all_tags]
            return tag_badges, tag_options

        # -- TAGS: toggle edit modal --
        @app.callback(
            Output("gv-edit-tags-modal", "is_open"),
            Output("gv-edit-tags-current", "children"),
            Input("gv-edit-tags-btn", "n_clicks"),
            Input("gv-edit-tags-done", "n_clicks"),
            State("gv-edit-tags-modal", "is_open"),
            State("gv-group", "value"),
            State("gv-version", "value"),
            State("gv-plot-select", "data"),
        )
        def toggle_edit_tags_modal(n_edit, n_done, is_open, group, version, item_id):
            trigger = ctx.triggered_id
            if trigger == "gv-edit-tags-btn" and not is_open:
                if group and version:
                    tags = self.list_tags(item_id, group, version)
                    tag_list = [
                        dbc.Badge(
                            [
                                t,
                                html.Span(
                                    " ×",
                                    id={"type": "gv-tag-remove", "index": t},
                                    style={"marginLeft": "4px", "cursor": "pointer"},
                                    n_clicks=0,
                                ),
                            ],
                            color=_TAG_COLORS.get(t, "secondary"),
                            pill=True,
                            style={"marginRight": "4px", "marginBottom": "4px"},
                        )
                        for t in tags
                    ]
                    return True, tag_list
            if trigger == "gv-edit-tags-done":
                return False, dash.no_update
            return dash.no_update, dash.no_update

        # -- TAGS: add/remove tags via modal --
        @app.callback(
            Output("gv-new-tag-input", "value"),
            Output("gv-edit-tags-current", "children"),
            Output("gv-tags-row", "children", allow_duplicate=True),
            Output("gv-tag-filter", "options", allow_duplicate=True),
            Input("gv-add-tag-btn", "n_clicks"),
            Input({"type": "gv-tag-remove", "index": ALL}, "n_clicks"),
            State("gv-new-tag-input", "value"),
            State("gv-group", "value"),
            State("gv-version", "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def manage_tags(add_clicks, remove_clicks, new_tag, group, version, item_id):
            if not group or not version:
                return "", dash.no_update, dash.no_update, dash.no_update
            trigger = ctx.triggered_id
            if trigger == "gv-add-tag-btn" and new_tag:
                self.add_tag(item_id, group, version, new_tag.strip())
            elif isinstance(trigger, dict) and trigger.get("type") == "gv-tag-remove":
                # Avoid spurious removes when n_clicks=0 (initial render).
                if not any(remove_clicks):
                    return (
                        dash.no_update,
                        dash.no_update,
                        dash.no_update,
                        dash.no_update,
                    )
                tag_to_remove = trigger["index"]
                self.remove_tag(item_id, group, version, tag_to_remove)
            else:
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update
            tags = self.list_tags(item_id, group, version)
            all_tags = self.all_tags(item_id, group)
            tag_list = [
                dbc.Badge(
                    [
                        t,
                        html.Span(
                            " ×",
                            id={"type": "gv-tag-remove", "index": t},
                            style={"marginLeft": "4px", "cursor": "pointer"},
                            n_clicks=0,
                        ),
                    ],
                    color=_TAG_COLORS.get(t, "secondary"),
                    pill=True,
                    style={"marginRight": "4px", "marginBottom": "4px"},
                )
                for t in tags
            ]
            badges = [_tag_badge(t) for t in tags]
            filter_options = [{"label": t, "value": t} for t in all_tags]
            return "", tag_list, badges, filter_options

        # -- TAGS: filter version dropdown by tag --
        @app.callback(
            Output("gv-version", "options"),
            Output("gv-version", "value"),
            Input("gv-tag-filter", "value"),
            State("gv-group", "value"),
            State("gv-plot-select", "data"),
            State("gv-version", "value"),
            prevent_initial_call=True,
        )
        def filter_versions_by_tag(selected_tag, group, item_id, current_version):
            if not group:
                return [], None
            backend = self._get_backend(item_id)
            all_versions = backend.list_versions(group)
            if selected_tag:
                filtered = backend.versions_with_tag(group, selected_tag)
                versions = [v for v in all_versions if v in filtered]
            else:
                versions = all_versions
            options = [{"label": f"v{v}", "value": v} for v in versions]
            new_value = (
                current_version
                if current_version in versions
                else (versions[-1] if versions else None)
            )
            return options, new_value

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

        # -- SAVE: step 1.5 — pre-fill author from context store --
        # Fires when the modal opens. Pre-fills from context["author"] if set.
        # The user can still override before submitting.
        @app.callback(
            Output("gv-save-author", "value"),
            Input("gv-save-modal", "is_open"),
            State("gv-context", "data"),
            prevent_initial_call=True,
        )
        def prefill_author_from_context(is_open, context_data):
            if is_open and context_data:
                author = (context_data or {}).get("author", "")
                if author:
                    return author
            return dash.no_update

        # -- SAVE: step 2 — actual save + refresh gallery --
        @app.callback(
            Output("gv-console", "children", allow_duplicate=True),
            Output("gv-output-panel", "children", allow_duplicate=True),
            Output("gv-gallery-items", "data", allow_duplicate=True),
            Output("gv-group", "options", allow_duplicate=True),
            Output("gv-group", "value", allow_duplicate=True),
            Output("gv-version", "options", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Output("gv-editor-script", "value", allow_duplicate=True),
            Output("gv-clean-script-store", "data", allow_duplicate=True),
            Input("gv-confirm-save-ok", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            State("gv-plot-select", "data"),
            State("gv-group", "value"),
            State("gv-save-author", "value"),
            State("gv-save-description", "value"),
            prevent_initial_call=True,
        )
        def save_version(
            n_clicks,
            script_code,
            param_values,
            item_id,
            selected_group,
            author,
            change_note,
        ):
            if not script_code:
                return (
                    "Nothing to save.",
                    _no_plot(),
                    *(dash.no_update,) * 7,
                )

            import datetime as _dt

            save_group = selected_group or _dt.date.today().strftime("%Y%m%d")
            sections = self.apply_params_to_script(script_code, param_values)

            new_version = self.save_script(
                item_id,
                save_group,
                sections,
                author=author,
                change_note=change_note,
            )

            console = (
                f"Saved v{new_version}\n"
                f"  scripts/script_{save_group}_v{new_version}.py\n"
                f"  plots/plot_{save_group}_v{new_version}.png"
            )
            groups = self.list_groups(item_id)
            group_opts = [{"label": d, "value": d} for d in groups]
            versions = self.list_versions(item_id, save_group)
            ver_opts = [{"label": f"v{v}", "value": v} for v in versions]
            plot_bytes = self.load_artifact(item_id, save_group, str(new_version))
            updated_script = sections.to_text()

            return (
                console,
                _plot_img(plot_bytes),
                self.plot_names,
                group_opts,
                save_group,
                ver_opts,
                new_version,
                updated_script,
                updated_script,
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
            return self.apply_params_to_script(script_code, param_values).to_text()

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

        # -- Feature 2: Version diff label + change note --
        @app.callback(
            Output("gv-version-diff", "children"),
            Input("gv-version", "value"),
            State("gv-group", "value"),
            State("gv-plot-select", "data"),
        )
        def show_version_diff(version, group, item_id):
            if not group or not version:
                return ""
            text, color = self.version_diff_label(item_id, group, version)
            note = self.change_note(item_id, group, version)
            author = self.author(item_id, group, version)
            children = [html.Div(text, style={"color": color})]
            # Author line — small, dim, italic. Skip if absent.
            if author:
                children.append(
                    html.Div(
                        f"by {author}",
                        style={"color": "#666", "fontStyle": "italic"},
                    )
                )
            # Change note — rendered as a quote-style block on a second line so
            # the "what changed" rationale is visible at a glance, not buried
            # in the script. Truncate visually via CSS but keep the full text
            # available on hover via the title attribute.
            if note:
                children.append(
                    html.Div(
                        f"“{note}”",
                        title=note,
                        style={
                            "color": "#bbb",
                            "fontStyle": "italic",
                            "whiteSpace": "nowrap",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "maxWidth": "100%",
                        },
                    )
                )
            return children

        # -- Feature 3: New Date button (detect uncharted data) --
        @app.callback(
            Output("gv-group", "options", allow_duplicate=True),
            Output("gv-group", "value", allow_duplicate=True),
            Output("gv-version", "options", allow_duplicate=True),
            Output("gv-version", "value", allow_duplicate=True),
            Output("gv-editor-script", "value", allow_duplicate=True),
            Output("gv-param-fields", "children", allow_duplicate=True),
            Output("gv-console", "children", allow_duplicate=True),
            Output("gv-clean-script-store", "data", allow_duplicate=True),
            Input("gv-new-group-btn", "n_clicks"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def new_group_from_data(n_clicks, item_id):
            if not item_id:
                return (*(dash.no_update,) * 8,)
            uncharted = self.list_uncharted_groups(item_id)
            if not uncharted:
                return (
                    *(dash.no_update,) * 6,
                    f"No new {self.group_label.lower()}s found without scripts.",
                    dash.no_update,
                )
            new_group = uncharted[0]
            template = self.template_for_group(item_id, new_group)
            script_text = template.to_text()
            param_fields = _build_param_fields(template.configurator)
            groups = sorted(set(self.list_groups(item_id) + [new_group]), reverse=True)
            group_opts = [{"label": d, "value": d} for d in groups]
            return (
                group_opts,
                new_group,
                [{"label": "v1 (new)", "value": "1"}],
                "1",
                script_text,
                param_fields,
                f"New {self.group_label.lower()} {new_group} — edit and Save Version to create v1.",
                script_text,
            )

        # -- Feature 5: Dirty flag — store clean script on load --
        # (The clean-script-store is also updated in save_version above)

        # -- Feature 5: Confirm before navigating with unsaved changes --
        # We intercept nav_click and group/version changes via a clientside check.
        # For simplicity, we use a Store-based approach: compare editor vs clean store.

        # -- Feature 8: Export standalone script --
        @app.callback(
            Output("gv-export-script-download", "data"),
            Input("gv-export-script-btn", "n_clicks"),
            State("gv-editor-script", "value"),
            State({"type": "gv-param", "name": dash.ALL}, "value"),
            State("gv-group", "value"),
            State("gv-version", "value"),
            State("gv-plot-select", "data"),
            prevent_initial_call=True,
        )
        def export_standalone(
            n_clicks, script_code, param_values, group, version, item_id
        ):
            if not script_code:
                return dash.no_update
            sections = ScriptSections.from_text(script_code)
            # Build inject vars: params + group/version/paths
            inject = _param_values_to_inject(sections.configurator, param_values) or {}
            inject["group"] = group or "unknown"
            inject["version"] = int(version) if version else 0
            inject.update(
                self.export_inject_vars(item_id, group or "unknown", version or "0")
            )
            standalone = sections.to_full(inject_vars=inject)
            filename = (
                f"script_{group}_v{version}.py" if group and version else "script.py"
            )
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
                    return (
                        f"Please enter a {self.item_label.lower()} name.",
                        dash.no_update,
                        dash.no_update,
                    )

                name = name.strip().replace(" ", "_").lower()
                config = load_config(self._config_path)  # type: ignore[arg-type]  # ty:ignore[invalid-argument-type]
                if name in config.get("plots", {}):
                    return (
                        f"{self.item_label} '{name}' already exists.",
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
                # is_multi is now a @property — re-derives automatically

                # Trigger sidebar rebuild by updating gallery-items
                return f"Created '{name}'", name, self.plot_names


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


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


def _build_param_fields(
    configurator_source: str, overrides: dict | None = None
) -> list:
    """Detect typed params and build input fields for them.

    ``overrides`` (e.g. from URL deep-linking) replace the configurator's
    declared defaults on a per-name basis. Unknown override names are
    ignored — defaults still come from the script.
    """
    params = detect_params(configurator_source)
    if not params:
        return []

    overrides = overrides or {}
    fields = []
    for name, spec in params.items():
        label = name.replace("_", " ").title()
        default = overrides.get(name, spec.default)
        if spec.annotation is bool:
            field = dbc.Checkbox(
                id={"type": "gv-param", "name": name},
                label=label,
                value=bool(default),
                style={"marginBottom": "4px"},
            )
        elif spec.annotation in (int, float):
            field = html.Div(
                [
                    html.Label(label, style={"color": "#aaa", "fontSize": "11px"}),
                    dbc.Input(
                        id={"type": "gv-param", "name": name},
                        type="number",
                        value=default,
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
                        value=str(default),
                        size="sm",
                        style={"marginBottom": "4px"},
                    ),
                ]
            )
        fields.append(field)

    if fields:
        fields.insert(0, html.Div("Parameters", style=_SECTION_LABEL))
    return fields


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
    return html.Div(
        children, style={"display": "flex", "flexDirection": "column", "gap": "12px"}
    )


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
