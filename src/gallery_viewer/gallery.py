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
import dash_mantine_components as dmc
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
    # Theme-aware via CSS light-dark(): the browser picks the matching
    # value based on the active ``color-scheme`` (which Mantine sets
    # from the MantineProvider's color scheme).
    "backgroundColor": (
        "light-dark(var(--mantine-color-gray-0), "
        "var(--mantine-color-dark-8))"
    ),
    "color": "var(--mantine-color-text)",
    "border": (
        "1px solid light-dark(var(--mantine-color-gray-3), "
        "var(--mantine-color-dark-4))"
    ),
    "padding": "10px",
    "borderRadius": "4px",
    "minHeight": "80px",
    "whiteSpace": "pre-wrap",
    "overflowY": "auto",
    "maxHeight": "200px",
}
_SECTION_LABEL = {
    "color": "var(--mantine-color-dimmed)",
    "fontSize": "11px",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "marginBottom": "2px",
    "marginTop": "10px",
}


# Conventional tag colors (Mantine color names). Anything not listed falls
# back to "gray". ``frozen`` reads as a warning even though it's purely
# informational — Save always creates a new version, so there's nothing
# to enforce.
_TAG_COLORS = {
    "published": "green",
    "final": "blue",
    "frozen": "red",
    "draft": "gray",
    "wip": "gray",
}


def _tag_badge(tag: str) -> Any:
    """Render a single tag as a dmc.Badge with conventional color."""
    return dmc.Badge(
        tag,
        color=_TAG_COLORS.get(tag, "gray"),
        radius="xl",
        size="sm",
        style={"marginRight": "4px"},
    )


