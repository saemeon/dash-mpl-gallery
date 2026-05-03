# Migration inventory — components & callbacks

Step 0 of [PAGES_MIGRATION.md](PAGES_MIGRATION.md). Source of truth: every
`@app.callback` and every `id=` in [`gallery.py`](src/gallery_viewer/gallery.py)
as of the pre-migration commit, classified by where it will live after
the move.

Classes:

- **shell** — must be present on every URL (always-mounted layout)
- **sidebar** — owned by the sidebar tree component (lives in shell)
- **detail** — only meaningful on `/` (the editor + preview view)
- **gallery** — only meaningful on `/branch/<path>`
- **delete** — replaced by URL routing, will not exist post-migration

## Callbacks (27 total)

| # | Function | Line | Class | Notes |
| --- | --- | --- | --- | --- |
| 1 | `render_sidebar` | 1557 | sidebar | Renders the tree from `gv-gallery-items` + search + collapsed state. |
| 2 | `toggle_group` | 1587 | sidebar | Tree-group click. Currently writes `gv-sidebar-collapsed` AND `gv-active-group`. **After:** write `gv-sidebar-collapsed` AND navigate to `/branch/<path>`. |
| 3 | `show_pane` | 1611 | **delete** | Pane dispatch — replaced by `dash.page_container`. |
| 4 | `render_gallery_panel` | 1627 | **delete** | Move logic into `pages/gallery.py` `_layout(path=...)`. |
| 5 | `nav_click` | 1652 | sidebar | Tree-leaf click. Currently writes `gv-plot-select` and clears `gv-active-group`. **After:** navigate to `/?id=<name>`. |
| 6 | `init_groups_for_plot` | 1670 | detail | Loads group dropdown options when `gv-plot-select` changes. **After:** triggered by URL `?id=` change on detail-page mount. |
| 7 | `refresh_groups` | 1688 | detail | Refresh button. |
| 8 | `update_versions` | 1709 | detail | Group→version cascade. |
| 9 | `apply_url` | 1725 | detail | Parses query params into selectors + override store. **After:** still parses, but inside `pages/detail.py`. |
| 10 | `load_version` | 1747 | detail | Loads script + data + plot when group/version changes. Big one. |
| 11 | `run_script` | 1780 | detail | RUN button. |
| 12 | `update_tags_row` | 1804 | detail | |
| 13 | `toggle_edit_tags_modal` | 1824 | detail | |
| 14 | `manage_tags` | 1865 | detail | Add/remove tags via pattern-matched `gv-tag-remove` ids. |
| 15 | `filter_versions_by_tag` | 1917 | detail | |
| 16 | `toggle_save_modal` | 1944 | detail | |
| 17 | `prefill_author_from_context` | 1959 | detail | |
| 18 | `save_version` | 1986 | detail | Save button — write script, refresh dropdowns. |
| 19 | `update_script_from_params` | 2047 | detail | "Update Script" button. |
| 20 | `toggle_update_script_visibility` | 2057 | detail | |
| 21 | `toggle_editor` | 2071 | detail | Read-only switch. |
| 22 | `show_version_diff` | 2083 | detail | |
| 23 | `new_group_from_data` | 2133 | detail | "New Group" (+) button. |
| 24 | `export_standalone` | 2178 | detail | "Export .py" button. |
| 25 | `export_plot` (conditional) | 2206 | detail | Only registered when `export_fn` provided. |
| 26 | `toggle_add_plot_modal` (conditional) | 2224 | sidebar | Only when `config_path` set. |
| 27 | `create_plot` (conditional) | 2237 | sidebar | Only when `config_path` set. Writes `gv-plot-select` + `gv-gallery-items`. |

