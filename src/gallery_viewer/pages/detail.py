"""Detail page — script editor + preview view at ``/``.

The detail page mounts ``Gallery._build_detail_layout()`` (the editor +
preview cluster) and owns *all* the callbacks that drive that view.

Why not on the Gallery class? Pages should own their own behavior. Keeping
the callbacks here makes the host (`Gallery`) a pure orchestrator and lets
the detail page be reasoned about, tested, and refactored in isolation.

The page module exposes:

- ``bind(gallery)`` — host calls this once during ``_build_app``; it stores a
  module-level reference and registers all page-scoped callbacks.
- ``_layout(**url_kwargs)`` — Dash calls this on every navigation to ``/``;
  returns the editor + preview layout from the bound Gallery.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html

from gallery_viewer._types import ScriptSections
from gallery_viewer.gallery import (
    _CONSOLE_STYLE,
    _SECTION_LABEL,
    _make_editor,
    _no_data,
    _no_plot,
)

if TYPE_CHECKING:
    from gallery_viewer.gallery import Gallery

_gallery: Gallery | None = None
_callbacks_registered = False


def bind(gallery: Gallery) -> None:
    """Attach the host Gallery and register page-scoped callbacks (idempotent)."""
    global _gallery
    _gallery = gallery
    _register_callbacks()


def _layout(**_url_kwargs: object) -> html.Div:
    if _gallery is None:
        return html.Div(
            "detail page used before bind()",
            style={"color": "var(--mantine-color-dimmed)"},
        )
    return html.Div(
        _build_detail_layout(_gallery),
        id="gv-detail-page",
    )


# ---------------------------------------------------------------------------
# Panels — each function returns a Dash component (or list) and is composable.
# Add a new panel = add a new function. Reposition a panel = change LAYOUT.
# Panels take the bound ``Gallery`` so they can read attrs (item_label,
# group_label, version_label, export_fn, extra_controls, ...).
# ---------------------------------------------------------------------------


def _panel_selectors(g: Gallery) -> Any:
    """Group dropdown stacked above version dropdown, with the refresh and
    new-group action icons in a small row below."""
    return dmc.Stack(
        [
            dmc.Select(
                id="gv-group",
                label=g.group_label,
                placeholder=f"Select {g.group_label.lower()}...",
                clearable=False,
                size="sm",
            ),
            dmc.Select(
                id="gv-version",
                label=g.version_label,
                clearable=False,
                size="sm",
            ),
            dmc.Group(
                [
                    dmc.ActionIcon(
                        "↻",
                        id="gv-refresh-btn",
                        variant="default",
                        size="lg",
                        n_clicks=0,
                        **{"aria-label": "Refresh"},
                    ),
                    dmc.ActionIcon(
                        "+",
                        id="gv-new-group-btn",
                        variant="default",
                        size="lg",
                        n_clicks=0,
                        **{"aria-label": "New group from uncharted data"},
                    ),
                ],
                gap="xs",
            ),
        ],
        gap="xs",
    )


def _panel_filter(g: Gallery) -> Any:
    """Tag-based version filter."""
    return html.Div(
        [
            dmc.Text("Filter", size="xs", c="dimmed", mb=4),
            dmc.Select(
                id="gv-tag-filter",
                placeholder="All versions",
                clearable=True,
                size="sm",
                mb="xs",
            ),
        ]
    )


def _panel_tags(g: Gallery) -> Any:
    """Tags for the current version (free-text TagsInput)."""
    return dmc.TagsInput(
        id="gv-tags-input",
        label="Tags",
        placeholder="Add a tag and press Enter",
        value=[],
        clearable=True,
        size="sm",
    )


def _panel_extras(g: Gallery) -> Any:
    """User-provided controls passed via ``Gallery(extra_controls=...)``."""
    return g.extra_controls or html.Div()


def _panel_params(g: Gallery) -> Any:
    """Parameter form fields (configurator) + update-script row + version diff."""
    return html.Div(
        [
            html.Div(id="gv-param-fields", style={"marginBottom": "4px"}),
            html.Div(id="gv-update-script-row", style={"marginBottom": "4px"}),
            html.Div(
                id="gv-version-diff",
                style={
                    "fontSize": "11px",
                    "color": "#8cb4d5",
                    "marginBottom": "4px",
                    "fontFamily": "monospace",
                },
            ),
        ]
    )


def _panel_editor(g: Gallery) -> Any:
    """Script source editor — collapsible via the ``Script`` switch."""
    return html.Div(
        [
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
                    dmc.Switch(
                        id="gv-show-script",
                        checked=False,
                        size="sm",
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
        ]
    )


def _panel_actions(g: Gallery) -> Any:
    """Primary action buttons: RUN, Update Script, Save Version, Export .py."""
    return dmc.Grid(
        [
            dmc.GridCol(
                dmc.Button(
                    "RUN",
                    id="gv-run-btn",
                    color="green",
                    size="sm",
                    n_clicks=0,
                    fullWidth=True,
                    leftSection=dmc.Loader(size="xs", id="gv-run-spinner"),
                ),
                span=3,
            ),
            dmc.GridCol(
                dmc.Button(
                    "Update Script",
                    id="gv-update-script-btn",
                    variant="default",
                    size="sm",
                    n_clicks=0,
                    fullWidth=True,
                ),
                span=3,
            ),
            dmc.GridCol(
                dmc.Button(
                    "Save Version",
                    id="gv-save-btn",
                    color="blue",
                    size="sm",
                    n_clicks=0,
                    fullWidth=True,
                ),
                span=3,
            ),
            dmc.GridCol(
                dmc.Button(
                    "Export .py",
                    id="gv-export-script-btn",
                    color="cyan",
                    variant="outline",
                    size="sm",
                    n_clicks=0,
                    fullWidth=True,
                ),
                span=3,
            ),
        ],
        style={"marginTop": "8px", "marginBottom": "6px"},
    )


def _panel_console(g: Gallery) -> Any:
    """Stdout / stderr from the script's last run."""
    return html.Div(
        [
            dmc.Text("Console", size="xs", c="dimmed", mb=4),
            html.Div(id="gv-console", style=_CONSOLE_STYLE),
        ]
    )


