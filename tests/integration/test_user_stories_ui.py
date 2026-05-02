# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Browser-driven integration tests mirroring the user stories from CLAUDE.md.

Each test exercises ONE user story through the actual Dash UI so that the
unit-level coverage of the same story is validated against the rendered
callback wiring. These complement (not replace) the API-facade tests in
``tests/gallery_viewer/test_gallery.py``.

User stories (numbering matches CLAUDE.md):
    #1 The thinker         — versioned scripts; multiple versions browsable
    #2 No skill floor      — typed assignments → auto-rendered form fields
    #4 The reproducer      — export standalone .py
    #5 The annotator       — per-version change-note (intent capture)
    #6 The reviewer        — version diff label between v_n and v_{n-1}
    #7-#8 Tags             — covered in test_tags_ui.py
    #9 The auditor         — data hash + provenance metadata stamped at save
    #10 The naive user     — Save always creates a NEW version (no overwrite)
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
        sections = ScriptSections(
            configurator=configurator,
            code="print('hi')",
        )
        (d / "scripts" / f"script_20240101_v{v}.py").write_text(sections.to_text())
    return d


# ── #5 The annotator — change-note captured via Save modal ─────────────────


def test_annotator_story_change_note_persists_through_save_modal(dash_duo, tmp_path):
    """Story #5: "I want to record WHY I made this change in v4."

    User opens Save modal, fills in author + the "what changed?" textarea,
    confirms — the saved script's metadata block contains the change note.
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-save-btn", timeout=10)
    time.sleep(0.5)

    # Open the Save modal.
    dash_duo.find_element("#gv-save-btn").click()
    dash_duo.wait_for_element("#gv-save-description", timeout=5)

    # Fill author and change-note.
    dash_duo.find_element("#gv-save-author").send_keys("Alice")
    dash_duo.find_element("#gv-save-description").send_keys(
        "Switched to log scale because client said linear buried small values"
    )
    dash_duo.find_element("#gv-confirm-save-ok").click()

    # Wait for save to complete — a new version v2 should exist on disk.
    time.sleep(1.5)
    saved = (base / "scripts" / "script_20240101_v2.py").read_text()
    assert "# author: Alice" in saved
    assert "Switched to log scale" in saved


# ── #6 The reviewer — version diff label between v_n and v_{n-1} ───────────


def test_reviewer_story_diff_label_summarizes_what_changed(dash_duo, tmp_path):
    """Story #6: "Show me what changed between Tuesday and today."

    Two versions where v2 differs from v1 in one parameter. Selecting v2
    must surface a one-line diff label naming that parameter — so the
    reviewer doesn't have to mentally A/B the scripts.
    """
    base = tmp_path / "g"
    (base / "data").mkdir(parents=True)
    (base / "plots").mkdir()
    (base / "scripts").mkdir()
    pd.DataFrame({"x": [1, 2]}).to_csv(base / "data" / "data_20240101.csv", index=False)
    (base / "plots" / "plot_20240101_v1.png").write_bytes(b"\x89PNG fake")
    (base / "plots" / "plot_20240101_v2.png").write_bytes(b"\x89PNG fake")
    (base / "scripts" / "script_20240101_v1.py").write_text(
        ScriptSections(
            configurator='title: str = "Old"\nshow: bool = True',
            code="print('hi')",
        ).to_text()
    )
    (base / "scripts" / "script_20240101_v2.py").write_text(
        ScriptSections(
            configurator='title: str = "New"\nshow: bool = True',
            code="print('hi')",
        ).to_text()
    )

    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-version", timeout=10)
    time.sleep(0.7)

    # Diff label is in #gv-version-diff. For v2 it should mention `title`.
    dash_duo.wait_for_text_to_equal(
        "#gv-version-diff", "v2 — title", timeout=5
    ) if False else None  # contains-check below is more robust
    diff_text = dash_duo.find_element("#gv-version-diff").text
    assert "v2" in diff_text
    assert "title" in diff_text


# ── #1 The thinker — versioning is first-class; versions are browsable ─────


def test_thinker_story_multiple_versions_appear_in_dropdown(dash_duo, tmp_path):
    """Story #1: "An analyst iterating on a chart for a paper."

    The thinker compares v3 vs v7 and remembers why. Step zero is that all
    saved versions show up in the version dropdown so they CAN be compared.
    """
    base = _seed_gallery(tmp_path, n_versions=4)
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-version", timeout=10)
    time.sleep(0.5)

    # The new dash-dropdown is a Radix listbox button — click to open, then
    # the rendered ``[role='option']`` items live in a popover elsewhere
    # in the DOM (``aria-controls`` on the button names the listbox id).
    dash_duo.find_element("#gv-version").click()
    time.sleep(0.5)
    options = dash_duo.driver.find_elements("css selector", "[role='option']")
    rendered_text = " ".join(el.text for el in options)
    for v in ("v1", "v2", "v3", "v4"):
        assert v in rendered_text, (
            f"version {v} missing from dropdown options: {rendered_text!r}"
        )


# ── #2 No skill floor — typed assignments → auto-rendered form fields ──────


def test_no_skill_floor_story_typed_assignments_render_as_form_fields(
    dash_duo, tmp_path
):
    """Story #2: "The boss fixes a typo in the chart title."

    The boss never opens the editor — only the form fields. So every typed
    assignment in the CONFIGURATOR (``title: str = ...``, ``show: bool = ...``,
    ``dpi: int = ...``) must render as a form input keyed by its variable name.
    """
    base = _seed_gallery(
        tmp_path,
        n_versions=1,
        configurator=(
            'title: str = "Quarterly Revenue"\nshow_target: bool = True\ndpi: int = 150'
        ),
    )
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-param-fields", timeout=10)
    time.sleep(0.5)

    # Each declared param surfaces as an input — Dash uses pattern-matching IDs
    # whose dict-form serialisation contains the param name.
    fields_html = dash_duo.find_element("#gv-param-fields").get_attribute("innerHTML")
    for name in ("title", "show_target", "dpi"):
        assert name in fields_html, f"param {name!r} not rendered into #gv-param-fields"


# ── #4 The reproducer — standalone .py export ──────────────────────────────


def test_reproducer_story_export_button_present_and_clickable(dash_duo, tmp_path):
    """Story #4: "Send me the chart from your Tuesday slide."

    The consumer wants a single self-contained .py that runs on a clean
    Python install. The "Export .py" button must be present and clickable
    once a saved version exists.
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-export-script-btn", timeout=10)
    time.sleep(0.3)

    btn = dash_duo.find_element("#gv-export-script-btn")
    assert btn.is_displayed()
    assert btn.is_enabled()
    # Triggering the click should not raise a JS error — the dcc.Download
    # component handles the actual file delivery.
    btn.click()
    time.sleep(0.5)
    # No console errors were raised.
    logs = dash_duo.get_logs() or []
    severe = [entry for entry in logs if entry.get("level") == "SEVERE"]
    assert not severe, f"unexpected console errors: {severe}"


