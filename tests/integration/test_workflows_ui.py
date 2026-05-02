# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Browser-driven integration tests for the inner-loop workflows.

These mirror the facade tests in ``tests/gallery_viewer/test_gallery.py`` for
behaviors with a real UI surface — see ``UI_TEST_PLAN.md`` for the mapping.

Chunk A — param form ↔ script editor ↔ render loop:
    A1 — Update Script button propagates form values into the script editor
    A2 — Show-script switch toggles editor visibility
    A3 — Running a script renders a PNG image into the output panel

Chunk B — guardrails and per-user context:
    B2 — Gallery(context={"author": ...}) pre-fills Save modal author field
    B3 — Script with a runtime error surfaces the error in the console panel

Chunk C (subset):
    C1 — "New date" button creates a fresh entry from the latest template
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from gallery_viewer import FileSystemBackend, ScriptSections
from gallery_viewer.gallery import Gallery


def _seed_gallery(
    root: Path,
    *,
    n_versions: int = 1,
    configurator: str = 'title: str = "Demo"\nshow: bool = True',
    code: str = "print('hi')",
) -> Path:
    """Minimal gallery dir at *root* with one date and N saved versions."""
    d = root / "g"
    (d / "data").mkdir(parents=True)
    (d / "plots").mkdir()
    (d / "scripts").mkdir()
    pd.DataFrame({"x": [1, 2], "y": [3, 4]}).to_csv(
        d / "data" / "data_20240101.csv", index=False
    )
    for v in range(1, n_versions + 1):
        (d / "plots" / f"plot_20240101_v{v}.png").write_bytes(b"\x89PNG fake")
        sections = ScriptSections(configurator=configurator, code=code)
        (d / "scripts" / f"script_20240101_v{v}.py").write_text(sections.to_text())
    return d


# A real matplotlib script the run_btn callback can execute end-to-end. Writes
# a PNG to OUTPUT_PATH so the run pipeline produces image bytes the panel can
# render. Kept tiny so the test stays fast.
_REAL_MPL_SCRIPT = """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(2, 2))
ax.plot([0, 1, 2], [0, 1, 4])
ax.set_title(title)
fig.savefig(OUTPUT_PATH, format="png")
""".lstrip()


# ── A1: Update Script button propagates form values into editor ───────────


def test_update_script_button_writes_form_values_into_editor(dash_duo, tmp_path):
    """Story: form-only user tweaks `title`, hits Update Script, and the
    editor (which they can later inspect / save) reflects the new value.

    Mirrors facade tests `TestUpdateScriptButton` + `TestParamValuesToInject`.
    """
    base = _seed_gallery(
        tmp_path,
        n_versions=1,
        configurator='title: str = "Old"\nshow: bool = True',
    )
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-update-script-btn", timeout=10)
    time.sleep(0.7)

    # Locate the `title` form field via Dash pattern-matching ID. The ID
    # serialises as a JSON string, so a CSS `[id*=...]` substring match is
    # the simplest reliable selector.
    title_input = dash_duo.find_element('input[id*=\'"name":"title"\']')
    title_input.clear()
    title_input.send_keys("Brand New Title")

    # Reveal the editor so we can read its value.
    dash_duo.find_element("#gv-show-script").click()
    time.sleep(0.3)

    dash_duo.find_element("#gv-update-script-btn").click()
    time.sleep(0.7)

    # Editor is either DashAceEditor or dcc.Textarea. Both render as a child
    # element under #gv-editor-wrapper; for assertion we read the wrapper's
    # text content which captures the editor value either way.
    wrapper = dash_duo.find_element("#gv-editor-wrapper")
    editor_text = wrapper.text or wrapper.get_attribute("innerHTML")
    assert "Brand New Title" in editor_text, (
        f"updated title not visible in editor wrapper. text={editor_text!r}"
    )


# ── A2: Show-script switch toggles editor visibility ──────────────────────


