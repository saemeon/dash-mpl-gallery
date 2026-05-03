# Pages migration — plan

A standing plan for migrating dash-script-gallery from the current
single-layout-with-pane-dispatch model to `dash.Pages`. This file is meant
to be edited as we discover things during the migration, not deleted when
we're done.

## 1. Goal

Move the gallery from "one big layout with two hidden panes, dispatched by
a Store" to "one app, multiple Pages, dispatched by URL". The end-state:

- The detail editor lives at `/` (with the existing
  `?id=&group=&version=` query-param deep-linking unchanged).
- The branch gallery lives at `/branch/<path>` (a new, shareable URL).
- The sidebar tree lives in the app shell, persistent across pages.
- Browser back/forward, deep links, and "open in new tab" all work.

Non-goals: re-skinning, adding new features, rewriting the storage backend,
or changing the public `Gallery(...)` API. Downstream consumers
(`corpframe-gallery`) must keep working with the same constructor.

## 2. Page structure

```text
app shell (always mounted)
├── header (title)
├── sidebar (tree + search + add-plot button)
├── dcc.Location (URL = source of truth for "what view")
├── dcc.Stores (cross-page state — see §3)
└── page container  ← Dash routes the active page here

pages/
├── detail.py    → registers path="/"
│                  layout: editor + preview cluster
│                  callbacks: load_version, save, run, tag edit, …
│                  reads URL: ?id=&group=&version=
│
└── gallery.py   → registers path_template="/branch/<branch_path>"
                   layout: card grid (subfolder cards + leaf cards)
                   callbacks: render the grid for the current branch
                   reads URL: branch_path = the branch (slash URL-encoded)
```

**Shell vs page boundary.** A component lives in the shell if (a) it must
be mounted on every URL, or (b) its state must survive page transitions.
Otherwise it lives in its page. Concretely:

| Component | Shell or page? | Why |
| --- | --- | --- |
| Header (title) | shell | always visible |
| Sidebar tree | shell | always visible; clicks drive URL |
| `dcc.Location` | shell | one per app |
| `dcc.Stores` for cross-page state (see §3) | shell | survive transitions |
| Editor, parameter form, preview, console | detail page | only meaningful in detail view |
| Save / Edit-tags / Add-plot modals | detail page | only triggered from detail |
| Gallery cards grid | gallery page | only meaningful in gallery view |

**Why a path param (`/branch/<path>`), not a query param (`?branch=…`).**
Query params are for filters/state-of-the-current-view; paths are for
"which view". `/branch/finance` reads as a thing you can bookmark and
share; `?branch=finance` reads as configuration. This also matches how
the existing detail URL is structured (`/` is the view, `?id=…&group=…`
are selectors within it).

## 3. State preservation across page transitions

This is the load-bearing concern that almost killed the migration. Pages
unmounts inactive page layouts. By default, anything typed into the
editor would be **gone** the moment the user clicks a tree branch. Not
acceptable for an editing surface.

### What needs to survive

| State | Source | Survival? | Rationale |
| --- | --- | --- | --- |
| Mid-edit script text | `gv-editor-script` | **yes** | Typed but not saved; losing this is a real data loss. |
| Form parameter values | `gv-param-*` (pattern) | **yes** | User adjusted a slider; same data-loss concern. |
| Console output | `gv-console` | **yes** (cheap) | "Why did my last RUN say what it said?" |
| Rendered plot bytes | `gv-plot-bytes-store` | **yes** | Recomputing costs a subprocess run; preserve. |
| Selected `id`/`group`/`version` | URL query params | **yes** (in URL) | Already URL state; re-read on mount. |
| Tag filter selection | `gv-tag-filter` | **no** | Filter is a transient lens; OK to reset. |
| Open modals | `gv-*-modal` | **no** | Modals always start closed on mount. |

### Strategy: a single "in-progress edit buffer", keyed by leaf id

One shell-level `dcc.Store(storage_type="session")`:

```python
{
    "leaf_id": "finance/revenue",   # which script the buffer belongs to
    "group": "20260101",            # which (group, version) it was loaded from
    "version": "3",
    "script": "<text>",             # mid-edit script text
    "params": {...},                # form values
    "console": "...",               # last console output
    "plot_b64": "..."               # last rendered plot
}
```

On detail page mount:

1. Page reads URL → `id`, `group`, `version`.
2. Page reads buffer Store. If `(leaf_id, group, version)` matches URL,
   **restore the buffer** into editor / params / console / preview.
   Otherwise **discard the buffer** and load fresh from disk.

On editor / param change (debounced, ~300 ms):

1. Page writes the buffer Store with the current state.

On Save:

1. Page clears the buffer (now persisted to disk; nothing to preserve).