def _editor_style(height: str = "200px") -> dict:
    return {
        **_MONOSPACE,
        "width": "100%",
        "height": height,
        "backgroundColor": "#1e1e1e",
        "color": "var(--mantine-color-text)",
        "border": "1px solid var(--mantine-color-default-border)",
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
# Theme presets
# ---------------------------------------------------------------------------

# Mapping from preset name → (forceColorScheme, mantine theme dict). The
# dict is passed verbatim to ``dmc.MantineProvider(theme=...)``; see
# https://mantine.dev/theming/theme-object/ for the full schema.
THEMES: dict[str, tuple[str, dict[str, Any]]] = {
    "dark": ("dark", {"primaryColor": "blue"}),
    "light": ("light", {"primaryColor": "blue"}),
    "monokai": ("dark", {"primaryColor": "gray"}),
}


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


def _overview_entry(group_path: str, indent_px: int) -> Any:
    """Render the per-branch ``Overview`` leaf as a ``dmc.NavLink``.

    Clicking writes ``_pages_location.pathname = "/branch/<group_path>"``
    so the gallery page mounts. NavLink is auto-themed by the surrounding
    ``MantineProvider`` (color-scheme reactive).
    """
    return dmc.NavLink(
        id={"type": "gv-overview", "index": group_path},
        label="Overview",
        leftSection=dmc.Text("▣", size="xs", c="dimmed"),
        n_clicks=0,
        style={"paddingLeft": f"{indent_px + 12}px"},
    )


def _render_tree_node(
    tree: dict,
    collapsed: list[str],
    active_plot: str | None,
    descriptions: dict[str, str],
    depth: int = 0,
    path_prefix: str = "",
) -> list:
    """Recursively render a sidebar tree node into Dash components.

    Each branch (and the root) gets an injected ``Overview`` leaf as its
    first child \u2014 clicking it opens the branch's gallery view. Branches
    themselves are collapse-only; they no longer navigate on click.
    """
    children: list = []
    indent = depth * 14

    # Inject an "Overview" leaf for the current branch (skip root —
    # empty path_prefix would not match the /branch/<branch_path>
    # template, and root's contents are already visible at top level).
    if path_prefix:
        children.append(_overview_entry(path_prefix, indent))

    # Render sub-groups first, then leaves
    group_keys = [k for k in tree if k != "__leaves__"]
    for group in group_keys:
        group_path = f"{path_prefix}/{group}" if path_prefix else group
        is_collapsed = group_path in collapsed
        chevron = "\u25b8" if is_collapsed else "\u25be"
        children.append(
            dmc.NavLink(
                id={"type": "gv-tree-group", "index": group_path},
                label=group.replace("_", " ").title(),
                leftSection=dmc.Text(chevron, size="xs", c="dimmed"),
                n_clicks=0,
                style={"paddingLeft": f"{indent + 8}px"},
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
        is_active = name == active_plot
        children.append(
            dmc.NavLink(
                id={"type": "gv-nav-item", "index": name},
                label=label,
                leftSection=dmc.Text("·", size="xs", c="dimmed"),
                active=is_active,
                n_clicks=0,
                style={"paddingLeft": f"{indent + 12}px"},
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
        "backgroundColor": "var(--mantine-color-default)",
        "border": "1px solid var(--mantine-color-default-border)",
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
                style={"fontSize": "28px", "color": "var(--mantine-color-dimmed)"},
            ),
            html.Div(
                label,
                style={
                    "fontWeight": "bold",
                    "fontSize": "13px",
                    "color": "var(--mantine-color-text)",
                },
            ),
            html.Div(
                description or "",
                style={"fontSize": "11px", "color": "var(--mantine-color-dimmed)"},
            ),
        ],
        id={"type": "gv-nav-item", "index": name},
        n_clicks=0,
        style=_gallery_card_style(),
    )


def _subfolder_card(group_path: str, leaf_count: int) -> Any:
    """Render a sub-group as a clickable card showing its leaf count.

    Uses ``gv-overview`` ids — clicking drills into the sub-branch's
    gallery (i.e. its Overview leaf). This is the only way to navigate
    into a branch now that branch-row clicks only collapse/expand.
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
                    "color": "var(--mantine-color-text)",
                },
            ),
            html.Div(
                f"{leaf_count} item{'s' if leaf_count != 1 else ''}",
                style={"fontSize": "11px", "color": "var(--mantine-color-dimmed)"},
            ),
        ],
        id={"type": "gv-overview", "index": group_path},
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
            f"Group not found: {group_path}", style={"color": "var(--mantine-color-dimmed)"}
        )

    cards: list = []
    sub_keys = [k for k in node if k != "__leaves__"]
    for sub in sub_keys:
        sub_path = f"{group_path}/{sub}" if group_path else sub
        cards.append(_subfolder_card(sub_path, _count_descendant_leaves(node[sub])))
    for leaf in node.get("__leaves__", []):
        cards.append(_leaf_card(leaf, descriptions.get(leaf, "")))

    if not cards:
        return html.Span("Empty group", style={"color": "var(--mantine-color-dimmed)"})

    title = group_path.replace("_", " ").replace("/", " / ").title() or "All"
    return html.Div(
        [
            html.Div(
                title,
                style={
                    "color": "var(--mantine-color-dimmed)",
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
        Visual theme preset. One of ``"dark"`` (default; dark + blue
        accent), ``"light"`` (light + blue accent), ``"monokai"`` (dark +
        gray accent). See ``THEMES`` for the full mapping.
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
        theme: str = "dark",
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
        if theme not in THEMES:
            raise ValueError(
                f"Unknown theme {theme!r}. Available: {sorted(THEMES)}"
            )
        self.theme = theme
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
    def item_ids(self) -> list[str]:
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
            external_stylesheets=[],
            title=self.title,
            use_pages=True,
            pages_folder="",
            suppress_callback_exceptions=True,
        )
        # Import + bind page modules. Importing triggers register_page().
        # bind() attaches the Gallery instance for callbacks to close over
        # (see PAGES_MIGRATION.md §1a).
        from gallery_viewer.pages import detail as _detail_page
        from gallery_viewer.pages import gallery as _gallery_page

        _detail_page.bind(self)
        _gallery_page.bind(self)

        app.layout = self._layout()
        self._register_callbacks()
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

    def _layout(self) -> dmc.MantineProvider:
        item_ids = list(self.backends.keys())

        # "Add <item>" button (only when config file is used)
        add_plot_btn = []
        if self._config_path:
            add_plot_btn = [
                dmc.Button(
                    f"+ Add {self.item_label}",
                    id="gv-add-plot-btn",
                    variant="default",
                    size="sm",
                    n_clicks=0,
                    fullWidth=True,
                    mt="sm",
                    mb="sm",
                ),
                dmc.Modal(
                    id="gv-add-plot-modal",
                    title=f"Add New {self.item_label}",
                    opened=False,
                    size="md",
                    children=[
                        dmc.TextInput(
                            id="gv-add-plot-name",
                            label=f"{self.item_label} name",
                            placeholder="e.g. revenue_chart",
                        ),
                        dmc.TextInput(
                            id="gv-add-plot-desc",
                            label="Description",
                            placeholder="Optional description",
                            mt="sm",
                        ),
                        dmc.Group(
                            [
                                dmc.Button(
                                    "Cancel",
                                    id="gv-add-plot-cancel",
                                    variant="default",
                                    size="sm",
                                ),
                                dmc.Button(
                                    "Create",
                                    id="gv-add-plot-submit",
                                    color="blue",
                                    size="sm",
                                ),
                            ],
                            justify="flex-end",
                            mt="md",
                        ),
                    ],
                ),
                html.Div(
                    id="gv-add-plot-feedback",
                    style={"fontSize": "12px", "color": "var(--mantine-color-dimmed)"},
                ),
            ]

        color_scheme, theme_dict = THEMES[self.theme]
        return dmc.MantineProvider(
            id="gv-mantine-provider",
            forceColorScheme=color_scheme,
            theme=theme_dict,
            children=dmc.Container(
            fluid=True,
            style={"padding": "16px"},
            children=[
                dmc.Grid(
                    dmc.GridCol(
                        html.Div(
                            [
                                dmc.Title(
                                    self.title,
                                    order=3,
                                    style={"marginBottom": 0},
                                ),
                                dmc.Select(
                                    id="gv-theme-select",
                                    data=[
                                        {"value": k, "label": k.title()}
                                        for k in THEMES
                                    ],
                                    value=self.theme,
                                    size="xs",
                                    clearable=False,
                                    allowDeselect=False,
                                    style={"width": "110px"},
                                ),
                            ],
                            style={
                                "display": "flex",
                                "justifyContent": "space-between",
                                "alignItems": "center",
                                "marginBottom": "12px",
                            },
                        ),
                    )
                ),
                # Persists the user's theme choice across sessions; the
                # apply_theme callback rebroadcasts it onto the
                # MantineProvider on every page load.
                dcc.Store(
                    id="gv-theme-store",
                    storage_type="local",
                    data=self.theme,
                ),
                dmc.Grid(
                    [
                        # ── GALLERY SIDEBAR ───────────────────────────────
                        dmc.GridCol(
                            span=2,
                            children=[
                                dmc.Text(
                                    f"{self.item_label}s",
                                    size="xs",
                                    c="dimmed",
                                    tt="uppercase",
                                    style={"letterSpacing": "0.06em"},
                                    mb="sm",
                                ),
                                dcc.Input(
                                    id="gv-search",
                                    type="text",
                                    placeholder="Filter...",
                                    debounce=False,
                                    style={
                                        "width": "100%",
                                        "marginBottom": "8px",
                                        "backgroundColor": "var(--mantine-color-default-hover)",
                                        "color": "var(--mantine-color-text)",
                                        "border": "1px solid var(--mantine-color-default-border)",
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
                                    data=item_ids[0] if item_ids else None,
                                ),
                                dcc.Store(id="gv-gallery-items"),
                                dcc.Store(id="gv-sidebar-collapsed", data=[]),
                            ],
                        ),
                        # Main panel — Dash Pages mounts the active page
                        # here. ``/`` mounts the detail editor+preview;
                        # ``/branch/<x>`` mounts the gallery card grid.
                        dmc.GridCol(span=10, children=[dash.page_container]),
                    ]
                ),
                dcc.Store(id="gv-plot-bytes-store"),
                # Track the last-loaded script text for dirty detection
                dcc.Store(id="gv-clean-script-store"),
                # URL deep-linking — selectors + configurator param overrides.
                # We don't declare our own dcc.Location: dash.page_container
                # auto-mounts dcc.Location(id="_pages_location"), which is
                # the *only* Location whose pathname changes drive page
                # routing. Sibling Location components don't observe each
                # other's pushState calls, so writing to a custom id leaves
                # the page_container stale. All our URL-driven callbacks
                # target/read "_pages_location".
                dcc.Store(id="gv-url-overrides"),
                # In-progress edit buffer (session-scoped). Detail page
                # writes mid-edit script text + identity (leaf/group/version)
                # here on editor change; on remount it restores the buffer
                # if identity still matches. Solves the Pages-migration
                # regression where detail ↔ branch ↔ detail navigation
                # would otherwise wipe unsaved typing. Schema:
                #     {"leaf_id": str, "group": str, "version": str,
                #      "script": str}
                dcc.Store(id="gv-edit-buffer", storage_type="session"),
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
            ),
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
            * ``("v1 — initial version", "var(--mantine-color-dimmed)")`` for v1
            * ``("v{n} — no parameter changes from v{n-1}", "var(--mantine-color-dimmed)")`` for unchanged
            * ``("v{n} — <comma-joined diff>", "#8cb4d5")`` for changed
        """
        version = str(version)
        if version == "1":
            return ("v1 — initial version", "var(--mantine-color-dimmed)")
        prev_version = str(int(version) - 1)
        diff = self.version_diff(item_id, group, version)
        if not diff:
            return (f"v{version} — no parameter changes from v{prev_version}", "var(--mantine-color-dimmed)")
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

    def _register_callbacks(self) -> None:
        # -- Theme: persist the user's choice and apply it to the provider --
        # Two callbacks: the select pushes to local-storage; the storage
        # rebroadcasts to the MantineProvider props. Splitting them lets
        # the provider apply the persisted theme on every reload (the
        # store's initial-call fires apply_theme without user interaction).
        @dash.callback(
            Output("gv-theme-store", "data"),
            Input("gv-theme-select", "value"),
            prevent_initial_call=True,
        )
        def save_theme_choice(theme: str) -> str:
            return theme if theme in THEMES else dash.no_update

        @dash.callback(
            Output("gv-mantine-provider", "forceColorScheme"),
            Output("gv-mantine-provider", "theme"),
            Output("gv-theme-select", "value"),
            Input("gv-theme-store", "data"),
        )
        def apply_theme(theme: str | None) -> tuple[str, dict, str]:
            if theme not in THEMES:
                theme = "dark"
            color_scheme, theme_dict = THEMES[theme]
            return color_scheme, theme_dict, theme

        # -- Render sidebar nav list (tree-aware) --
        @dash.callback(
            Output("gv-gallery-sidebar", "children"),
            Input("gv-gallery-items", "data"),
            Input("gv-search", "value"),
            Input("gv-plot-select", "data"),
            Input("gv-sidebar-collapsed", "data"),
        )
        def render_sidebar(_, search, active_plot, collapsed):
            names = self.item_ids
            if search and search.strip():
                q = search.lower()
                names = [n for n in names if q in n.lower()]
            if not names:
                return html.Span("No plots", style={"color": "var(--mantine-color-dimmed)"})
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

        # -- Tree-group click: toggle collapse only --
        # Branches no longer navigate; the gallery for a branch is reached
        # via its injected "Overview" leaf (id type ``gv-overview``).
        @dash.callback(
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

        # -- Overview-leaf click → navigate to that branch's gallery page --
        # Used by both the sidebar Overview leaves and the subfolder cards
        # rendered inside a gallery view (drill-down).
        @dash.callback(
            Output("_pages_location", "pathname", allow_duplicate=True),
            Output("_pages_location", "search", allow_duplicate=True),
            Input({"type": "gv-overview", "index": ALL}, "n_clicks"),
            prevent_initial_call=True,
        )
        def overview_click(n_clicks_list):
            from urllib.parse import quote
            if not any(n_clicks_list):
                return dash.no_update, dash.no_update
            triggered = ctx.triggered_id
            if triggered is None:
                return dash.no_update, dash.no_update
            group_path = triggered["index"]
            # Empty group_path = root overview. Use trailing "" for the
            # path_template so Dash still matches /branch/<branch_path>.
            return f"/branch/{quote(group_path, safe='')}", ""

        # -- Click nav item → navigate to detail page for that leaf --
        # The URL becomes the source of truth: pathname goes to "/" and
        # ?id=<leaf> drives selector population on the detail page.
        # Only outputs that live in the shell are written here — gv-group
        # lives in the detail page, so its options/value are populated by
        # init_groups_for_plot once the page remounts. (If we wrote them
        # here, Dash would skip the *entire* callback when the detail page
        # is unmounted, breaking nav from the gallery view.)
        @dash.callback(
            Output("gv-plot-select", "data", allow_duplicate=True),
            Output("_pages_location", "pathname", allow_duplicate=True),
            Output("_pages_location", "search", allow_duplicate=True),
            Input({"type": "gv-nav-item", "index": dash.ALL}, "n_clicks"),
            prevent_initial_call=True,
        )
        def nav_click(n_clicks_list):
            if not any(n_clicks_list):
                return (dash.no_update,) * 3
            triggered = ctx.triggered_id
            if triggered is None:
                return (dash.no_update,) * 3
            item_id = triggered["index"]
            return (
                item_id,
                "/",
                f"?{self.item_url_key}={item_id}",
            )


        # -- Add Plot (only if config file is used) --
        if self._config_path:

            @dash.callback(
                Output("gv-add-plot-modal", "opened"),
                Input("gv-add-plot-btn", "n_clicks"),
                Input("gv-add-plot-cancel", "n_clicks"),
                Input("gv-add-plot-submit", "n_clicks"),
                State("gv-add-plot-modal", "opened"),
                prevent_initial_call=True,
            )
            def toggle_add_plot_modal(n_open, n_cancel, n_submit, is_open):
                trigger = ctx.triggered_id
                return trigger == "gv-add-plot-btn"

            @dash.callback(
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
                return f"Created '{name}'", name, self.item_ids


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
                    dmc.NumberInput(
                        id={"type": "gv-param", "name": name},
                        label=label,
                        value=default,
                        size="sm",
                        mb="xs",
                    ),
                ]
            )
        else:
            field = html.Div(
                [
                    dmc.TextInput(
                        id={"type": "gv-param", "name": name},
                        label=label,
                        value=str(default),
                        size="sm",
                        mb="xs",
                    ),
                ]
            )
        fields.append(field)

    if fields:
        fields.insert(0, html.Div("Parameters", style=_SECTION_LABEL))
    return fields


def _no_plot():
    return html.Span("No plot available", style={"color": "var(--mantine-color-dimmed)"})


def _no_data():
    return html.Span("No data loaded", style={"color": "var(--mantine-color-dimmed)"})


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
            "backgroundColor": "var(--mantine-color-default-hover)",
            "color": "var(--mantine-color-text)",
            "fontWeight": "bold",
            "fontFamily": "monospace",
            "fontSize": "12px",
        },
        style_cell={
            "backgroundColor": "var(--mantine-color-default)",
            "color": "var(--mantine-color-text)",
            "fontFamily": "monospace",
            "fontSize": "12px",
            "border": "1px solid var(--mantine-color-default-border)",
            "padding": "4px 8px",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#252525"},
        ],
        page_size=50,
    )