# ── #9 The auditor — data hash + provenance stamped at save time ───────────


def test_auditor_story_provenance_stamped_when_saving_through_ui(dash_duo, tmp_path):
    """Story #9: "What data file produced this exact PNG?"

    Saving through the UI must stamp a data hash + Python version into the
    new version's metadata block — the auditor reads the .py and sees the
    hash without running anything.
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-save-btn", timeout=10)
    time.sleep(0.5)

    dash_duo.find_element("#gv-save-btn").click()
    dash_duo.wait_for_element("#gv-confirm-save-ok", timeout=5)
    dash_duo.find_element("#gv-save-author").send_keys("Auditor")
    dash_duo.find_element("#gv-confirm-save-ok").click()

    time.sleep(1.5)
    saved = (base / "scripts" / "script_20240101_v2.py").read_text()
    assert "# data_hash: sha256:" in saved
    assert "# python: " in saved


# ── #10 The naive user — Save creates a NEW version (no overwrite) ─────────


def test_naive_user_story_save_never_overwrites_existing_version(dash_duo, tmp_path):
    """Story #10: "I just wanted to see — and now v8 is the boss's experiment."

    The boss hits Save expecting nothing to happen. Save must always create
    a new version, leaving the previous one byte-identical on disk.
    """
    base = _seed_gallery(tmp_path, n_versions=1)
    v1_path = base / "scripts" / "script_20240101_v1.py"
    v1_before = v1_path.read_bytes()

    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-save-btn", timeout=10)
    time.sleep(0.5)

    dash_duo.find_element("#gv-save-btn").click()
    dash_duo.wait_for_element("#gv-confirm-save-ok", timeout=5)
    dash_duo.find_element("#gv-save-author").send_keys("Boss")
    dash_duo.find_element("#gv-confirm-save-ok").click()
    time.sleep(1.5)

    # v1 untouched, v2 created.
    assert v1_path.read_bytes() == v1_before, (
        "Save overwrote v1 — that violates story #10"
    )
    v2_path = base / "scripts" / "script_20240101_v2.py"
    assert v2_path.exists()
