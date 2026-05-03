# dash-script-gallery

A Dash dashboard for **versioned, scripted charts and scripts in general** —
built so that the chart, its source script, its data, and its history all live
as plain files that any human or pipeline can inspect.

The architecture is framework-neutral: nothing in `Gallery`, `StorageBackend`,
`ScriptSections`, the versioning model, or the output-rendering layer assumes
a particular plotting library. The package ships an **mpl starter template**
(opinionated default that imports matplotlib), but the starter is overridable
via `FileSystemBackend(starter_template_fn=...)` — Plotly, Altair, or any
script that emits PNG / JSON / CSV works today.

This file documents the *identity* of the tool, the *user stories* that drive
its design, and the *near-term roadmap*. For workspace-level architecture
(packages, dependencies, conventions), see the top-level `CLAUDE.md`.

---

## Identity — three principles

The package was designed around three principles, each implied by a primary
user story:

1. **The tool is for thinking, not just rendering.**
   *Story: an analyst iterating on a chart for a paper.*
   The answer is rarely v1. The user needs to compare v3 vs v7 and remember
   why. Versioning is first-class, diffs are visible, history is browsable.

2. **The tool has no skill floor.**
   *Story: the boss fixes a typo in the chart title.*
   Anyone who can read `title = "Foo"` is enabled. No IDE setup, no
   environment, no pipeline. The form fields lift typed assignments out of
   the script for non-coders; the script editor is there for power users.

3. **The tool floats above plain files.**
   *Story: someone tar's the directory and emails it.*
   No DB, no proprietary format, no "export to share." The plot, script, and
   data are all on disk in obvious filenames. The Gallery is *orchestration
   plus standardisation* over a directory tree, not a wrapper around state
   that lives somewhere else.

These principles are the test for any new feature: does it respect the
versioning model, does it stay accessible, does it keep the filesystem
self-describing?

---

## User stories

The three above plus the additional ones that surfaced during design review:

### 4. **The reproducer** — "Send me the chart from your Tuesday slide"
The consumer wants to see what the chart was made from. The standalone export
(`export_standalone` callback + `export_inject_vars` facade) is the answer:
one self-contained `.py` file that runs on a clean Python install and writes
the same PNG. **Implication:** every chart should be trivially reproducible
from a single file.

### 5. **The annotator** — "I want to record WHY I made this change in v4"
Implemented: save captures both **who** and **why**. The Save modal stores a
per-version change note (commit-style rationale) alongside author metadata,
so analytical intent is preserved directly with the script version.

### 6. **The reviewer** — "Show me what changed between Tuesday and today"
Implemented: `version_diff` covers parameter-level changes and is now paired
with persisted change notes, so reviewers see both the config delta and the
author's intent. Side-by-side perceptual image diff remains a possible future
enhancement.

### 7. **The publication-time freezer** — "Don't let v7 ever change"
Once a chart ships in a paper, every future operation must be non-destructive.
Versioning helps, but there's no "this is locked" marker. A frozen flag, or
just a convention (`script_..._v7_FINAL.py`) the UI respects.

### 8. **The new collaborator** — "I just got added, what's going on?"
A new analyst lands in the directory. The plot dir has 47 PNGs and the README
is empty. They don't know which is current, which was rejected, which was a
draft. Wants to grow into a *project state* layer (a `status.md` per date, or
a "current" pointer).

### 9. **The auditor / stickler** — "Show me the data lineage"
Implemented: save-time provenance stamping captures audit metadata in script
frontmatter, including data linkage metadata (hash-based lineage) so a saved
version is self-describing for regulated review.

### 10. **The naive user who shouldn't break things** — "I just wanted to see"
The boss again, but more dangerous. They edit, hit Save, and now v8 is "boss's
experiment" instead of "the canonical chart." Want a sandbox/draft mode, or
auto-save-as-branch behavior.

### 11. **The CI / pipeline integrator** — "Run this chart from a Makefile"
The standalone export gives a runnable script. What's missing is a stable
**interface contract**: `BASE_DIR/data/...` in, `OUTPUT_PATH` out. If a user
rewires those in their script, downstream pipelines break silently.
`export_inject_vars` is the start of this contract.