def _panel_plot(g: Gallery) -> Any:
    """Rendered plot output. Includes the ``Export`` image button if
    ``Gallery(export_fn=...)`` was provided."""
    export_btn: list = []
    if g.export_fn is not None:
        export_btn = [
            dmc.Button(
                "Export",
                id="export-btn",
                color="yellow",
                size="sm",
                n_clicks=0,
                ml="sm",
            ),
            dcc.Download(id="export-download"),
        ]
    return html.Div(
        [
            html.Div(
                [dmc.Text("Output", size="xs", c="dimmed", mb=4), *export_btn],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": "4px",
                },
            ),
            dcc.Loading(
                type="circle",
                color="var(--mantine-color-dimmed)",
                children=html.Div(
                    id="gv-output-panel",
                    style={
                        "backgroundColor": "var(--mantine-color-default)",
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
        ]
    )


def _panel_data(g: Gallery) -> Any:
    """First 50 rows of the input data for the current group."""
    return html.Div(
        [
            dmc.Text("Data (first 50 rows)", size="xs", c="dimmed", mb=4),
            html.Div(
                id="gv-data-panel",
                style={
                    "overflowX": "auto",
                    "maxHeight": "300px",
                    "overflowY": "auto",
                },
                children=_no_data(),
            ),
        ]
    )


def _modals(g: Gallery) -> Any:
    """Modals — mounted but not positioned in the grid."""
    return dmc.Modal(
        id="gv-save-modal",
        title="Save New Version",
        opened=False,
        size="md",
        children=[
            dmc.Text(
                "The script and plot will be saved to disk.",
                size="sm",
                mb="sm",
            ),
            dmc.TextInput(
                id="gv-save-author",
                label="Author (optional)",
                placeholder="e.g. Alice",
                size="sm",
            ),
            dmc.Textarea(
                id="gv-save-description",
                label="What changed? (optional)",
                placeholder=(
                    "Why this version exists — e.g. switched to log scale "
                    "because small categories were buried."
                ),
                minRows=3,
                autosize=True,
                mt="sm",
            ),
            dmc.Group(
                [
                    dmc.Button(
                        "Cancel",
                        id="gv-confirm-save-cancel",
                        variant="default",
                        size="sm",
                    ),
                    dmc.Button(
                        "Save",
                        id="gv-confirm-save-ok",
                        color="blue",
                        size="sm",
                    ),
                ],
                justify="flex-end",
                mt="md",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Layout config — list of rows; each row is a list of columns; each column
# is ``(span, [panel_functions])`` stacked top-to-bottom in that column.
#
# Rearrange the detail page entirely by editing this constant. To add a
# panel: write a ``_panel_xxx(g)`` function and reference it here.
# ---------------------------------------------------------------------------

PanelFn = Callable[["Gallery"], Any]
LAYOUT: list[list[tuple[int, list[PanelFn]]]] = [
    [
        # Middle column: the visual output is the focus.
        (7, [_panel_plot, _panel_console, _panel_data]),
        # Right column: all controls live here.
        (
            5,
            [
                _panel_selectors,
                _panel_filter,
                _panel_tags,
                _panel_extras,
                _panel_params,
                _panel_editor,
                _panel_actions,
            ],
        ),
    ],
]


def _build_detail_layout(g: Gallery) -> list:
    """Compose the detail-page layout from panels per ``LAYOUT``.

    Returns a list of dmc.Grid rows + the modal mount. To rearrange the
    page, edit ``LAYOUT`` (no need to touch this function).
    """
    rows = []
    for row in LAYOUT:
        cols = [
            dmc.GridCol(span=span, children=[fn(g) for fn in fns])
            for span, fns in row
        ]
        rows.append(dmc.Grid(cols))
    rows.append(_modals(g))
    return rows


def _register_callbacks() -> None:
    """Register all detail-page callbacks against the bound ``_gallery``.

    Idempotent — guarded so multiple ``bind`` calls (e.g. in tests) don't
    duplicate registrations.
    """
    global _callbacks_registered
    if _callbacks_registered:
        return
    _callbacks_registered = True

    # Helper for callbacks that need the gallery — they all do, but we
    # capture the reference at registration time via the module-level
    # ``_gallery`` attribute (bind() set it before this function ran).
    if _gallery is None:
        raise RuntimeError("_register_callbacks called before bind()")

    # -- Also load groups on initial plot select --
    # Prefers gv-edit-buffer's group when it belongs to this leaf, so
    # detail-page remount after a branch detour lands the user back on
    # the group they were editing (not the newest one).
    @dash.callback(
        Output("gv-group", "data", allow_duplicate=True),
        Output("gv-group", "value", allow_duplicate=True),
        Input("gv-plot-select", "data"),
        State("gv-edit-buffer", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def init_groups_for_plot(item_id, buffer):
        if not item_id:
            return [], None
        groups = _gallery.list_groups(item_id)
        opts = [{"label": d, "value": d} for d in groups]
        preferred = None
        if (
            isinstance(buffer, dict)
            and buffer.get("leaf_id") == item_id
            and buffer.get("group") in groups
        ):
            preferred = buffer["group"]
        return opts, (preferred or (groups[0] if groups else None))

    # -- Refresh button → reload groups + versions for current plot --
    @dash.callback(
        Output("gv-group", "data", allow_duplicate=True),
        Output("gv-group", "value", allow_duplicate=True),
        Output("gv-version", "data", allow_duplicate=True),
        Output("gv-version", "value", allow_duplicate=True),
        Input("gv-refresh-btn", "n_clicks"),
        State("gv-plot-select", "data"),
        State("gv-group", "value"),
        prevent_initial_call=True,
    )
    def refresh_groups(n_clicks, item_id, current_group):
        if not item_id:
            return [], None, [], None
        groups = _gallery.list_groups(item_id)
        group_opts = [{"label": d, "value": d} for d in groups]
        group_val = (
            current_group if current_group in groups else (groups[0] if groups else None)
        )
        versions = _gallery.list_versions(item_id, group_val) if group_val else []
        ver_opts = [{"label": f"v{v}", "value": v} for v in versions]
        ver_val = versions[-1] if versions else None
        return group_opts, group_val, ver_opts, ver_val

    # -- Update version dropdown when group changes --
    # Prefers gv-edit-buffer's version when it belongs to this
    # (leaf, group), so detail-page remount lands on the version the
    # user was editing rather than the latest.
    @dash.callback(
        Output("gv-version", "data"),
        Output("gv-version", "value", allow_duplicate=True),
        Input("gv-group", "value"),
        State("gv-plot-select", "data"),
        State("gv-edit-buffer", "data"),
        prevent_initial_call=True,
    )
    def update_versions(group, item_id, buffer):
        if not group:
            return [], None
        versions = _gallery.list_versions(item_id, group)
        opts = [{"label": f"v{v}", "value": v} for v in versions]
        preferred = None
        if (
            isinstance(buffer, dict)
            and buffer.get("leaf_id") == item_id
            and buffer.get("group") == group
        ):
            v = buffer.get("version")
            if v in versions or (v is not None and str(v) in {str(x) for x in versions}):
                preferred = v
        return opts, (preferred if preferred is not None else (versions[-1] if versions else None))

    # -- URL deep-link → selectors + override store (initial load + nav) --
    @dash.callback(
        Output("gv-plot-select", "data", allow_duplicate=True),
        Output("gv-group", "value", allow_duplicate=True),
        Output("gv-version", "value", allow_duplicate=True),
        Output("gv-url-overrides", "data"),
        Input("_pages_location", "search"),
        prevent_initial_call="initial_duplicate",
    )
    def apply_url(search):
        state = _gallery.parse_url_state(search or "")
        return (
            state["item"] or dash.no_update,
            state["group"] or dash.no_update,
            state["version"] or dash.no_update,
            state["param_overrides"] or None,
        )

    # -- Load script + data + plot + detect params --
    # Also restores in-progress edits from gv-edit-buffer when identity
    # matches: this is what makes detail ↔ branch ↔ detail navigation
    # non-destructive after the dash.Pages migration (which unmounts
    # and remounts the editor across page transitions).
    @dash.callback(
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
        State("gv-edit-buffer", "data"),
    )
    def load_version(group, version, item_id, url_overrides, buffer):
        if not group or not version:
            return (*(dash.no_update,) * 6,)
        version = str(version)
        sections = _gallery.load_script(item_id, group, version)
        script_text = sections.to_text()
        editor_text = script_text
        if (
            isinstance(buffer, dict)
            and buffer.get("leaf_id") == item_id
            and buffer.get("group") == group
            and str(buffer.get("version")) == version
            and buffer.get("script")
        ):
            editor_text = buffer["script"]
        param_fields = _build_param_fields(
            sections.configurator, overrides=url_overrides
        )
        data_children = _data_table(_gallery.load_data(item_id, group))
        plot_bytes = _gallery.load_artifact(item_id, group, version)
        plot_children = _plot_img(plot_bytes)
        b64 = base64.b64encode(plot_bytes).decode() if plot_bytes else None
        return (
            editor_text,
            param_fields,
            data_children,
            plot_children,
            b64,
            script_text,
        )

    # -- Write the edit buffer on editor change --
    # Persists mid-edit text so it survives page transitions. Clears
    # the buffer when the editor matches the clean (on-disk) script
    # so that "no unsaved work" leaves no stale buffer behind.
    @dash.callback(
        Output("gv-edit-buffer", "data"),
        Input("gv-editor-script", "value"),
        State("gv-plot-select", "data"),
        State("gv-group", "value"),
        State("gv-version", "value"),
        State("gv-clean-script-store", "data"),
        prevent_initial_call=True,
    )
    def write_edit_buffer(script, item_id, group, version, clean):
        if not item_id or not group or not version:
            return None
        if not script or script == clean:
            return None
        return {
            "leaf_id": item_id,
            "group": group,
            "version": str(version),
            "script": script,
        }

    # -- RUN button --
    @dash.callback(
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
        result = _gallery.run_script(item_id, sections, inject_vars=inject)
        console = result.output
        if not result.success:
            console += f"\n--- ERROR ---\n{result.error}"
        b64 = (
            base64.b64encode(result.image_bytes).decode()
            if result.image_bytes
            else None
        )
        return console or "(no output)", _render_outputs(result.items), b64

    # -- TAGS: load tags into the input when (item, group, version) changes --
    # Also refreshes the tag-filter dropdown's options to reflect any
    # tags that exist anywhere in the current group.
    @dash.callback(
        Output("gv-tags-input", "value"),
        Output("gv-tag-filter", "data"),
        Input("gv-version", "value"),
        State("gv-group", "value"),
        State("gv-plot-select", "data"),
    )
    def load_tags(version, group, item_id):
        if not group or not version:
            return [], []
        tags = _gallery.list_tags(item_id, group, version)
        all_tags = _gallery.all_tags(item_id, group)
        return tags, [{"label": t, "value": t} for t in all_tags]

    # -- TAGS: persist edits in the input back to the backend --
    # Diffs the input's value against the backend on every change and
    # adds/removes accordingly. Refreshes the tag-filter so newly
    # created tags become filterable immediately.
    @dash.callback(
        Output("gv-tag-filter", "data", allow_duplicate=True),
        Input("gv-tags-input", "value"),
        State("gv-group", "value"),
        State("gv-version", "value"),
        State("gv-plot-select", "data"),
        prevent_initial_call=True,
    )
    def save_tags(new_tags, group, version, item_id):
        if not group or not version:
            return dash.no_update
        new_set = {t.strip() for t in (new_tags or []) if t and t.strip()}
        current = set(_gallery.list_tags(item_id, group, version))
        for t in new_set - current:
            _gallery.add_tag(item_id, group, version, t)
        for t in current - new_set:
            _gallery.remove_tag(item_id, group, version, t)
        return [
            {"label": t, "value": t}
            for t in _gallery.all_tags(item_id, group)
        ]

    # -- TAGS: filter version dropdown by tag --
    @dash.callback(
        Output("gv-version", "data"),
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
        backend = _gallery._get_backend(item_id)
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
    @dash.callback(
        Output("gv-save-modal", "opened"),
        Input("gv-save-btn", "n_clicks"),
        Input("gv-confirm-save-ok", "n_clicks"),
        Input("gv-confirm-save-cancel", "n_clicks"),
        State("gv-save-modal", "opened"),
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
    @dash.callback(
        Output("gv-save-author", "value"),
        Input("gv-save-modal", "opened"),
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
    @dash.callback(
        Output("gv-console", "children", allow_duplicate=True),
        Output("gv-output-panel", "children", allow_duplicate=True),
        Output("gv-gallery-items", "data", allow_duplicate=True),
        Output("gv-group", "data", allow_duplicate=True),
        Output("gv-group", "value", allow_duplicate=True),
        Output("gv-version", "data", allow_duplicate=True),
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
        sections = _gallery.apply_params_to_script(script_code, param_values)

        new_version = _gallery.save_script(
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
        groups = _gallery.list_groups(item_id)
        group_opts = [{"label": d, "value": d} for d in groups]
        versions = _gallery.list_versions(item_id, save_group)
        ver_opts = [{"label": f"v{v}", "value": v} for v in versions]
        plot_bytes = _gallery.load_artifact(item_id, save_group, str(new_version))
        updated_script = sections.to_text()

        return (
            console,
            _plot_img(plot_bytes),
            _gallery.item_ids,
            group_opts,
            save_group,
            ver_opts,
            new_version,
            updated_script,
            updated_script,
        )

    # -- Update Script from Parameters --
    @dash.callback(
        Output("gv-editor-script", "value", allow_duplicate=True),
        Input("gv-update-script-btn", "n_clicks"),
        State("gv-editor-script", "value"),
        State({"type": "gv-param", "name": dash.ALL}, "value"),
        prevent_initial_call=True,
    )
    def update_script_from_params(n_clicks, script_code, param_values):
        if not script_code or not param_values:
            return dash.no_update
        return _gallery.apply_params_to_script(script_code, param_values).to_text()

    # -- Show/hide Update Script button based on param fields --
    @dash.callback(
        Output("gv-update-script-row", "children"),
        Input("gv-param-fields", "children"),
    )
    def toggle_update_script_visibility(param_fields):
        if param_fields:
            return html.Div(
                "Use form fields above to tweak parameters, "
                "then RUN to preview or Save Version to persist.",
                style={"fontSize": "11px", "color": "var(--mantine-color-dimmed)", "marginTop": "2px"},
            )
        return None

    # -- Feature 1: Toggle script editor visibility --
    @dash.callback(
        Output("gv-editor-wrapper", "style"),
        Input("gv-show-script", "checked"),
    )
    def toggle_editor(show):
        if show:
            return {"display": "block"}
        return {"display": "none"}

    # -- Feature 2: Version diff label + change note --
    @dash.callback(
        Output("gv-version-diff", "children"),
        Input("gv-version", "value"),
        State("gv-group", "value"),
        State("gv-plot-select", "data"),
    )
    def show_version_diff(version, group, item_id):
        if not group or not version:
            return ""
        text, color = _gallery.version_diff_label(item_id, group, version)
        note = _gallery.change_note(item_id, group, version)
        author = _gallery.author(item_id, group, version)
        children = [html.Div(text, style={"color": color})]
        # Author line — small, dim, italic. Skip if absent.
        if author:
            children.append(
                html.Div(
                    f"by {author}",
                    style={"color": "var(--mantine-color-dimmed)", "fontStyle": "italic"},
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
                        "color": "var(--mantine-color-dimmed)",
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
    @dash.callback(
        Output("gv-group", "data", allow_duplicate=True),
        Output("gv-group", "value", allow_duplicate=True),
        Output("gv-version", "data", allow_duplicate=True),
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
        uncharted = _gallery.list_uncharted_groups(item_id)
        if not uncharted:
            return (
                *(dash.no_update,) * 6,
                f"No new {_gallery.group_label.lower()}s found without scripts.",
                dash.no_update,
            )
        new_group = uncharted[0]
        template = _gallery.template_for_group(item_id, new_group)
        script_text = template.to_text()
        param_fields = _build_param_fields(template.configurator)
        groups = sorted(set(_gallery.list_groups(item_id) + [new_group]), reverse=True)
        group_opts = [{"label": d, "value": d} for d in groups]
        return (
            group_opts,
            new_group,
            [{"label": "v1 (new)", "value": "1"}],
            "1",
            script_text,
            param_fields,
            f"New {_gallery.group_label.lower()} {new_group} — edit and Save Version to create v1.",
            script_text,
        )

    # -- Feature 5: Dirty flag — store clean script on load --
    # (The clean-script-store is also updated in save_version above)

    # -- Feature 5: Confirm before navigating with unsaved changes --
    # We intercept nav_click and group/version changes via a clientside check.
    # For simplicity, we use a Store-based approach: compare editor vs clean store.

    # -- Feature 8: Export standalone script --
    @dash.callback(
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
            _gallery.export_inject_vars(item_id, group or "unknown", version or "0")
        )
        standalone = sections.to_full(inject_vars=inject)
        filename = (
            f"script_{group}_v{version}.py" if group and version else "script.py"
        )
        return dcc.send_string(standalone, filename)

    # -- Export (only if export_fn provided) --
    if _gallery.export_fn is not None:

        @dash.callback(
            Output("export-download", "data"),
            Input("export-btn", "n_clicks"),
            State("gv-plot-bytes-store", "data"),
            prevent_initial_call=True,
        )
        def export_plot(n_clicks, b64_data):
            if not b64_data:
                return dash.no_update
            raw_bytes = base64.b64decode(b64_data)
            exported = _gallery.export_fn(raw_bytes)  # type: ignore[misc]  # ty:ignore[call-non-callable]
            return dcc.send_bytes(exported, "exported_chart.png")


dash.register_page(__name__, path="/", layout=_layout)
