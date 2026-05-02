# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Browser-driven integration tests for the tag feature.

These exercise the actual Dash callback wiring — pieces that the unit tests
cannot reach because they depend on the rendered DOM and event dispatch:

  - "Edit" button opens the tag modal (toggle_edit_tags_modal callback)
  - Typing + clicking "+" adds a tag (manage_tags callback)
  - Adding a tag updates BOTH the modal and the main gv-tags-row badge list
    AND the gv-tag-filter dropdown options (tag-sync regression test)
  - Selecting a tag in the filter narrows the version dropdown
    (filter_versions_by_tag callback)
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from gallery_viewer import FileSystemBackend, ScriptSections
from gallery_viewer.gallery import Gallery


def _seed_gallery(root: Path, n_versions: int = 3) -> Path:
    """Create a minimal gallery directory at *root* with one date and N versions."""
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
            configurator=f"version: int = {v}",
            code=f"print({v})",
        )
        (d / "scripts" / f"script_20240101_v{v}.py").write_text(sections.to_text())
    return d


def _select_dropdown_option(
    dash_duo, dropdown_id: str, option_text: str, timeout: float = 5.0
):
    """Select *option_text* from a Dash dropdown rendered as a listbox popover."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        dash_duo.find_element(dropdown_id).click()
        time.sleep(0.2)
        options = dash_duo.driver.find_elements(By.CSS_SELECTOR, "[role='option']")
        for option in options:
            if option.text.strip() == option_text:
                option.click()
                return
        dash_duo.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.1)
    raise AssertionError(f"option {option_text!r} not found in {dropdown_id}")


# ── 1. Adding a tag updates all three sinks (regression: tag sync) ──────────


def test_add_tag_via_modal_updates_main_row_and_filter(dash_duo, tmp_path):
    """Story #7 — add `published` via the Edit modal; the badge appears in
    the main tags row AND the filter dropdown gains the option.

    Regression: previously, only the modal updated; the main gv-tags-row
    and gv-tag-filter stayed stale until a version-change re-fired the
    update_tags_row callback.
    """
    base = _seed_gallery(tmp_path)
    gallery = Gallery(backend=FileSystemBackend(base))
    dash_duo.start_server(gallery.app)

    # Wait for initial render — version dropdown populated.
    dash_duo.wait_for_element("#gv-version", timeout=10)
    time.sleep(0.5)  # allow date/version stores to propagate

    # Open Edit Tags modal.
    dash_duo.find_element("#gv-edit-tags-btn").click()
    dash_duo.wait_for_element("#gv-new-tag-input", timeout=5)

    # Type a tag and click +.
    inp = dash_duo.find_element("#gv-new-tag-input")
    inp.send_keys("published")
    dash_duo.find_element("#gv-add-tag-btn").click()

    # Tag must appear in BOTH the modal's current-tags list AND the main row.
    dash_duo.wait_for_contains_text("#gv-edit-tags-current", "published", timeout=5)
    dash_duo.wait_for_contains_text("#gv-tags-row", "published", timeout=5)


# ── 2. Tag persists across version selection ────────────────────────────────


def test_tag_persists_when_switching_versions_and_back(dash_duo, tmp_path):
    """A tag added to v1 is still shown when the user navigates v1 → v2 → v1.

    Catches regressions where add_tag mutates only the in-memory ScriptSections
    and not the file on disk.
    """
    base = _seed_gallery(tmp_path, n_versions=3)
    gallery = Gallery(backend=FileSystemBackend(base))
    # Pre-tag v1 directly (no UI step needed for this assertion).
    gallery.add_tag(None, "20240101", "1", "frozen")
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-version", timeout=10)
    time.sleep(0.5)

    # Pick v1 explicitly (initial selection defaults to the latest version).
    _select_dropdown_option(dash_duo, "#gv-version", "v1")
    dash_duo.wait_for_contains_text("#gv-tags-row", "frozen", timeout=5)

    # Switching away and back must keep the persisted tag.
    _select_dropdown_option(dash_duo, "#gv-version", "v2")
    _select_dropdown_option(dash_duo, "#gv-version", "v1")
    dash_duo.wait_for_contains_text("#gv-tags-row", "frozen", timeout=5)


# ── 3. Filter dropdown narrows version list to versions carrying the tag ────


def test_filter_dropdown_restricts_versions_to_tagged_ones(dash_duo, tmp_path):
    """Story #8 — selecting `published` in the filter chip leaves only v2 in
    the version dropdown when only v2 is published.
    """
    base = _seed_gallery(tmp_path, n_versions=3)
    gallery = Gallery(backend=FileSystemBackend(base))
    gallery.add_tag(None, "20240101", "2", "published")
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-tag-filter", timeout=10)
    time.sleep(0.5)

    # Pick `published` from the tag filter dropdown.
    _select_dropdown_option(dash_duo, "#gv-tag-filter", "published")

    # Version dropdown should now only contain v2.
    time.sleep(0.5)  # let the callback chain settle
    version_dd = dash_duo.find_element("#gv-version")
    # The displayed value should be "v2".
    assert "v2" in version_dd.text


# ── 4. Removing a tag clears it from the main row ───────────────────────────


def test_remove_tag_via_modal_clears_main_row(dash_duo, tmp_path):
    """Click × on a tag in the modal → tag disappears from main gv-tags-row."""
    base = _seed_gallery(tmp_path)
    gallery = Gallery(backend=FileSystemBackend(base))
    gallery.add_tag(None, "20240101", "1", "draft")
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-version", timeout=10)
    time.sleep(0.5)

    # Pick v1 explicitly (initial selection defaults to the latest version).
    _select_dropdown_option(dash_duo, "#gv-version", "v1")

    # Sanity: tag is rendered in the main row.
    dash_duo.wait_for_contains_text("#gv-tags-row", "draft", timeout=5)

    # Open modal and click the × on the `draft` badge.
    dash_duo.find_element("#gv-edit-tags-btn").click()
    dash_duo.wait_for_element("#gv-edit-tags-current", timeout=5)

    # The remove span uses pattern-matching id {"type": "gv-tag-remove", "index": "draft"}.
    # Find it via XPath text-match — robust to dash's id serialization.
    remove_span = dash_duo.driver.find_element(
        By.XPATH, "//*[@id='gv-edit-tags-current']//span[contains(text(), '×')]"
    )
    remove_span.click()

    # Main row no longer contains `draft`.
    time.sleep(0.5)
    main_row = dash_duo.find_element("#gv-tags-row")
    assert "draft" not in main_row.text