**Tally after migration:** 2 deleted, 6 sidebar, 19 detail, 0 gallery (the
gallery's only callback work happens at layout-build time via `_layout(path=...)`).

## Components by id

### Shell (always mounted)

| id | Component | Why shell |
| --- | --- | --- |
| `gv-url` | `dcc.Location` | One per app. |
| `gv-context` | `dcc.Store(session)` | Ambient identity (author, env). Survives transitions. |
| `gv-edit-buffer` (NEW per §3) | `dcc.Store(session)` | In-progress edit buffer. |
| `gv-confirm-navigate` | `dcc.ConfirmDialog` | Dirty-warning dialog must fire from any page. |

### Sidebar (in shell layout)

| id | Component | Notes |
| --- | --- | --- |
| `gv-search` | `dcc.Input` | Filter the tree. |
| `gv-gallery-sidebar` | `html.Div` | Tree render target. |
| `gv-plot-select` | `dcc.Store` | Current leaf id. **Candidate for removal** if URL is sole source of truth — defer decision to step 4. |
| `gv-gallery-items` | `dcc.Store` | Triggers `render_sidebar` re-runs (currently used as a refresh signal). |
| `gv-sidebar-collapsed` | `dcc.Store` | Tree expand/collapse state. |
| `gv-add-plot-btn`, `gv-add-plot-modal`, `gv-add-plot-name`, `gv-add-plot-desc`, `gv-add-plot-submit`, `gv-add-plot-cancel`, `gv-add-plot-feedback` | various | "Add plot" UI; only mounted when `config_path` is set. |
| `{"type": "gv-tree-group", "index": <path>}` | pattern | Group header / subfolder card click target. |
| `{"type": "gv-nav-item", "index": <name>}` | pattern | Leaf click target. |

### Detail page (`/`)

| id | Component | Notes |
| --- | --- | --- |
| `gv-group`, `gv-version` | `dcc.Dropdown` | Selectors. |
| `gv-refresh-btn`, `gv-new-group-btn` | `dbc.Button` | |
| `gv-tag-filter`, `gv-tags-row`, `gv-edit-tags-btn` | various | Tag UI. |
| `gv-param-fields`, `gv-update-script-row`, `gv-version-diff` | `html.Div` | |
| `gv-show-script` | `dbc.Switch` | Read-only toggle. |
| `gv-editor-script`, `gv-editor-wrapper` | editor | DashAce or Textarea. |
| `gv-run-btn`, `gv-run-spinner`, `gv-update-script-btn`, `gv-save-btn`, `gv-export-script-btn` | buttons | |
| `gv-console` | `html.Div` | Stdout/stderr from RUN. |
| `gv-save-modal`, `gv-save-author`, `gv-save-description`, `gv-confirm-save-ok`, `gv-confirm-save-cancel` | modal | |
| `gv-edit-tags-modal`, `gv-edit-tags-current`, `gv-edit-tags-done`, `gv-new-tag-input`, `gv-add-tag-btn` | modal | |
| `gv-output-panel` | `html.Div` (inside `dcc.Loading`) | Plot preview. |
| `gv-data-panel` | `html.Div` | Data table. |
| `gv-plot-bytes-store` | `dcc.Store` | Last rendered plot bytes (for export). Should move to `gv-edit-buffer` or stay here — decide in step 5. |
| `gv-clean-script-store` | `dcc.Store` | Last-loaded script text (for dirty detection). Folds into `gv-edit-buffer`. |
| `gv-url-overrides` | `dcc.Store` | Parsed `?script_*=` overrides. |
| `gv-export-script-download` | `dcc.Download` | |
| `export-btn`, `export-download` | conditional | Only when `export_fn` provided. |
| `{"type": "gv-tag-remove", "index": <tag>}` | pattern | Tag chip remove button. |
| `{"type": "gv-param", "name": <param>}` | pattern | CONFIGURATOR form fields. |

### Gallery page (`/branch/<path>`)

| id | Component | Notes |
| --- | --- | --- |
| (none with explicit ids — cards reuse `gv-tree-group` / `gv-nav-item` pattern ids from sidebar) | | |

The gallery page is **stateless** — its only DOM is the cards grid,
generated from `path` at layout time. Click handlers for the cards are
the same sidebar handlers (item 5 + item 2 in the callback table).

## Items being removed

| id | Reason |
| --- | --- |
| `gv-active-group` (Store) | URL is the source of truth for "active branch". |
| `gv-pane-gallery`, `gv-pane-detail` (Divs) | Replaced by `dash.page_container`. |
| `show_pane` callback | Same. |
| `render_gallery_panel` callback | Replaced by `pages/gallery.py` `_layout(path=...)`. |

## Items being added

| id | Type | Purpose |
| --- | --- | --- |
| `gv-edit-buffer` | `dcc.Store(session)` | In-progress edit buffer (§3). |
| `gv-is-dirty` | `dcc.Store` (clientside) | Computed from editor + params; gates the confirm dialog. |
| `gv-pending-nav` | `dcc.Store` | Holds the URL the user tried to navigate to before the dirty warning interrupted; used to re-issue the navigation on confirm. |

## Sanity check

Total ids today (by grep): ~60 explicit + 4 pattern-matched.
Total callbacks today: 27 (24 always + 3 conditional).
After migration: ~58 + 4 pattern-matched, 25 callbacks (2 deleted, 0
added — buffer logic folds into existing detail callbacks).
