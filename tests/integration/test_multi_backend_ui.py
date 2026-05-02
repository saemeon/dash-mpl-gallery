# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Browser-driven integration tests for multi-backend wiring + opt-in features.

Mirrors the facade-level coverage in:
    - tests/gallery_viewer/test_gallery.py::TestGalleryFacadeRouting
    - tests/gallery_viewer/test_gallery.py::TestExportButton

Chunk C (subset):
    C2 — Multi-backend gallery: clicking a sidebar nav item switches the
         active plot, and dates / script content reflect the chosen backend.
    C3 — A Gallery built without an ``export_fn`` does not render the
         per-plot export button (only the standalone-script export remains).
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from selenium.common.exceptions import NoSuchElementException

from gallery_viewer import FileSystemBackend, ScriptSections
from gallery_viewer.gallery import Gallery


def _make_gallery_dir(
    root: Path, name: str, *, dates_versions: dict[str, int] | None = None
) -> Path:
    """Build a minimal valid gallery dir under ``root/name`` and return it.

    Mirrors the helper of the same name in ``tests/gallery_viewer/test_gallery.py``.
    Each script's configurator embeds the backend name so the UI test can
    distinguish which backend the editor is currently showing.
    """
    if dates_versions is None:
        dates_versions = {"20240101": 1}
    d = root / name
    d.mkdir()
    (d / "data").mkdir()
    (d / "plots").mkdir()
    (d / "scripts").mkdir()
    for date, n_versions in dates_versions.items():
        pd.DataFrame({"x": [1], "y": [2]}).to_csv(
            d / "data" / f"data_{date}.csv", index=False
        )
        for v in range(1, n_versions + 1):
            sections = ScriptSections(
                configurator=f'name: str = "{name}"\nversion: int = {v}',
                code=f"print({name!r}, {v})",
            )
            (d / "scripts" / f"script_{date}_v{v}.py").write_text(sections.to_text())
    return d


# ── C2: Multi-backend routing — sidebar click switches active backend ─────


def test_multi_backend_sidebar_click_switches_active_plot(dash_duo, tmp_path):
    """Story (#facade-routing): a deployment hosts two distinct chart
    "plots" via separate backends. Clicking one in the sidebar must update
    the editor / param fields to that backend's content.

    Mirrors `TestGalleryFacadeRouting.test_load_script_routes_per_plot` end
    to end through the UI.
    """
    dir_alpha = _make_gallery_dir(tmp_path, "alpha")
    dir_beta = _make_gallery_dir(tmp_path, "beta")
    gallery = Gallery(
        backends={
            "alpha": FileSystemBackend(dir_alpha),
            "beta": FileSystemBackend(dir_beta),
        }
    )
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-gallery-sidebar", timeout=10)
    time.sleep(0.7)

    sidebar_html = dash_duo.find_element("#gv-gallery-sidebar").get_attribute(
        "innerHTML"
    )
    assert "alpha" in sidebar_html, "sidebar should list backend 'alpha'"
    assert "beta" in sidebar_html, "sidebar should list backend 'beta'"

    # Reveal the editor — needed to read which backend's script is active.
    dash_duo.find_element("#gv-show-script").click()
    time.sleep(0.4)

    # Click the "beta" nav item. The pattern-matching ID is
    # {"type": "gv-nav-item", "index": "beta"} — find via CSS substring.
    beta_nav = dash_duo.find_element('[id*=\'"index":"beta"\']')
    beta_nav.click()
    time.sleep(1.0)  # nav_click → date opts → version reload → script load

    wrapper_html = (
        dash_duo.find_element("#gv-editor-wrapper").get_attribute("innerHTML") or ""
    )
    assert "beta" in wrapper_html, (
        "editor should contain beta's configurator after clicking beta. "
        f"snippet={wrapper_html[:200]!r}"
    )

    # Now click alpha — round-trip switch confirms routing isn't sticky.
    alpha_nav = dash_duo.find_element('[id*=\'"index":"alpha"\']')
    alpha_nav.click()
    time.sleep(1.0)

    wrapper_html = (
        dash_duo.find_element("#gv-editor-wrapper").get_attribute("innerHTML") or ""
    )
    assert "alpha" in wrapper_html, (
        "editor should contain alpha's configurator after switching back. "
        f"snippet={wrapper_html[:200]!r}"
    )


# ── C3: No export_fn → per-plot export button is absent from the DOM ──────


def test_export_btn_absent_when_no_export_fn(dash_duo, tmp_path):
    """Story (negative): a Gallery built without ``export_fn`` should not
    expose a per-plot Export button. (The standalone-script export button
    `gv-export-script-btn` is unconditional and remains.)

    Mirrors `TestExportButton.test_no_export_btn_without_fn` — the facade
    asserts via ``str(g.app.layout)``; this test asserts via the rendered DOM.
    """
    dir_alpha = _make_gallery_dir(tmp_path, "alpha")
    gallery = Gallery(backend=FileSystemBackend(dir_alpha))
    assert gallery.export_fn is None
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#gv-export-script-btn", timeout=10)
    time.sleep(0.5)

    # `#gv-export-script-btn` is unconditional and must be present.
    standalone_btn = dash_duo.find_element("#gv-export-script-btn")
    assert standalone_btn.is_displayed()

    # `#export-btn` is gated on `export_fn is not None` — absent here.
    try:
        offending = dash_duo.find_element("#export-btn")
    except NoSuchElementException:
        offending = None
    assert offending is None, (
        "per-plot export button should be absent when Gallery has no export_fn"
    )


def test_export_btn_present_when_export_fn_provided(dash_duo, tmp_path):
    """Positive companion to the above: with ``export_fn`` set, the per-plot
    Export button IS rendered and clickable.
    """
    dir_alpha = _make_gallery_dir(tmp_path, "alpha")
    gallery = Gallery(
        backend=FileSystemBackend(dir_alpha),
        # Identity function — we only verify presence + clickability here,
        # not the export contents.
        export_fn=lambda raw: raw,
    )
    dash_duo.start_server(gallery.app)

    dash_duo.wait_for_element("#export-btn", timeout=10)
    btn = dash_duo.find_element("#export-btn")
    assert btn.is_displayed()
    assert btn.is_enabled()