### Why one buffer, not a dict-by-leaf

A dict-by-leaf would let you preserve multiple in-progress edits across
many leaves. We don't want that:

- It encourages forgotten edits accumulating in session storage.
- Session storage has a ~5MB limit; large script bodies × many leaves
  would hit it.
- The mental model "the editor remembers my unsaved work for the
  current script" is simpler than "the editor remembers all my unsaved
  work for everything".

### Confirm-on-loss UX

The buffer covers detail↔gallery↔detail (same leaf). Anything else
that would discard unsaved work needs an explicit confirm dialog:

| Navigation | Buffer covers it? | Confirm dialog needed? |
| --- | --- | --- |
| Detail (leaf A) → gallery → detail (leaf A) | yes | no |
| Detail (leaf A) → detail (leaf A), different version | partial — see below | yes |
| Detail (leaf A) → detail (leaf B) | no — buffer would be discarded on mount | **yes** |
| Detail (leaf A) → close tab / browser back to non-app URL | no — `beforeunload` only | **yes** (browser-level) |
| Gallery (branch X) → gallery (branch Y) | no state to lose | no |

"Unsaved work" = any of: editor text differs from on-disk script,
parameter form values differ from script defaults, console output
not yet acted on. The dirty check should be one boolean derived from
all of these (clientside-callable so the dialog fires before the
navigation, not after).

Implementation:

- A clientside callback computes `is_dirty` whenever editor or params
  change.
- Tree leaf clicks (and version dropdown changes) check `is_dirty`
  via a clientside guard. If dirty, show `dcc.ConfirmDialog`. On OK,
  proceed with navigation; on Cancel, suppress it.
- `beforeunload` for tab close / external nav — set window listener
  via clientside callback when `is_dirty` is true.

This generalizes the old B7 (dirty-flag navigation warning) and pairs
with the buffer: buffer = "we tried to preserve your work
automatically", confirm = "we couldn't, are you sure?".

> **Note:** the version-dropdown case (same leaf, different version)
> currently loads-on-change without warning. After migration it
> should also confirm if dirty — switching versions reloads the
> editor, blowing away unsaved edits to the current version.

## 4. Migration steps

Each step ends with a verifiable checkpoint (tests pass, app builds, or
a manual click-through still works). Do not start step N+1 until N is
green.

### Step 0 — inventory (read-only)

Before touching code, produce two grep tables:

- **callbacks**: every `@app.callback`, its inputs, outputs, and the
  pane it logically belongs to (detail / gallery / shell).
- **components**: every `id=...` in the layout, classified the same way.

Write the result into `MIGRATION_INVENTORY.md`. This is the cheat sheet
the rest of the migration follows.

**Checkpoint:** the table accounts for every existing callback and id.
No item should land in "shell" by default — push everything to a page
unless it must be on every URL.

### Step 1 — choose the page registration mechanism

`dash.Pages` supports two registration styles:

1. **Auto-discovery** from a `pages/` folder. Cleanest for apps,
   awkward for installable libraries (the folder must be discoverable
   at `pages_folder=...`, and the lookup happens at import time).
2. **Explicit** via `dash.register_page(__name__, path=..., layout=...)`
   called from any module. Clean for libraries, slightly more code.

**Decision: explicit.** Inside `gallery_viewer.pages.detail` and
`gallery_viewer.pages.gallery`, call `dash.register_page` at import
time. `Gallery._build_app` instantiates `dash.Dash(use_pages=True,
pages_folder="")` and then imports the page modules to trigger
registration.

This avoids any path-sniffing at install time and keeps the migration
local to one package.

### Step 1a — callback decorator and Gallery access

**Rule:** every callback uses `@dash.callback`, never `@app.callback`.
The `app` object stays inside `Gallery._build_app` and is never passed
to page modules. This keeps page modules:

- Importable in isolation (no app dependency)
- Decoupled from how the app is constructed
- Free to be tested without instantiating Dash

**Pattern for accessing Gallery state from a page module.** Callbacks
need to call `gallery.list_versions(...)`, `gallery.load_script(...)`,
etc. The page module exposes a module-level `bind(g: Gallery)` function:

```python
# gallery_viewer/pages/detail.py
import dash
from dash import Input, Output, State, callback

_gallery: "Gallery | None" = None

def bind(gallery: "Gallery") -> None:
    """Attach the Gallery instance and register page-scoped callbacks.
    Must be called exactly once, before app.run.
    """
    global _gallery
    _gallery = gallery
    _register_callbacks()

def _layout(**url_kwargs):
    assert _gallery is not None, "detail page used before bind()"
    return _build_detail_layout(_gallery, **url_kwargs)

dash.register_page(__name__, path="/", layout=_layout)

def _register_callbacks() -> None:
    @callback(Output(...), Input(...))
    def some_callback(...):
        return _gallery.list_versions(...)   # closure over module-level _gallery
    # ...
```