### 12. **The forgetful self of three months from now** — "What is this?"
You open a folder you haven't touched since January. Configurator says
`threshold: float = 0.42`. Why 0.42? The author comment helps a little. The
methodology lives outside the gallery. Want a `notes/` companion or a
free-form "purpose" field.

---

## Cross-cutting patterns

What the stories together imply about *missing dimensions*:

- **Provenance** (data hash, brand version, library versions) — for #9, #11
- **Intent capture** (why this version exists) — for #5, #6, #8, #12
- **Diff visualization** (image diff, not just config diff) — for #6
- **State markers** (final / draft / locked) — for #7, #10, generalized to **tags** (E)

The cheapest, highest-leverage of these is **intent capture**. One free-form
`description` field per version unlocks #5, #6, #8, and #12 with a single
feature.

---

## Feature status

### Implemented recently (formerly roadmap A/B/C/E)
- **A. Intent capture:** Save modal includes per-version change note and stores
  rationale metadata with the script version.
- **B. Provenance stamping:** save-time frontmatter includes provenance fields
  (including data lineage hash and runtime/package context).
- **C. Current-user registration:** `Gallery.user` can seed author defaults so
  save flows auto-fill current user identity.
- **E. Tags:** versions support free-form tags (`published`, `final`, `draft`,
  `wip`, `frozen`, etc.) in frontmatter and UI filtering workflows.
- **F. Branch-click gallery view:** clicking a tree group opens a card grid
  in the right panel — direct leaves render as cards (name + description +
  glyph), sub-groups render as drillable folder cards (name + recursive
  leaf count). Clicking a leaf returns to the existing script detail view.
  Addresses story #8 ("the new collaborator — what's going on?") by making
  the structure of a populated directory legible without forcing the visitor
  to scan the sidebar one item at a time. Real composite thumbnails
  (mosaic of latest leaf PNGs) are deliberately deferred — v1 uses a glyph.

  Three implementation choices worth knowing if you extend this:

  1. **Layout is sidebar (tree) + main panel (panes).** The main panel hosts
     siblings ``gv-pane-detail`` and ``gv-pane-gallery``; only one is
     visible at a time. The detail pane wraps the existing editor + preview
     row (now ``width=5`` / ``width=7`` inside a nested grid that fills
     the ``width=10`` main col). The gallery pane is full-width within main
     and is filled by ``render_gallery_panel``. **Adding a new pane** =
     add a Div with ``id="gv-pane-X"``, add an Output to ``show_pane``,
     write a content callback that targets ``gv-pane-X``. The tree never
     references pane ids.
  2. **Card ids reuse the tree ids.** Leaf cards use
     ``{"type": "gv-nav-item", "index": <name>}`` and subfolder cards use
     ``{"type": "gv-tree-group", "index": <path>}`` — identical to the
     sidebar entries. The existing pattern-matching handlers (``nav_click``
     and ``toggle_group``) catch card clicks for free, so adding the gallery
     required no new click callbacks. If you change card ids, you also have
     to wire up parallel callbacks.
  3. **``gv-active-group`` is the single source of truth for pane visibility.**
     ``show_pane`` reads it and toggles the ``style`` of every pane Div
     (display: none vs {}). Empty string = detail pane visible; non-empty
     = gallery pane visible. Each pane owns its own content callbacks and
     never writes outside its own Div, so there is no cross-pane racing.
     ``toggle_group`` writes the path on group click; ``nav_click`` clears
     it on leaf click. The detail pane's components stay mounted (just
     hidden) so its many callbacks keep working without pane-aware guards.

### Still open / documentation follow-up
- **D. Generic framing:** package is framework-neutral in architecture, but docs
  should continue to emphasize that this is not matplotlib-only.

---

## Out of scope (deliberately)

- **Bulk operations** (CLI runners, rerun-all-charts after a brand update,
  matrix re-execution). Tempting, but not the current pain point.