def test_show_script_switch_toggles_editor_visibility(dash_duo, tmp_path):
    """Story: by default the editor is hidden (no skill floor); flipping the
    switch reveals it for power users.

    Mirrors facade test `TestScriptToggle`.
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-show-script", timeout=10)
    time.sleep(0.5)

    wrapper = dash_duo.find_element("#gv-editor-wrapper")
    # Initially hidden.
    assert "none" in (wrapper.get_attribute("style") or ""), (
        f"editor should start hidden, got style={wrapper.get_attribute('style')!r}"
    )

    dash_duo.find_element("#gv-show-script").click()
    time.sleep(0.4)

    wrapper = dash_duo.find_element("#gv-editor-wrapper")
    style_after = wrapper.get_attribute("style") or ""
    assert "block" in style_after, (
        f"editor should be visible after toggle, got style={style_after!r}"
    )

    # Toggle off again — round-trip.
    dash_duo.find_element("#gv-show-script").click()
    time.sleep(0.4)
    wrapper = dash_duo.find_element("#gv-editor-wrapper")
    assert "none" in (wrapper.get_attribute("style") or ""), (
        "editor should hide again after second toggle"
    )


# ── A3: Run renders PNG into output panel ─────────────────────────────────


def test_run_script_renders_png_image_into_output_panel(dash_duo, tmp_path):
    """Story: hitting Run executes the script and shows the resulting plot
    in the output panel — the inner feedback loop the analyst lives in.

    Mirrors facade test `TestRenderOutputs` (PNG branch).
    """
    base = _seed_gallery(
        tmp_path,
        n_versions=1,
        configurator='title: str = "Demo"',
        code=_REAL_MPL_SCRIPT,
    )
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-run-btn", timeout=10)
    time.sleep(0.7)

    dash_duo.find_element("#gv-run-btn").click()

    # The run callback writes a base64 data-URL <img> into #gv-output-panel.
    # Wait for it to appear (matplotlib + savefig can take a moment).
    deadline = time.time() + 15
    img_src = ""
    while time.time() < deadline:
        try:
            img = dash_duo.find_element("#gv-output-panel img")
            img_src = img.get_attribute("src") or ""
            if img_src.startswith("data:image/png;base64,"):
                break
        except Exception:
            pass
        time.sleep(0.3)

    assert img_src.startswith("data:image/png;base64,"), (
        f"output panel did not render a base64 PNG image. last src={img_src!r}"
    )
    # Console should be free of "ERROR" markers on success.
    console_text = dash_duo.find_element("#gv-console").text
    assert "--- ERROR ---" not in console_text, (
        f"run reported an error: {console_text!r}"
    )


# ── B2: Gallery context pre-fills Save modal author field ─────────────────


def test_gallery_context_prefills_author_in_save_modal(dash_duo, tmp_path):
    """Story (#C): a deployment registers the current user once via
    ``Gallery(context={"author": "Paul"})``. Each time Paul opens the Save
    modal, his name is already in the author field.

    Mirrors facade test `TestContextRegistration` (UI-visible portion).
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    gallery = Gallery(
        backend=FileSystemBackend(base),
        context={"author": "Paul"},
    )
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-save-btn", timeout=10)
    time.sleep(0.5)

    # Open the modal — the prefill callback fires on `is_open` flipping true.
    dash_duo.find_element("#gv-save-btn").click()
    dash_duo.wait_for_element("#gv-save-author", timeout=5)
    time.sleep(0.5)  # let the prefill callback round-trip

    author_value = dash_duo.find_element("#gv-save-author").get_attribute("value")
    assert author_value == "Paul", (
        f"expected author field pre-filled with 'Paul', got {author_value!r}"
    )


# ── B3: Script with runtime error surfaces error in console ───────────────


_CRASHING_SCRIPT = "raise ValueError('intentional test failure: do not panic')\n"


def test_run_script_with_runtime_error_surfaces_in_console(dash_duo, tmp_path):
    """Story (#error path): a user types a broken script and hits Run. The
    UI must surface the error inline rather than crashing or going silent.

    Mirrors facade test `TestErrorPaths.test_run_script_raising_exception_*`.
    """
    base = _seed_gallery(
        tmp_path,
        n_versions=1,
        configurator='title: str = "Demo"',
        code=_CRASHING_SCRIPT,
    )
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-run-btn", timeout=10)
    time.sleep(0.7)

    dash_duo.find_element("#gv-run-btn").click()

    # Console populates asynchronously — poll until we see the ERROR marker
    # the run callback prepends to result.error.
    deadline = time.time() + 15
    console_text = ""
    while time.time() < deadline:
        console_text = dash_duo.find_element("#gv-console").text
        if "--- ERROR ---" in console_text:
            break
        time.sleep(0.3)

    assert "--- ERROR ---" in console_text, (
        f"console missing ERROR marker. text={console_text!r}"
    )
    assert "ValueError" in console_text or "intentional test failure" in console_text, (
        f"console missing actual error text. text={console_text!r}"
    )


# ── C1: "New date" button creates an entry from the latest template ───────


def test_new_date_button_creates_entry_from_uncharted_data(dash_duo, tmp_path):
    """Story: a fresh CSV (``data_20240202.csv``) lands in the data folder
    overnight. The user clicks "New date" and a v1-from-template entry for
    that date is added to the dropdown — no manual file shuffling needed.

    Mirrors facade test `TestNewDate.test_find_uncharted_dates` and
    `Gallery.template_for_date` end-to-end through the UI.
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    # Add an uncharted data file — date present in /data but absent in /scripts.
    pd.DataFrame({"x": [9, 10], "y": [11, 12]}).to_csv(
        base / "data" / "data_20240202.csv", index=False
    )

    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-new-date-btn", timeout=10)
    time.sleep(0.7)

    dash_duo.find_element("#gv-new-date-btn").click()
    time.sleep(1.2)  # callback chain: new_date → date.value → version reload

    # Contract: console announces the new date, the date selector moves to
    # it, and the editor is populated with a fresh template that references
    # the new date. (The "(new)" version label is a UX hint that gets
    # overwritten by the date-change cascade — relying on it would make the
    # test brittle to harmless callback reordering.)
    console_text = dash_duo.find_element("#gv-console").text
    assert "20240202" in console_text, (
        f"console should announce new date. text={console_text!r}"
    )

    date_text = dash_duo.find_element("#gv-date").text
    assert "20240202" in date_text, (
        f"date selector should show the new date. text={date_text!r}"
    )

    # Reveal the editor to verify the template was loaded.
    dash_duo.find_element("#gv-show-script").click()
    time.sleep(0.4)
    wrapper = dash_duo.find_element("#gv-editor-wrapper")
    editor_text = wrapper.text or wrapper.get_attribute("innerHTML") or ""
    assert "20240202" in editor_text, (
        "editor should contain a template referencing the new date. "
        f"snippet={editor_text[:200]!r}"
    )