`Gallery._build_app` then does:

```python
from gallery_viewer.pages import detail, gallery_page
detail.bind(self)
gallery_page.bind(self)
```

The module-level `_gallery` is mutable but written exactly once at app
boot — same lifecycle as `app` itself. Globals are usually a smell,
but here the pages are deliberately app-singleton and the alternative
(threading `gallery` through every callback definition) is worse.

### Step 2 — scaffold pages with empty layouts

Goal: get URL routing working before moving any logic.

- Create `gallery_viewer/pages/__init__.py` (empty).
- Create `gallery_viewer/pages/detail.py` with
  `dash.register_page(__name__, path="/", layout=html.Div("detail
  placeholder"))`.
- Create `gallery_viewer/pages/gallery.py` with
  `dash.register_page(__name__, path_template="/branch/<path:path>",
  layout=lambda path=None: html.Div(f"gallery placeholder: {path}"))`.
- Update `Gallery._build_app` to pass `use_pages=True, pages_folder=""`
  and import the page modules.
- Replace the existing top-level layout with: header + sidebar +
  `dash.page_container` + the existing shell-level Stores.

**Checkpoint:** `g.app` builds; visiting `/` shows the detail
placeholder; visiting `/branch/finance` shows the gallery placeholder
with the path threaded through. **Do not** move any callbacks yet.

### Step 3 — move the gallery view into its page

Smaller of the two pages; do it first to validate the pattern.

- Move `_render_gallery_view` and the gallery layout factory into
  `pages/gallery.py`.
- The page's `layout` becomes a function that receives `path=...` from
  the URL and returns `_render_gallery_view(...)` for that branch.
- Delete `render_gallery_panel` from `gallery.py` (its work is now done
  at layout-build time, not at callback time).
- Delete `gv-pane-gallery`, `gv-pane-detail`, and `show_pane` —
  pane dispatch is now URL routing.
- Update tree branch click: instead of writing `gv-active-group`,
  navigate via `dcc.Location.pathname = f"/branch/{path}"`.

**Checkpoint:** clicking a tree branch navigates to `/branch/...` and
the gallery renders. The detail view is broken at this point — that's
expected; step 4 fixes it.

### Step 4 — move the detail view into its page

- Move the editor + parameter form + preview cluster into
  `pages/detail.py`'s layout.
- Move all detail-only callbacks (`load_version`, `update_versions`,
  `save_*`, `run_*`, `update_script`, tag-edit, modals, …) into the
  same module. They are registered against `app` via `@callback` (the
  page-aware decorator), or `@app.callback` if we keep an `app`
  reference imported.
- Tree leaf click: navigate to
  `/?{item_url_key}=<id>&{group_url_key}=<g>&{version_url_key}=<v>`
  via `dcc.Location.search`.
- The existing `apply_url` callback that parses query params stays —
  but it now lives in `pages/detail.py` (only meaningful there).

**Checkpoint:** clicking a leaf navigates to `/` with the correct
selectors; the detail view loads as before; save / run / export still
work.

### Step 5 — implement the in-progress edit buffer (per §3)

- Add a shell-level `dcc.Store(id="gv-edit-buffer",
  storage_type="session")`.
- In `pages/detail.py`:
  - On editor / param change (debounced), write the buffer.
  - On layout mount (= page navigation), check the buffer; if its
    `(leaf_id, group, version)` matches the URL, restore. Otherwise
    discard and load fresh from disk.
  - On Save success, clear the buffer.
- Add the dirty-warning ConfirmDialog for cross-leaf navigation
  (replaces the partial B7).

**Checkpoint:** type into editor → click branch → click back to leaf →
text is restored. Type into editor → click a different leaf → confirm
dialog. Save → buffer cleared, navigating away no longer restores.

### Step 6 — clean up

- Remove `gv-active-group` (replaced by URL).
- Remove the pane wrapper Divs (replaced by `dash.page_container`).
- Remove any callback Outputs that referenced the now-deleted ids.
- Update `_get_backend`, facade methods — likely unchanged but verify
  no callbacks accidentally took on layout responsibilities.

**Checkpoint:** `grep gv-active-group` and `grep gv-pane-` return zero
hits. App builds, all unit tests pass.

### Step 7 — tests

- Existing `test_sidebar_tree.py` and `test_gallery_view.py` keep
  working unchanged (they test pure helpers).
- Update `test_gallery.py` callbacks-related tests if they referenced
  pane Outputs.
- Add `test_pages.py` covering: page registration, URL→layout
  resolution, buffer round-trip (fresh URL → empty restore; matching
  URL → buffer restored).