- **Image diff / perceptual diff badges** (#6). Useful, but second-priority
  to intent capture, which addresses the underlying need ("what changed?")
  more cheaply.
- **Multi-user session model.** See #C nuance above.

---

## Architectural notes

### Facade pattern
`Gallery` exposes a thin facade over `StorageBackend` for every operation
the UI needs (`list_groups`, `load_script`, `save_script`, `run_script`,
`version_diff`, `export_inject_vars`, `apply_params_to_script`,
`version_diff_label`, …). Callbacks are kept thin: parse Dash inputs,
delegate to a facade method, format the result for Dash outputs.

**Rule of thumb:** if a callback grows more than ~5 lines of inline logic,
extract that logic into a facade method. The facade is unit-testable; the
callback is not. The current test suite exists *because* the facade exists.

This count has grown substantially; keep the testing summary below current.

### Backends
`StorageBackend` is the abstraction; `FileSystemBackend` is the concrete
flat-file implementation. The facade and the UI never assume filesystem —
they go through the backend. A future S3 / cloud backend would slot in here
without UI changes.

### Tests
- `tests/gallery_viewer/` — unit tests, **320 passing** (includes 21 for the
  branch-click gallery view in `test_gallery_view.py`)
- `tests/integration/` — UI integration tests, **20 total**
  - `test_workflows_ui.py` — 6 tests
  - `test_multi_backend_ui.py` — 3 tests
  - `test_user_stories_ui.py` — 7 tests
  - `test_tags_ui.py` — 4 tests
- `tests/integration/UI_TEST_PLAN.md` tracks mirrored workflows and known gaps.
- `tests/gallery_viewer/conftest.py` — shared fixtures (`make_dir`,
  `multi_backend_gallery`, `gallery_with_chain`, `empty_gallery`)
- Coverage strategy: aim for *thorough scenario coverage* on the facade;
  accept lower line coverage on callbacks (they're UI glue and self-checking
  visually). The right test investment is parametrized matrices over
  configurations × workflows × orderings, not exhaustive callback tests.

## Requirements (merged snapshot)

This section is the canonical high-level requirements view for the project.

### Functional requirements

| # | Requirement | Status |
|---|---|---|
| F1 | Browse multiple named plots in a sidebar | Done |
| F2 | Select group and version for each item | Done |
| F3 | View plot images and data tables | Done |
| F4 | Edit the script in a syntax-highlighted editor | Done (dash-ace) |
| F5 | Detect typed parameters and render form fields | Done |
| F6 | Run the script and show live preview | Done |
| F7 | Save as a new version (with confirmation + author) | Done |
| F8 | Refresh groups/versions from disk | Done |
| F9 | Search/filter plots by name | Done |
| F10 | Add new plots from the dashboard | Done (with gallery.json) |
| F11 | Pluggable storage backend | Done |
| F12 | JSON config file (read + write) | Done |
| F13 | Auto-discover plots from directory structure | Done |
| F14 | Optional export button (post-process with corpframe) | Done |
| F15 | Multi-output support (matplotlib, Plotly, DataFrames) | Done |
| F16 | Version diff labels (parameter changes between versions) | Done |
| F17 | Read-only mode (hide script editor) | Done |
| F18 | Export standalone .py script | Done |
| F19 | Author metadata on save | Done |
| F20 | New Group button (detect uncharted data groups) | Done |
| F21 | Copy from latest version when creating new group | Done |
| F22 | RUN does not modify editor (injection at execution time) | Done |
| F23 | Save uses selected group, not today's date | Done |
| F24 | Save includes per-version change note (intent capture) | Done |
| F25 | Save stamps provenance metadata (lineage/runtime context) | Done |
| F26 | Version tags (add/remove/filter) | Done |
| F27 | Save modal context pre-fill (author/group/version context) | Done |
| F28 | URL deep-linking: selectors + configurator overrides via query string | Done |
| F29 | `/render` endpoint: cached PNG bytes for `?id=&group=&version=` | Done |
| F30 | Branch-click gallery view (cards for direct leaves + drillable subfolders) | Done |

### Non-functional requirements

| # | Requirement | Status |
|---|---|---|
| N1 | No corporate-design dependency (generic) | Done |
| N2 | Works without dash-ace (falls back to textarea) | Done |
| N3 | Scripts execute in isolated subprocesses (60s timeout) | Done |
| N4 | Config file writes are atomic (temp + rename) | Done |
| N5 | Backwards-compatible with old 3-section scripts (LOAD/PLOT/SAVE) | Done |
| N6 | Plotly is optional (works without it installed) | Done |

### Backlog / future

| # | Item | Status |
|---|---|---|
| B1 | Two-way binding: editing param fields auto-updates script AND vice versa | Backlog |
| B2 | Delete plot / delete version from the dashboard | Backlog |
| B3 | Authentication / access control | Backlog |
| B4 | Git-backed storage backend | Backlog |
| B5 | Scheduled script execution (cron-like) | Backlog |
| B6 | Thumbnail previews in sidebar | Backlog |
| B7 | Dirty-flag navigation warning (clientside JS + dialog flow) | Partial |
| B8 | Live-render endpoint: `/render` runs the script with overridden params (vs current cached-only behaviour). Needs allowlist of overridable params, rate limiting, and an auth story — it's a public script-execution surface. Subprocess + 60s timeout (N3) makes it costly. Worth doing only when there's a concrete consumer. | Backlog |

## URL deep-linking & vocabulary — design notes (revisit candidates)

Implemented as F28/F29. The model has three axes — **item × group × version**
— exposed via configurable URL keys (`item_url_key` / `group_url_key` /
`version_url_key`, defaults `id` / `group` / `version`) and configurable UI
labels (`item_label` / `group_label` / `version_label`, defaults
`Item` / `Group` / `Version`). Override per-gallery for domain-friendly
vocabulary, e.g. `Gallery(item_label="Plot", group_label="Date")` recovers
the previous chart-flavoured UI.

Choices worth revisiting if the URL story expands:

1. **`script_<name>` prefix for configurator overrides.** Exists to
   disambiguate selector keys from configurator params with the same name
   (e.g. a script with `group: str = "..."`). Alternative: a reserved-word
   convention (drop the prefix, document that scripts cannot use `id`/
   `group`/`version` as param names). Cheap to change later — only
   `parse_url_state` cares about the syntax.

2. **Param overrides applied at render time, not via a separate callback.**
   The `load_version` callback reads `gv-url-overrides` as `State` and bakes
   override values into field defaults inside `_build_param_fields`. The
   alternative — a second callback using pattern-matching IDs to write into
   already-rendered `gv-param` fields — would be more decoupled but adds a
   round-trip and another callback to reason about. Switch if URL state needs
   to update fields *after* initial load (e.g. user changes `?script_dpi=...`
   without reselecting the version).

3. **Internal Dash IDs stay date-flavoured (`gv-date`, `gv-plot-select`).**
   Renamed labels but not internal component IDs — they're an internal
   contract, not user-facing. Renaming would mean touching every callback for
   zero user benefit. Worth it only if the storage backend interface
   (`list_dates`, `load_artifact`, `_get_backend(plot_name)`) is also
   renamed in a coordinated refactor.

4. **Storage backend interface keeps date/version vocabulary.** `list_dates`,
   `load_script(date, version)`, `plot_{date}_v{N}.png` filenames — all kept
   for now. A generic backend (`list_groups`, `{group}_v{N}.<ext>` filenames)
   would let project-flavoured galleries have project-flavoured directories
   too, but it's a breaking change for every existing deployment. Evaluate
   when a real non-date use case appears.

5. **Inject-vars contract uses `date`/`version`.** User scripts read
   `inject["date"]` / `inject["version"]`; renaming silently breaks every
   existing script. Treat as part of the public API; don't change without
   a migration path.

6. **2-axis variant (collapse group into id).** Discussed and deferred. The
   3-axis split is load-bearing for auto-versioning, `version_diff`,
   `template_for_date`, and the "new data arrived" workflow (F20) — all
   well-defined only when versions share inputs within a group. A
   `group_axis=False` opt-in (hide the group dropdown, default group to a
   constant) could ship later for one-off-script galleries. Don't collapse
   in the storage layer — too much workflow lives on the split.
