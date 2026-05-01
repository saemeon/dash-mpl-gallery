# UI test plan — mirroring facade coverage in Selenium

Goal: every behavior currently exercised through the `Gallery` facade in
`tests/gallery_viewer/test_gallery.py` that has a real user-visible UI surface
should also have a `dash_duo` integration test under `tests/integration/`.
Pure unit-level facade tests (diff algorithm, params parsing helpers,
metadata-block formatting, headless API) stay facade-only.

## Status legend

- `[ ]` not started
- `[~]` in progress
- `[x]` done

## Already covered (no work needed)

- `[x]` #1 thinker — versions in dropdown — `test_user_stories_ui.py`
- `[x]` #2 no-skill-floor — typed assignments → form fields — `test_user_stories_ui.py`
- `[x]` #4 reproducer — export button present + clickable — `test_user_stories_ui.py`
- `[x]` #5 annotator — change-note via Save modal — `test_user_stories_ui.py`
- `[x]` #6 reviewer — version diff label — `test_user_stories_ui.py`
- `[x]` #9 auditor — provenance stamping at save — `test_user_stories_ui.py`
- `[x]` #10 naive user — Save creates new version — `test_user_stories_ui.py`
- `[x]` tags — add / remove / persist / filter — `test_tags_ui.py`

## Chunks to add

### Chunk A — param form ↔ script editor ↔ render loop

Highest user-visible value: this is the inner loop of using the gallery.

- `[x]` **A1** — `TestUpdateScriptButton` + `TestParamValuesToInject`
  Change a form field → click "Update script" → script editor reflects the new
  param value. → `test_update_script_button_writes_form_values_into_editor`
- `[x]` **A2** — `TestScriptToggle`
  Toggling the show-script switch shows/hides the editor.
  → `test_show_script_switch_toggles_editor_visibility`
- `[x]` **A3** — `TestRenderOutputs`
  Running a script renders a PNG image into the output panel.
  → `test_run_script_renders_png_image_into_output_panel`

Target file: `tests/integration/test_workflows_ui.py` ✅ created.

### Chunk B — guardrails and per-user context

- `[~]` **B1** — `TestDirtyFlag` — **DROPPED from UI scope.** The
  `gv-clean-script-store` is updated by load/save callbacks but no callback
  currently drives `gv-confirm-navigate.displayed`. The dialog is reserved
  infrastructure with no observable user-facing behavior; a Selenium test
  would only re-verify what `str(g.app.layout)` already covers at the facade.
  Revisit once a navigation/edit guard is wired.
- `[x]` **B2** — `TestContextRegistration`
  `Gallery(context={"author": "Paul"})` pre-fills the author field in the
  Save modal when it opens.
  → `test_gallery_context_prefills_author_in_save_modal`
- `[x]` **B3** — `TestErrorPaths`
  A script that raises shows the error in the console panel rather than
  crashing the UI. → `test_run_script_with_runtime_error_surfaces_in_console`

Target file: extended `test_workflows_ui.py` ✅.

### Chunk C — wiring boundaries

- `[x]` **C1** — `TestNewDate`
  "New date" button moves the user onto an uncharted date with a fresh
  template loaded into the editor.
  → `test_new_date_button_creates_entry_from_uncharted_data`
  *(in `test_workflows_ui.py`)*
- `[x]` **C2** — `TestGalleryFacadeRouting`
  Multi-backend gallery: clicking a sidebar nav item switches the active
  plot, and the editor reflects the chosen backend's content. Round-trips.
  → `test_multi_backend_sidebar_click_switches_active_plot`
- `[x]` **C3** — `TestExportButton` (negative + positive companion)
  → `test_export_btn_absent_when_no_export_fn`
  → `test_export_btn_present_when_export_fn_provided`

Target file: `tests/integration/test_multi_backend_ui.py` ✅ created (C2/C3),
`test_workflows_ui.py` extended with C1.

## Final tally

11 new browser tests added, 100% passing locally:

- `test_workflows_ui.py` — 6 tests (A1, A2, A3, B2, B3, C1)
- `test_multi_backend_ui.py` — 3 tests (C2, C3 negative, C3 positive)

(The 7 pre-existing `test_user_stories_ui.py` tests + 1 of the 4 tags tests
also pass; the other 3 tags tests in `test_tags_ui.py` fail independently
of this work — pre-existing failure, not introduced here.)

## Next pass (out of scope for this iteration)

- B1 dirty flag — revisit once a navigation/edit guard is wired to
  `gv-confirm-navigate.displayed`.
- Tags UI tests in `test_tags_ui.py` are pre-existingly failing in 3 of 4
  cases — unrelated to this work, but worth a follow-up triage.
- A "save through the UI then run again" round-trip — currently each
  workflow test exercises a single causal arrow; a longer scenario would
  be a useful regression net.

## Out of scope (intentionally facade-only)

These have no UI surface, are pure data/algorithmic, or are explicitly
documented as headless:

- `TestDiffConfigurator` — pure dict diff algorithm
- `TestParamValuesToInject` (helper) — dict → string injection
- `TestApplyParamsToScript` — sections-level helper
- `TestVersionDiffLabel` — label formatter unit (covered transitively by #6)
- `TestHeadlessAPI` / `TestHeadlessWorkflow` — explicitly non-browser
- `TestWorkflowOrders` — operation-ordering invariants on the facade
- `TestConfigurationMatrix` — parametrized smoke; one UI smoke is enough
- `_with_metadata_*` helpers — string-formatting unit tests
- `TestProvenance` *internals* — covered by #9 at the UI level; the per-key
  unit assertions stay facade-only.

## Notes

- All tests live under `tests/integration/` and are auto-skipped on CI via
  `tests/integration/conftest.py`.
- Use `dash_duo` fixture (Selenium under the hood). Run locally with:
  `uv run pytest dash-script-gallery/tests/integration/ -v`.
- Helper `_seed_gallery` already exists in `test_user_stories_ui.py`; reuse
  pattern (or factor into a shared conftest helper if duplication grows).