- Update integration tests (`tests/integration/`):
  - Tree leaf click → URL changes to `/?id=...`
  - Tree branch click → URL changes to `/branch/...`
  - Browser back → returns to previous URL → previous view
  - Buffer round-trip: type, navigate, navigate back, verify text

**Checkpoint:** all unit + integration tests pass. CI green.

### Step 8 — docs

- Update `CLAUDE.md`:
  - Replace the "branch-click gallery view" implementation notes
    (id reuse, active-group, pane dispatch — all gone) with the new
    URL-routed model.
  - Bump the requirements table: F30 stays "Done" but its status note
    references URL routing, not pane dispatch.
  - Add a new requirement (F31?) for "shareable branch URLs".
  - Bump test counts.
- Update `README.md`: the "Branch-click gallery view" bullet now
  mentions deep-linkable branch URLs.
- Delete `PAGES_MIGRATION.md`? **No** — keep it as a record of why
  this design was chosen, with a final "Outcome" section appended.

## 5. Public API stability

The constructor `Gallery(backend=..., backends=..., title=..., theme=...,
export_fn=..., extra_controls=..., config_path=..., context=...,
track_packages=..., item_label=..., group_label=..., version_label=...,
item_url_key=..., group_url_key=..., version_url_key=...)` and the
public methods (`run`, `app`, `from_config`, `run_script`, `save_script`,
`list_groups`, `list_versions`, `load_script`, `load_data`,
`load_artifact`, `template_for_group`, `parse_url_state`, `apply_params_to_script`,
`version_diff`, `version_diff_label`, `export_inject_vars`) are all
**unchanged**. Downstream apps (`corpframe-gallery`) re-import and run.

Two soft API points worth thinking about:

- **`extra_controls`.** Today it's injected into the detail layout. After
  migration it stays in `pages/detail.py`. No API change, but if a future
  user wants to inject controls into the gallery page too, that's a new
  parameter (`extra_gallery_controls=...`). Out of scope for this
  migration.
- **`/render` Flask route.** Independent of Pages — stays where it is on
  `app.server`. Verify it still mounts correctly with `use_pages=True`.

## 6. Testing strategy

| Test | What it verifies | Pre-migration | Post-migration |
| --- | --- | --- | --- |
| `test_sidebar_tree.py` | Pure tree helpers | Unchanged | Unchanged |
| `test_gallery_view.py` | Pure card-render helpers | Unchanged | Unchanged |
| `test_backend.py` | Backend protocol | Unchanged | Unchanged |
| `test_config.py` | gallery.json IO | Unchanged | Unchanged |
| `test_params.py` | CONFIGURATOR parsing | Unchanged | Unchanged |
| `test_gallery.py` | Facade methods + headless run | Some IDs change, mostly stable | Update tests that asserted pane Outputs (none today) |
| `test_pages.py` (new) | Page registration, URL→layout, buffer round-trip | — | Add |
| `tests/integration/*` | UI workflows via Selenium | All pass on current model | Re-record any flow that asserted a specific layout id structure; add browser back/forward + URL-share tests |

The two helper test files are the safety net: they cover ~46 tests that
exercise pure functions and never touch the app shell. As long as those
stay green during the move, we know the rendering primitives didn't
break.

## 7. Rollback plan

Each step's checkpoint is a green build. If step N goes wrong:

1. `git stash` or `git restore` the WIP changes.
2. The previous step's checkpoint is the rollback point.
3. If steps 0–4 succeed but step 5 (the buffer) is too gnarly, ship
   without buffer + with the dirty-warning only. Buffer can be added
   later as an enhancement; it's not a blocker for shipping the URL
   routing.
4. If the whole approach fails (e.g. `dash.Pages` interacts badly with
   our `external_stylesheets`/`pages_folder=""` combo), revert to the
   pre-migration commit. The current pane-dispatch model works; we lose
   no functionality by reverting.

The commit history during the migration should be one commit per step,
so rollbacks are surgical.

## 8. Open questions (decide as we go)

- **`extra_stylesheets` and theme.** Confirm `dbc.themes.SLATE` works
  with `use_pages=True` (it should — Pages doesn't touch styling). Spot
  check after step 2.
- **Backwards-compat URL.** Does anyone currently rely on `/?id=X` (no
  `group`/`version`) as a stable URL? Pages keeps `/` working for the
  detail page, so this is fine — but write a regression test.
- **404 page.** Pages auto-renders a default 404 for unknown routes.
  Override with a "branch not found" page that redirects to `/`?
  Defer — out of scope.
- **`_render_tree_node` location.** Today it's in `gallery.py`. Move
  to a shared `pages/_sidebar.py` so both the shell layout and tests
  can import it without the page modules.

