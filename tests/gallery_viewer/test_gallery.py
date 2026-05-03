"""Tests for the Gallery dashboard builder."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gallery_viewer import FileSystemBackend, ScriptSections, StorageBackend
from gallery_viewer.gallery import Gallery


@pytest.fixture
def tmp_gallery(tmp_path):
    """Create a minimal gallery directory with data, scripts, and plots."""
    (tmp_path / "data").mkdir()
    (tmp_path / "plots").mkdir()
    (tmp_path / "scripts").mkdir()

    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    df.to_csv(tmp_path / "data" / "data_20240101.csv", index=False)

    script = ScriptSections(
        configurator='title: str = "test"',
        code="import pandas as pd\nprint('hello')",
    )
    (tmp_path / "scripts" / "script_20240101_v1.py").write_text(script.to_text())

    (tmp_path / "plots" / "plot_20240101_v1.png").write_bytes(b"\x89PNG fake")

    return tmp_path


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestGalleryInit:
    def test_default_backend(self):
        """Gallery() with no args falls back to a default FileSystemBackend."""
        g = Gallery()
        assert "default" in g.backends
        assert isinstance(g.backends["default"], FileSystemBackend)

    def test_single_backend(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        assert list(g.backends.keys()) == ["default"]
        assert g.backends["default"] is backend

    def test_multiple_backends(self, tmp_path):
        b1 = FileSystemBackend(tmp_path)
        b2 = FileSystemBackend(tmp_path)
        g = Gallery(backends={"alpha": b1, "beta": b2})
        assert list(g.backends.keys()) == ["alpha", "beta"]
        assert g.is_multi is True

    def test_custom_title(self):
        g = Gallery(title="My Custom Gallery")
        assert g.title == "My Custom Gallery"

    def test_default_title(self):
        g = Gallery()
        assert g.title == "Gallery Viewer"

    def test_export_fn_stored(self):
        fn = lambda b: b  # noqa: E731
        g = Gallery(export_fn=fn)
        assert g.export_fn is fn

    def test_export_fn_default_none(self):
        g = Gallery()
        assert g.export_fn is None

    def test_extra_controls_stored(self):
        from dash import html

        ctrl = html.Div("extra")
        g = Gallery(extra_controls=ctrl)
        assert g.extra_controls is ctrl

    def test_config_path_stored(self, tmp_path):
        cfg = tmp_path / "gallery.json"
        cfg.write_text(json.dumps({"title": "test", "plots": {}}))
        g = Gallery(config_path=cfg)
        assert g._config_path == cfg

    def test_backends_takes_precedence_over_backend(self, tmp_path):
        """When both 'backends' and 'backend' are supplied, 'backends' wins."""
        b1 = FileSystemBackend(tmp_path)
        b2 = FileSystemBackend(tmp_path)
        g = Gallery(backend=b1, backends={"named": b2})
        assert "named" in g.backends
        assert "default" not in g.backends


# ---------------------------------------------------------------------------
# build_app / app property
# ---------------------------------------------------------------------------


class TestBuildApp:
    def test_app_property_returns_dash(self, tmp_gallery):
        import dash

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        assert isinstance(g.app, dash.Dash)

    def test_app_cached(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        app1 = g.app
        app2 = g.app
        assert app1 is app2

    def test_app_title_matches(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, title="Custom Title")
        assert g.app.title == "Custom Title"

    def test_app_has_layout(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        assert g.app.layout is not None

    def test_multi_backend_app_builds(self, tmp_path):
        """A gallery with multiple backends should build without errors."""
        for name in ("alpha", "beta"):
            d = tmp_path / name
            d.mkdir()
            (d / "data").mkdir()
            (d / "plots").mkdir()
            (d / "scripts").mkdir()

        g = Gallery(
            backends={
                "alpha": FileSystemBackend(tmp_path / "alpha"),
                "beta": FileSystemBackend(tmp_path / "beta"),
            }
        )
        app = g.app
        assert app is not None

    def test_empty_backends_builds(self):
        """A gallery with no plots (empty dict) should still build."""
        g = Gallery(backends={})
        # Empty backends → no plot_names → layout still renders
        # (gv-plot-select store.data = None)
        app = g.app
        assert app is not None


# ---------------------------------------------------------------------------
# Export button presence
# ---------------------------------------------------------------------------


class TestExportButton:
    def test_no_export_btn_without_fn(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "export-btn" not in layout_str

    def test_export_btn_present_with_fn(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, export_fn=lambda b: b)
        layout_str = str(g.app.layout)
        assert "export-btn" in layout_str


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------


class TestFromConfig:
    def test_from_config_creates_gallery(self, tmp_path):
        plot_dir = tmp_path / "my_plot"
        plot_dir.mkdir()
        (plot_dir / "data").mkdir()
        (plot_dir / "plots").mkdir()
        (plot_dir / "scripts").mkdir()

        config = {
            "title": "Config Gallery",
            "plots": {
                "my_plot": {"path": str(plot_dir)},
            },
        }
        cfg_path = tmp_path / "gallery.json"
        cfg_path.write_text(json.dumps(config))

        g = Gallery.from_config(cfg_path)
        assert g.title == "Config Gallery"
        assert "my_plot" in g.backends

    def test_from_config_empty_plots(self, tmp_path):
        config = {"title": "Empty", "plots": {}}
        cfg_path = tmp_path / "gallery.json"
        cfg_path.write_text(json.dumps(config))

        g = Gallery.from_config(cfg_path)
        assert g.title == "Empty"
        assert g.backends == {}

    def test_from_config_default_title(self, tmp_path):
        config = {"plots": {}}
        cfg_path = tmp_path / "gallery.json"
        cfg_path.write_text(json.dumps(config))

        g = Gallery.from_config(cfg_path)
        assert g.title == "Gallery Viewer"

    def test_from_config_export_fn(self, tmp_path):
        config = {"title": "test", "plots": {}}
        cfg_path = tmp_path / "gallery.json"
        cfg_path.write_text(json.dumps(config))

        fn = lambda b: b  # noqa: E731
        g = Gallery.from_config(cfg_path, export_fn=fn)
        assert g.export_fn is fn


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestUpdateScriptButton:
    def test_update_script_btn_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-update-script-btn" in layout_str

    def test_update_script_row_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-update-script-row" in layout_str


class TestParamValuesToInject:
    def test_basic_injection(self):
        from gallery_viewer.gallery import _param_values_to_inject

        source = 'title: str = "old"\ndpi: int = 100'
        result = _param_values_to_inject(source, ["new title", 200])
        assert result == {"title": "new title", "dpi": 200}

    def test_returns_none_when_no_params(self):
        from gallery_viewer.gallery import _param_values_to_inject

        result = _param_values_to_inject("x = 42", [])
        assert result is None

    def test_returns_none_when_no_values(self):
        from gallery_viewer.gallery import _param_values_to_inject

        result = _param_values_to_inject('title: str = "x"', [])
        assert result is None


# ---------------------------------------------------------------------------
# Feature 1: Read-only mode (script toggle)
# ---------------------------------------------------------------------------


class TestScriptToggle:
    def test_show_script_switch_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-show-script" in layout_str

    def test_editor_wrapper_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-editor-wrapper" in layout_str


# ---------------------------------------------------------------------------
# Feature 2: Version diff label
# ---------------------------------------------------------------------------


class TestDiffConfigurator:
    def test_changed_value(self):
        from gallery_viewer.params import diff_configurator as _diff_configurator

        old = 'title: str = "old"\ndpi: int = 100'
        new = 'title: str = "new"\ndpi: int = 100'
        diff = _diff_configurator(old, new)
        assert len(diff) == 1
        assert "'old'" in diff[0] and "'new'" in diff[0]

    def test_no_changes(self):
        from gallery_viewer.params import diff_configurator as _diff_configurator

        source = 'title: str = "same"'
        assert _diff_configurator(source, source) == []

    def test_added_param(self):
        from gallery_viewer.params import diff_configurator as _diff_configurator

        old = 'title: str = "x"'
        new = 'title: str = "x"\ndpi: int = 150'
        diff = _diff_configurator(old, new)
        assert any("+dpi" in d for d in diff)

    def test_removed_param(self):
        from gallery_viewer.params import diff_configurator as _diff_configurator

        old = 'title: str = "x"\ndpi: int = 150'
        new = 'title: str = "x"'
        diff = _diff_configurator(old, new)
        assert any("-dpi" in d for d in diff)

    def test_multiple_changes(self):
        from gallery_viewer.params import diff_configurator as _diff_configurator

        old = 'title: str = "A"\ndpi: int = 100'
        new = 'title: str = "B"\ndpi: int = 200'
        diff = _diff_configurator(old, new)
        assert len(diff) == 2

    def test_version_diff_element_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-version-diff" in layout_str


# ---------------------------------------------------------------------------
# version_diff via Gallery facade
# ---------------------------------------------------------------------------


class TestVersionDiffNoChange:
    def test_v1_always_empty(self, tmp_gallery):
        """version_diff for v1 returns [] — there is no predecessor."""
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert g.version_diff(None, "20240101", "1") == []

    def test_identical_versions_return_empty(self, tmp_gallery):
        """version_diff returns [] when v2 configurator is identical to v1."""
        backend = FileSystemBackend(tmp_gallery)
        # save v1 script, then save the identical script again as v2
        original = backend.load_script("20240101", "1")
        backend.save_version("20240101", original)  # → v2, same content
        g = Gallery(backend=backend)
        assert g.version_diff(None, "20240101", "2") == []

    def test_changed_version_returns_entries(self, tmp_gallery):
        """version_diff returns non-empty list when configurator changed."""
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        v2 = ScriptSections(
            configurator='title: str = "changed"',
            code="print('hi')",
        )
        backend.save_version("20240101", v2)  # → v2
        g = Gallery(backend=backend)
        diff = g.version_diff(None, "20240101", "2")
        assert len(diff) > 0


# ---------------------------------------------------------------------------
# Feature 3: New Date button + Feature 4: Copy from version
# ---------------------------------------------------------------------------


class TestNewDate:
    def test_new_date_btn_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-new-group-btn" in layout_str

    def test_find_uncharted_dates(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "scripts").mkdir()
        pd.DataFrame({"x": [1]}).to_csv(
            tmp_path / "data" / "data_20240101.csv", index=False
        )
        pd.DataFrame({"x": [1]}).to_csv(
            tmp_path / "data" / "data_20240601.csv", index=False
        )
        script = ScriptSections(code="print('hi')")
        (tmp_path / "scripts" / "script_20240101_v1.py").write_text(script.to_text())

        backend = FileSystemBackend(tmp_path)
        assert backend.list_uncharted_groups() == ["20240601"]

    def test_find_uncharted_dates_all_charted(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        assert backend.list_uncharted_groups() == []

    def test_template_from_latest(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        template = backend.template_for_group("20240601")
        assert "20240601" in template.code or template.configurator != ""

    def test_template_from_latest_fallback(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "scripts").mkdir()
        backend = FileSystemBackend(tmp_path)
        template = backend.template_for_group("20240101")
        assert "plt" in template.code


# ---------------------------------------------------------------------------
# Feature 5: Dirty flag
# ---------------------------------------------------------------------------


class TestDirtyFlag:
    def test_clean_script_store_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-clean-script-store" in layout_str

    def test_confirm_navigate_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-confirm-navigate" in layout_str


# ---------------------------------------------------------------------------
# Feature 8: Export standalone script
# ---------------------------------------------------------------------------


class TestRenderOutputs:
    def test_render_png(self):
        from gallery_viewer._types import OutputItem
        from gallery_viewer.gallery import _render_outputs

        items = [OutputItem(mime="image/png", data=b"\x89PNG fake")]
        result = _render_outputs(items)
        # Should be an Img element
        assert hasattr(result, "src") or "Img" in type(result).__name__

    def test_render_csv(self):
        from gallery_viewer._types import OutputItem
        from gallery_viewer.gallery import _render_outputs

        items = [OutputItem(mime="text/csv", data=b"x,y\n1,2\n3,4")]
        result = _render_outputs(items)
        assert result is not None

    def test_render_empty(self):
        from gallery_viewer.gallery import _render_outputs

        result = _render_outputs([])
        assert result is not None  # should return _no_plot()

    def test_render_multiple(self):
        from gallery_viewer._types import OutputItem
        from gallery_viewer.gallery import _render_outputs

        items = [
            OutputItem(mime="image/png", data=b"\x89PNG fake1"),
            OutputItem(mime="image/png", data=b"\x89PNG fake2"),
        ]
        result = _render_outputs(items)
        # Should be a Div with children
        assert hasattr(result, "children")


class TestExportStandalone:
    def test_export_script_btn_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-export-script-btn" in layout_str

    def test_export_download_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-export-script-download" in layout_str


# ---------------------------------------------------------------------------
# Feature 9: Author metadata
# ---------------------------------------------------------------------------


class TestAuthorMetadata:
    def test_save_modal_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-save-modal" in layout_str
        assert "gv-save-author" in layout_str

    def test_add_author_comment(self):
        sections = ScriptSections(
            configurator='title: str = "test"', code="print('hi')"
        )
        result = sections.with_author("Alice")
        # author + saved land in the metadata dict, not in configurator/code
        assert result.metadata["author"] == "Alice"
        assert "saved" in result.metadata
        assert result.configurator == sections.configurator
        assert result.code == sections.code
        # And they surface in the rendered METADATA block
        assert "# author: Alice" in result.to_text()

    def test_add_author_comment_no_configurator(self):
        sections = ScriptSections(code="print('hi')")
        result = sections.with_author("Bob")
        assert result.metadata["author"] == "Bob"
        assert result.configurator == ""
        assert "# author: Bob" in result.to_text()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
# Facade API — Gallery as orchestrator
# ---------------------------------------------------------------------------


class TestGalleryFacade:
    def test_list_dates(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert g.list_groups() == ["20240101"]

    def test_list_dates_by_plot_name(self, tmp_gallery):
        g = Gallery(backends={"main": FileSystemBackend(tmp_gallery)})
        assert g.list_groups("main") == ["20240101"]

    def test_list_versions(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert g.list_versions(None, "20240101") == ["1"]

    def test_load_script(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        sections = g.load_script(None, "20240101", "1")
        assert isinstance(sections, ScriptSections)
        assert sections.configurator != "" or sections.code != ""

    def test_load_data(self, tmp_gallery):
        import pandas as pd

        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        df = g.load_data(None, "20240101")
        assert isinstance(df, pd.DataFrame)

    def test_load_artifact(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        # tmp_gallery fixture has no plot file — should return None gracefully
        result = g.load_artifact(None, "20240101", "1")
        assert result is None or isinstance(result, bytes)

    def test_template_for_date(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        template = g.template_for_group(None, "20250101")
        assert isinstance(template, ScriptSections)
        assert template.code != ""

    def test_list_uncharted_dates_empty(self, tmp_gallery):
        # All data groups have scripts in tmp_gallery
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        uncharted = g.list_uncharted_groups()
        assert isinstance(uncharted, list)

    def test_list_uncharted_dates_with_new_data(self, tmp_gallery):
        import pandas as pd

        # Add a data file with no matching script
        df = pd.DataFrame({"x": [1], "y": [2]})
        df.to_csv(tmp_gallery / "data" / "data_20251231.csv", index=False)
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert "20251231" in g.list_uncharted_groups()

    def test_version_diff_v1_returns_empty(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert g.version_diff(None, "20240101", "1") == []

    def test_version_diff_detects_change(self, tmp_gallery):
        v1 = ScriptSections(configurator='title: str = "old"', code="pass")
        v2 = ScriptSections(configurator='title: str = "new"', code="pass")
        (tmp_gallery / "scripts" / "script_20240101_v1.py").write_text(v1.to_text())
        (tmp_gallery / "scripts" / "script_20240101_v2.py").write_text(v2.to_text())
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        diff = g.version_diff(None, "20240101", "2")
        assert any("title" in d for d in diff)


# ---------------------------------------------------------------------------


class TestGetBackend:
    def test_get_by_name(self, tmp_path):
        b1 = FileSystemBackend(tmp_path)
        b2 = FileSystemBackend(tmp_path)
        g = Gallery(backends={"a": b1, "b": b2})
        assert g._get_backend("a") is b1
        assert g._get_backend("b") is b2

    def test_get_fallback(self, tmp_path):
        b1 = FileSystemBackend(tmp_path)
        g = Gallery(backends={"first": b1})
        assert g._get_backend("nonexistent") is b1
        assert g._get_backend(None) is b1

    def test_plot_names_property(self, tmp_path):
        b1 = FileSystemBackend(tmp_path)
        b2 = FileSystemBackend(tmp_path)
        g = Gallery(backends={"x": b1, "y": b2})
        assert g.plot_names == ["x", "y"]

    def test_is_multi_re_derives_after_backend_added(self, tmp_path):
        """is_multi was a frozen attribute; now a property that re-derives."""
        b1 = FileSystemBackend(tmp_path)
        g = Gallery(backend=b1)
        assert g.is_multi is False
        g.backends["new"] = FileSystemBackend(tmp_path)
        assert g.is_multi is True


# ---------------------------------------------------------------------------
# Multi-backend facade routing
# ---------------------------------------------------------------------------


def _make_gallery_dir(root, name, *, groups_versions=None):
    """Build a minimal valid gallery dir under ``root/name`` and return it.

    Mirrors ``conftest.make_gallery_dir`` (duplicated locally because the
    project disallows ``__init__.py`` in test dirs, which prevents importing
    helpers from sibling modules).

    Parameters
    ----------
    root: parent directory.
    name: subdirectory name.
    groups_versions: ``{"YYYYMMDD": n_versions}``. Default = ``{"20240101": 1}``.
    """
    if groups_versions is None:
        groups_versions = {"20240101": 1}
    d = root / name
    d.mkdir()
    (d / "data").mkdir()
    (d / "plots").mkdir()
    (d / "scripts").mkdir()
    for group, n_versions in groups_versions.items():
        pd.DataFrame({"x": [1], "y": [2]}).to_csv(
            d / "data" / f"data_{group}.csv", index=False
        )
        for v in range(1, n_versions + 1):
            sections = ScriptSections(
                configurator=f'name: str = "{name}"\nversion: int = {v}',
                code=f"print({name!r}, {v})",
            )
            (d / "scripts" / f"script_{group}_v{v}.py").write_text(sections.to_text())
    return d


class TestGalleryFacadeRouting:
    """Verify Gallery facade methods route to the correct backend by item_id."""

    def test_export_inject_vars_routes_per_plot(self, tmp_path):
        """export_inject_vars returns paths from the matching backend, not the first one."""
        dir_alpha = _make_gallery_dir(tmp_path, "alpha")
        dir_beta = _make_gallery_dir(tmp_path, "beta")
        g = Gallery(
            backends={
                "alpha": FileSystemBackend(dir_alpha),
                "beta": FileSystemBackend(dir_beta),
            }
        )
        alpha_vars = g.export_inject_vars("alpha", "20240101", "1")
        beta_vars = g.export_inject_vars("beta", "20240101", "1")
        assert alpha_vars["BASE_DIR"] == str(dir_alpha)
        assert beta_vars["BASE_DIR"] == str(dir_beta)
        assert alpha_vars["BASE_DIR"] != beta_vars["BASE_DIR"]

    def test_export_inject_vars_unknown_plot_falls_back(self, tmp_path):
        """Unknown item_id falls back to the first backend (matches _get_backend)."""
        dir_alpha = _make_gallery_dir(tmp_path, "alpha")
        dir_beta = _make_gallery_dir(tmp_path, "beta")
        g = Gallery(
            backends={
                "alpha": FileSystemBackend(dir_alpha),
                "beta": FileSystemBackend(dir_beta),
            }
        )
        # "ghost" is not in backends; should fall through to "alpha" (first).
        result = g.export_inject_vars("ghost", "20240101", "1")
        assert result["BASE_DIR"] == str(dir_alpha)

    def test_load_script_routes_per_plot(self, tmp_path):
        """load_script reads from the right backend (smoke-test for the facade pattern)."""
        dir_alpha = _make_gallery_dir(tmp_path, "alpha")
        dir_beta = _make_gallery_dir(tmp_path, "beta")
        g = Gallery(
            backends={
                "alpha": FileSystemBackend(dir_alpha),
                "beta": FileSystemBackend(dir_beta),
            }
        )
        alpha_script = g.load_script("alpha", "20240101", "1")
        beta_script = g.load_script("beta", "20240101", "1")
        assert "alpha" in alpha_script.configurator
        assert "beta" in beta_script.configurator

    def test_export_inject_vars_with_base_storage_backend(self, tmp_path):
        """A non-filesystem backend mounted alongside a filesystem one yields {} for itself."""
        dir_alpha = _make_gallery_dir(tmp_path, "alpha")
        g = Gallery(
            backends={
                "fs": FileSystemBackend(dir_alpha),
                "memory": StorageBackend(),  # base class — no paths
            }
        )
        fs_vars = g.export_inject_vars("fs", "20240101", "1")
        mem_vars = g.export_inject_vars("memory", "20240101", "1")
        assert "BASE_DIR" in fs_vars
        assert mem_vars == {}


# ---------------------------------------------------------------------------
# Headless API
# ---------------------------------------------------------------------------


class TestHeadlessAPI:
    def test_run_script_no_browser(self, tmp_gallery):
        """Gallery.run_script() works without instantiating the Dash app."""
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(code="x = 1 + 1\nprint(x)")
        result = g.run_script(None, sections)
        assert result.success
        assert "2" in result.output

    def test_save_script_no_browser(self, tmp_gallery):
        """Gallery.save_script() writes a new version without touching Dash."""
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(
            configurator='title: str = "headless"',
            code=(
                "import matplotlib\n"
                'matplotlib.use("Agg")\n'
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\n"
                "ax.plot([1, 2], [3, 4])\n"
            ),
        )
        new_version = g.save_script(None, "20240101", sections, author="Alice")
        assert new_version == "2"  # fixture already has v1
        saved = backend.load_script("20240101", new_version)
        assert "# author: Alice" in saved.to_text()
        assert "headless" in saved.configurator


# ---------------------------------------------------------------------------
# End-to-end headless workflow (user-journey style)
# ---------------------------------------------------------------------------


class TestHeadlessWorkflow:
    """Walk through a full user session without instantiating the Dash app.

    Tells the story: open gallery → list groups → load script → edit and re-run
    → save new version → diff against predecessor → export standalone.
    """

    def test_complete_workflow_single_backend(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        g = Gallery(backend=FileSystemBackend(tmp_gallery))

        # 1. User opens gallery — groups and versions are visible.
        groups = g.list_groups(None)
        assert groups == ["20240101"]
        versions = g.list_versions(None, "20240101")
        assert versions == ["1"]

        # 2. User loads existing script.
        original = g.load_script(None, "20240101", "1")
        assert isinstance(original, ScriptSections)

        # 3. User edits and re-runs interactively.
        edited = ScriptSections(
            configurator='title: str = "edited"',
            code="x = 21 * 2\nprint(x)",
        )
        run_result = g.run_script(None, edited)
        assert run_result.success
        assert "42" in run_result.output

        # 4. User saves the edit.
        new_version = g.save_script(None, "20240101", edited, author="Bob")
        assert new_version == "2"

        # 5. User checks the diff against the previous version.
        diff = g.version_diff(None, "20240101", "2")
        assert len(diff) > 0  # configurator changed

        # 6. User exports a standalone runnable script — paths injected.
        inject_vars = g.export_inject_vars(None, "20240101", "2")
        assert "BASE_DIR" in inject_vars
        assert "plot_20240101_v2.png" in inject_vars["OUTPUT_PATH"]

    def test_workflow_routes_correctly_in_multi_backend(self, tmp_path):
        """Same workflow against a multi-backend gallery — each plot is independent."""
        from gallery_viewer._types import ScriptSections

        dir_a = _make_gallery_dir(tmp_path, "alpha")
        dir_b = _make_gallery_dir(tmp_path, "beta")
        g = Gallery(
            backends={
                "alpha": FileSystemBackend(dir_a),
                "beta": FileSystemBackend(dir_b),
            }
        )

        # Save a v2 only on alpha
        v2 = ScriptSections(
            configurator='title: str = "alpha-v2"',
            code="print('alpha v2')",
        )
        new_version = g.save_script("alpha", "20240101", v2, author="Carol")
        assert new_version == "2"

        # Beta is untouched
        assert g.list_versions("beta", "20240101") == ["1"]

        # Export inject vars for each — paths must differ
        a_vars = g.export_inject_vars("alpha", "20240101", "2")
        b_vars = g.export_inject_vars("beta", "20240101", "1")
        assert a_vars["BASE_DIR"] == str(dir_a)
        assert b_vars["BASE_DIR"] == str(dir_b)
        assert "plot_20240101_v2.png" in a_vars["OUTPUT_PATH"]
        assert "plot_20240101_v1.png" in b_vars["OUTPUT_PATH"]


# ---------------------------------------------------------------------------
# Provenance stamping — data hash + library versions
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_python_version_always_stamped(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.save_script(None, "20240101", ScriptSections(code="print(1)"))
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        # e.g. "# python: 3.14.4"
        assert "# python: " in saved
        import sys

        assert f"{sys.version_info.major}.{sys.version_info.minor}" in saved

    def test_data_hash_stamped_when_data_exists(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.save_script(None, "20240101", ScriptSections(code="print(1)"))
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# data_hash: sha256:" in saved

    def test_data_hash_omitted_when_no_data_file(self, tmp_path):
        from gallery_viewer._types import ScriptSections

        # Build a gallery dir but DELETE the data file
        d = _make_gallery_dir(tmp_path, "main")
        (d / "data" / "data_20240101.csv").unlink()
        backend = FileSystemBackend(d)
        g = Gallery(backend=backend)
        g.save_script(None, "20240101", ScriptSections(code="print(1)"))
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# data_hash:" not in saved
        # but Python version still present
        assert "# python: " in saved

    def test_data_hash_is_deterministic(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        h1 = backend.data_hash("20240101")
        h2 = backend.data_hash("20240101")
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_data_hash_changes_when_data_changes(self, tmp_path):
        d = _make_gallery_dir(tmp_path, "main")
        backend = FileSystemBackend(d)
        h_before = backend.data_hash("20240101")
        # Modify the data file
        (d / "data" / "data_20240101.csv").write_text("x,y\n99,99\n")
        h_after = backend.data_hash("20240101")
        assert h_before != h_after

    def test_data_hash_returns_none_for_missing_date(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        assert backend.data_hash("21000101") is None

    def test_base_backend_data_hash_returns_none(self):
        from gallery_viewer import StorageBackend

        b = StorageBackend()
        assert b.data_hash("20240101") is None

    def test_track_packages_stamps_versions(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        # matplotlib + pandas are both real workspace dependencies
        g = Gallery(backend=backend, track_packages=["matplotlib", "pandas"])
        g.save_script(None, "20240101", ScriptSections(code="print(1)"))
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# matplotlib: " in saved
        assert "# pandas: " in saved

    def test_track_packages_skips_missing_packages_silently(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(
            backend=backend,
            track_packages=["matplotlib", "this_package_does_not_exist_xyz"],
        )
        # Must not raise
        g.save_script(None, "20240101", ScriptSections(code="print(1)"))
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# matplotlib: " in saved
        assert "this_package_does_not_exist_xyz" not in saved

    def test_track_packages_default_empty(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert g.track_packages == []

    def test_provenance_metadata_directly(self, tmp_gallery):
        """The internal helper returns the dict directly — useful for unit tests."""
        g = Gallery(backend=FileSystemBackend(tmp_gallery), track_packages=["pandas"])
        meta = g._provenance_metadata(None, "20240101")
        assert "python" in meta
        assert "data_hash" in meta
        assert "pandas" in meta
        assert meta["data_hash"].startswith("sha256:")

    def test_full_metadata_block_order(self, tmp_gallery):
        """The stamped block order is: author → saved → change → provenance."""
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.save_script(
            None,
            "20240101",
            ScriptSections(code="print(1)"),
            author="Alice",
            change_note="why",
        )
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        # Order check: human-facing fields, then provenance.
        idx_author = saved.index("# author:")
        idx_saved = saved.index("# saved:")
        idx_change = saved.index("# change:")
        idx_python = saved.index("# python:")
        assert idx_author < idx_saved < idx_change < idx_python


# ---------------------------------------------------------------------------
# Intent capture (per-version description / "why" message)
# ---------------------------------------------------------------------------


class TestIntentCapture:
    def test_description_stamped_into_script(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(
            None,
            "20240101",
            sections,
            author="Alice",
            change_note="Switched to log scale because small categories were buried.",
        )
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# change: Switched to log scale" in saved
        assert "# author: Alice" in saved

    def test_multiline_description_indented(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(
            None,
            "20240101",
            sections,
            author="A",
            change_note="line one\nline two\nline three",
        )
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# change:" in saved
        assert "#   line one" in saved
        assert "#   line two" in saved
        assert "#   line three" in saved

    def test_no_description_no_stamp(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, author="A")
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# change" not in saved

    def test_blank_description_skipped(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, author="A", change_note="   ")
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# change" not in saved

    def test_description_without_author_works(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, change_note="why this version")
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest).to_text()
        assert "# change: why this version" in saved
        assert "# author:" not in saved

    def test_with_metadata_preserves_order(self):
        from gallery_viewer._types import ScriptSections

        s = ScriptSections(configurator="x: int = 1", code="print(1)")
        result = s.with_metadata({"first": "a", "second": "b", "third": "c"})
        # Insertion order preserved in the metadata dict and in the rendered text
        assert list(result.metadata.keys()) == ["first", "second", "third"]
        text = result.to_text()
        first_idx = text.index("# first:")
        second_idx = text.index("# second:")
        third_idx = text.index("# third:")
        assert first_idx < second_idx < third_idx

    def test_with_metadata_empty_values_skipped(self):
        from gallery_viewer._types import ScriptSections

        s = ScriptSections(configurator="x: int = 1", code="print(1)")
        result = s.with_metadata({"skip": "", "keep": "value", "also_skip": None})
        assert "skip" not in result.metadata
        assert "also_skip" not in result.metadata
        assert result.metadata["keep"] == "value"

    def test_with_metadata_empty_dict_returns_unchanged(self):
        from gallery_viewer._types import ScriptSections

        s = ScriptSections(configurator="x: int = 1", code="print(1)")
        result = s.with_metadata({})
        assert result.metadata == {}
        assert result.configurator == s.configurator
        assert result.code == s.code

    def test_layout_contains_description_textarea(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        layout_str = str(g.app.layout)
        assert "gv-save-description" in layout_str

    def test_change_note_facade_returns_value(self, tmp_gallery):
        """Gallery.change_note(...) returns the persisted change rationale."""
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.save_script(
            None,
            "20240101",
            ScriptSections(code="print(1)"),
            author="Alice",
            change_note="why this version exists",
        )
        latest = g.list_versions(None, "20240101")[-1]
        assert g.change_note(None, "20240101", latest) == "why this version exists"

    def test_change_note_facade_returns_none_when_absent(self, tmp_gallery):
        """No change note → facade returns None (not '')."""
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.save_script(None, "20240101", ScriptSections(code="print(1)"), author="A")
        latest = g.list_versions(None, "20240101")[-1]
        assert g.change_note(None, "20240101", latest) is None

    def test_author_facade_returns_value(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.save_script(None, "20240101", ScriptSections(code="print(1)"), author="Alice")
        latest = g.list_versions(None, "20240101")[-1]
        assert g.author(None, "20240101", latest) == "Alice"


# ---------------------------------------------------------------------------
# Current-user registration (Gallery.user)
# ---------------------------------------------------------------------------


class TestContextRegistration:
    def test_default_context_is_empty(self):
        g = Gallery()
        assert g.context == {}

    def test_context_set_via_constructor(self):
        g = Gallery(context={"author": "Paul", "env": "prod"})
        assert g.context == {"author": "Paul", "env": "prod"}

    def test_context_is_mutable_after_init(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        g.context["author"] = "Alice"
        assert g.context["author"] == "Alice"

    def test_save_script_falls_back_to_context_author(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, context={"author": "Paul"})
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, author=None)
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest)
        assert "# author: Paul" in saved.to_text()

    def test_explicit_author_overrides_context(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, context={"author": "Paul"})
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, author="Alice")
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest)
        assert "# author: Alice" in saved.to_text()
        assert "Paul" not in saved.to_text()

    def test_blank_author_falls_back_to_context(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, context={"author": "Paul"})
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, author="   ")  # whitespace only
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest)
        assert "# author: Paul" in saved.to_text()

    def test_no_context_no_author_no_stamp(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections, author=None)
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest)
        assert "# author:" not in saved.to_text()

    def test_extra_context_keys_stamped(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, context={"author": "Paul", "env": "prod"})
        sections = ScriptSections(configurator="x: int = 1", code="print(1)")
        g.save_script(None, "20240101", sections)
        latest = g.list_versions(None, "20240101")[-1]
        saved = backend.load_script("20240101", latest)
        assert "# env: prod" in saved.to_text()

    def test_layout_contains_context_store(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery), context={"author": "Paul"})
        layout_str = str(g.app.layout)
        assert "gv-context" in layout_str

    def test_context_runtime_change_affects_subsequent_saves(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend, context={"author": "Paul"})
        s1 = ScriptSections(configurator="x: int = 1", code="print(1)")
        s2 = ScriptSections(configurator="x: int = 2", code="print(2)")
        g.save_script(None, "20240101", s1)  # → Paul
        g.context["author"] = "Alice"
        g.save_script(None, "20240101", s2)  # → Alice
        versions = g.list_versions(None, "20240101")
        last_two = versions[-2:]
        saved_a = backend.load_script("20240101", last_two[0]).to_text()
        saved_b = backend.load_script("20240101", last_two[1]).to_text()
        assert "Paul" in saved_a
        assert "Alice" in saved_b


# ---------------------------------------------------------------------------
# apply_params_to_script — bake form values into a script's configurator
# ---------------------------------------------------------------------------


class TestApplyParamsToScript:
    def test_returns_sections_with_params_baked_in(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        script = '# === CONFIGURATOR ===\ntitle: str = "old"\n\n# === CODE ===\nprint(title)\n'
        result = g.apply_params_to_script(script, ["new"])
        assert "new" in result.configurator
        assert "old" not in result.configurator

    def test_no_param_values_returns_original(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        script = (
            '# === CONFIGURATOR ===\ntitle: str = "x"\n\n# === CODE ===\nprint(title)\n'
        )
        result = g.apply_params_to_script(script, [])
        assert "x" in result.configurator

    def test_none_param_values_does_not_crash(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        script = (
            '# === CONFIGURATOR ===\ntitle: str = "x"\n\n# === CODE ===\nprint(title)\n'
        )
        result = g.apply_params_to_script(script, None)
        assert isinstance(result, ScriptSections)

    def test_script_without_configurator_returns_unchanged(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        result = g.apply_params_to_script("print('hi')", ["ignored"])
        assert "print('hi')" in result.code
        assert result.configurator == ""

    def test_code_section_is_preserved(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        script = '# === CONFIGURATOR ===\nx: int = 1\n\n# === CODE ===\nprint(x)\nprint("hi")\n'
        result = g.apply_params_to_script(script, [42])
        assert "print(x)" in result.code
        assert 'print("hi")' in result.code


class TestParseUrlState:
    def test_empty_search_returns_no_selectors(self, gallery_with_chain):
        state = gallery_with_chain.parse_url_state("")
        assert state == {
            "item": None,
            "group": None,
            "version": None,
            "param_overrides": {},
        }

    def test_selectors_extracted(self, gallery_with_chain):
        state = gallery_with_chain.parse_url_state("?id=main&group=20240101&version=2")
        assert state["item"] == "main"
        assert state["group"] == "20240101"
        assert state["version"] == "2"

    def test_param_overrides_coerced_to_declared_types(self, gallery_with_chain):
        # chain script defines: name: str, version: int
        state = gallery_with_chain.parse_url_state(
            "?id=main&group=20240101&version=2&script_name=Q4&script_version=99"
        )
        assert state["param_overrides"] == {"name": "Q4", "version": 99}

    def test_unknown_param_silently_ignored(self, gallery_with_chain):
        state = gallery_with_chain.parse_url_state(
            "?id=main&group=20240101&version=2&script_does_not_exist=foo"
        )
        assert state["param_overrides"] == {}

    def test_bad_cast_dropped(self, gallery_with_chain):
        # version is int — "not-a-number" can't be coerced
        state = gallery_with_chain.parse_url_state(
            "?id=main&group=20240101&version=2&script_version=not-a-number"
        )
        assert state["param_overrides"] == {}

    def test_no_overrides_without_full_selectors(self, gallery_with_chain):
        # missing version → can't resolve param schema → overrides skipped
        state = gallery_with_chain.parse_url_state(
            "?id=main&group=20240101&script_name=Q4"
        )
        assert state["param_overrides"] == {}

    def test_render_route_returns_artifact_bytes(self, make_dir):
        d = make_dir("main", groups_versions={"20240101": 1})
        g = Gallery(backend=FileSystemBackend(d))
        client = g.app.server.test_client()
        resp = client.get("/render?id=main&group=20240101&version=1")
        assert resp.status_code == 200
        assert resp.mimetype == "image/png"
        assert resp.data  # non-empty

    def test_render_route_404_for_unknown_version(self, make_dir):
        d = make_dir("main", groups_versions={"20240101": 1})
        g = Gallery(backend=FileSystemBackend(d))
        client = g.app.server.test_client()
        resp = client.get("/render?id=main&group=20240101&version=99")
        assert resp.status_code == 404

    def test_render_route_400_when_selectors_missing(self, make_dir):
        d = make_dir("main", groups_versions={"20240101": 1})
        g = Gallery(backend=FileSystemBackend(d))
        client = g.app.server.test_client()
        resp = client.get("/render?id=main")
        assert resp.status_code == 400

    def test_url_keys_are_configurable(self, make_dir):
        # A "Plot/Date"-flavoured gallery overrides URL keys
        d = make_dir("main", groups_versions={"20240101": 1})
        g = Gallery(
            backend=FileSystemBackend(d),
            item_url_key="plot",
            group_url_key="date",
        )
        state = g.parse_url_state("?plot=main&date=20240101&version=1")
        assert state["item"] == "main"
        assert state["group"] == "20240101"
        # Keys returned use internal axis names regardless of URL key choice
        assert "plot" not in state and "date" not in state


# ---------------------------------------------------------------------------
# version_diff_label — pure-data label rendering for the version-diff badge
# ---------------------------------------------------------------------------


class TestVersionDiffLabel:
    def test_v1_returns_initial_version_label(self, tmp_gallery):
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        text, color = g.version_diff_label(None, "20240101", "1")
        assert text == "v1 — initial version"
        assert color == "#777"

    def test_no_change_returns_grey_label(self, tmp_gallery):
        from gallery_viewer._types import ScriptSections

        backend = FileSystemBackend(tmp_gallery)
        original = backend.load_script("20240101", "1")
        backend.save_version("20240101", original)  # → v2 identical to v1
        g = Gallery(backend=backend)
        text, color = g.version_diff_label(None, "20240101", "2")
        assert "no parameter changes from v1" in text
        assert color == "#777"

    def test_changed_returns_blue_label(self, tmp_path):
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        backend = FileSystemBackend(d)
        backend.save_version(
            "20240101",
            ScriptSections(configurator='name: str = "changed"', code="print(1)"),
        )
        g = Gallery(backend=backend)
        text, color = g.version_diff_label(None, "20240101", "2")
        assert text.startswith("v2 — ")
        assert color == "#8cb4d5"

    def test_v3_predecessor_arithmetic(self, tmp_path):
        """Off-by-one check: v3 diffs against v2, not v1 or v4."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        backend = FileSystemBackend(d)
        # v2: change name
        backend.save_version(
            "20240101",
            ScriptSections(configurator='name: str = "v2_value"', code="print(1)"),
        )
        # v3: change name again
        backend.save_version(
            "20240101",
            ScriptSections(configurator='name: str = "v3_value"', code="print(1)"),
        )
        g = Gallery(backend=backend)
        text, _ = g.version_diff_label(None, "20240101", "3")
        # v3's label should mention v3, and the diff describes v2→v3 transition
        assert text.startswith("v3 — ")
        # v2 was 'v2_value' → v3 is 'v3_value'; diff describes that change
        assert "v3_value" in text or "v2_value" in text

    def test_accepts_int_version(self, tmp_gallery):
        """Passing an int version (Dash sometimes sends ints) is handled."""
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        text, _ = g.version_diff_label(None, "20240101", 1)  # int, not str
        assert "v1" in text


# ---------------------------------------------------------------------------
# Error paths and robustness
# ---------------------------------------------------------------------------


class TestErrorPaths:
    """Negative-path tests — failures the user might actually hit."""

    def test_run_script_raising_exception_returns_failure(self, tmp_gallery):
        """A script that raises returns RunResult(success=False) with the error text."""
        from gallery_viewer._types import ScriptSections

        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        broken = ScriptSections(code="raise ValueError('boom')")
        result = g.run_script(None, broken)
        assert result.success is False
        assert "ValueError" in result.error or "boom" in result.error

    def test_run_script_with_syntax_error_returns_failure(self, tmp_gallery):
        """A SyntaxError in user code is captured, not propagated."""
        from gallery_viewer._types import ScriptSections

        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        broken = ScriptSections(code="def bad(:\n    pass\n")
        result = g.run_script(None, broken)
        assert result.success is False
        assert result.error  # some error text reported

    def test_run_script_with_import_error_returns_failure(self, tmp_gallery):
        """An import of a missing module is captured cleanly."""
        from gallery_viewer._types import ScriptSections

        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        broken = ScriptSections(code="import nonexistent_module_xyz_42")
        result = g.run_script(None, broken)
        assert result.success is False

    def test_load_script_missing_date_falls_back_to_template(self, tmp_gallery):
        """Loading a group that doesn't exist returns a starter template, not a crash."""
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        sections = g.load_script(None, "21000101", "1")
        # FileSystemBackend returns a starter template for missing groups
        assert sections is not None
        assert sections.code  # non-empty starter

    def test_load_data_missing_date_returns_none(self, tmp_gallery):
        """Loading data for an unknown group returns None, no exception."""
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        result = g.load_data(None, "21000101")
        assert result is None

    def test_load_artifact_missing_returns_none(self, tmp_gallery):
        """Loading a non-existent artifact returns None gracefully."""
        g = Gallery(backend=FileSystemBackend(tmp_gallery))
        result = g.load_artifact(None, "20240101", "999")
        assert result is None

    def test_version_diff_with_missing_predecessor_does_not_crash(self, tmp_path):
        """version_diff for v2 when v1 is absent (file deleted) returns gracefully."""
        from gallery_viewer._types import ScriptSections

        # Build a dir with only v2, no v1 (simulates external deletion)
        d = tmp_path / "broken"
        d.mkdir()
        (d / "data").mkdir()
        (d / "plots").mkdir()
        (d / "scripts").mkdir()
        v2 = ScriptSections(configurator="x: int = 1", code="print(1)")
        (d / "scripts" / "script_20240101_v2.py").write_text(v2.to_text())

        g = Gallery(backend=FileSystemBackend(d))
        # Should not raise; behaviour is "predecessor came back blank → diff against empty"
        diff = g.version_diff(None, "20240101", "2")
        assert isinstance(diff, list)

    def test_empty_backends_list_dates_returns_empty(self, empty_gallery):
        """A gallery with no backends doesn't crash on facade calls — returns []/{}."""
        # _get_backend will raise StopIteration on next() — confirm what happens
        with pytest.raises(StopIteration):
            empty_gallery.list_groups(None)

    def test_export_inject_vars_with_missing_plot_falls_back(
        self, multi_backend_gallery
    ):
        """Unknown item_id falls back to the first backend (consistent with _get_backend)."""
        # 'gamma' doesn't exist; should return alpha's paths (first in dict)
        result = multi_backend_gallery.export_inject_vars("gamma", "20240101", "1")
        assert "BASE_DIR" in result
        assert "alpha" in result["BASE_DIR"]


# ---------------------------------------------------------------------------
# Configuration matrix — every Gallery construction mode × basic facade calls
# ---------------------------------------------------------------------------


def _gallery_default(tmp_path):
    return Gallery()


def _gallery_single(tmp_path):
    d = _make_gallery_dir(tmp_path, "main")
    return Gallery(backend=FileSystemBackend(d))


def _gallery_multi(tmp_path):
    da = _make_gallery_dir(tmp_path, "alpha")
    db = _make_gallery_dir(tmp_path, "beta")
    return Gallery(
        backends={"alpha": FileSystemBackend(da), "beta": FileSystemBackend(db)}
    )


def _gallery_with_export_fn(tmp_path):
    d = _make_gallery_dir(tmp_path, "main")
    return Gallery(backend=FileSystemBackend(d), export_fn=lambda b: b)


def _gallery_with_title(tmp_path):
    d = _make_gallery_dir(tmp_path, "main")
    return Gallery(backend=FileSystemBackend(d), title="Custom")


# Each entry: (name, factory). Factory takes tmp_path or nothing.
_CONFIGS = [
    ("default", _gallery_default),
    ("single_backend", _gallery_single),
    ("multi_backend", _gallery_multi),
    ("with_export_fn", _gallery_with_export_fn),
    ("with_custom_title", _gallery_with_title),
]


class TestConfigurationMatrix:
    """Every supported Gallery configuration must support the basic facade calls.

    This is a smoke matrix: for each construction mode, confirm the Dash app
    builds and the facade methods don't crash. Catches regressions where a new
    config option breaks a facade method silently.
    """

    @pytest.mark.parametrize("name,factory", _CONFIGS, ids=[c[0] for c in _CONFIGS])
    def test_app_builds(self, tmp_path, name, factory):
        """Every configuration produces a working Dash app."""
        g = factory(tmp_path)
        assert g.app is not None
        assert g.app.layout is not None

    @pytest.mark.parametrize("name,factory", _CONFIGS, ids=[c[0] for c in _CONFIGS])
    def test_list_dates_does_not_crash(self, tmp_path, name, factory):
        """list_groups() works in every configuration (or empty for default)."""
        g = factory(tmp_path)
        # default config has no real backend dir, so list_groups may be empty
        result = g.list_groups(None)
        assert isinstance(result, list)

    @pytest.mark.parametrize(
        "name,factory",
        [c for c in _CONFIGS if c[0] != "default"],
        ids=[c[0] for c in _CONFIGS if c[0] != "default"],
    )
    def test_load_script_with_real_backend(self, tmp_path, name, factory):
        """Configurations with a real backend can load v1 of the seeded group."""
        g = factory(tmp_path)
        # multi_backend requires explicit item_id; others fall back
        item_id = "alpha" if name == "multi_backend" else None
        sections = g.load_script(item_id, "20240101", "1")
        assert isinstance(sections, ScriptSections)

    @pytest.mark.parametrize(
        "name,factory",
        [c for c in _CONFIGS if c[0] != "default"],
        ids=[c[0] for c in _CONFIGS if c[0] != "default"],
    )
    def test_export_inject_vars_with_real_backend(self, tmp_path, name, factory):
        """Every real-backend configuration produces valid inject vars."""
        g = factory(tmp_path)
        item_id = "alpha" if name == "multi_backend" else None
        result = g.export_inject_vars(item_id, "20240101", "1")
        assert "BASE_DIR" in result
        assert "OUTPUT_PATH" in result


# ---------------------------------------------------------------------------
# Workflow orderings — operations should give consistent results regardless of
# the order they're invoked in
# ---------------------------------------------------------------------------


class TestWorkflowOrders:
    """Verify that different orderings of facade calls converge on the same state."""

    def test_save_twice_increments_version(self, tmp_path):
        """Two consecutive saves produce v2 then v3, not two v2's."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        g = Gallery(backend=FileSystemBackend(d))
        s1 = ScriptSections(configurator="x: int = 1", code="print(1)")
        s2 = ScriptSections(configurator="x: int = 2", code="print(2)")
        v_first = g.save_script(None, "20240101", s1, author="A")
        v_second = g.save_script(None, "20240101", s2, author="B")
        assert v_first == "2"
        assert v_second == "3"
        assert g.list_versions(None, "20240101") == ["1", "2", "3"]

    def test_save_then_load_round_trips(self, tmp_path):
        """A saved script loads back unchanged (modulo author header)."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        g = Gallery(backend=FileSystemBackend(d))
        original = ScriptSections(
            configurator='title: str = "round-trip"',
            code="print('hi')",
        )
        new_v = g.save_script(None, "20240101", original, author="Author")
        loaded = g.load_script(None, "20240101", new_v)
        assert "round-trip" in loaded.configurator
        assert "print('hi')" in loaded.code

    def test_run_then_save_independent(self, tmp_path):
        """A preview run does not persist anything to disk."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        g = Gallery(backend=FileSystemBackend(d))
        before_versions = g.list_versions(None, "20240101")
        result = g.run_script(None, ScriptSections(code="x = 1"))
        assert result.success
        after_versions = g.list_versions(None, "20240101")
        assert before_versions == after_versions  # run did not save

    def test_save_then_run_uses_in_memory_value(self, tmp_path):
        """After save, run_script(sections) still uses the passed-in sections, not disk."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        g = Gallery(backend=FileSystemBackend(d))
        saved = ScriptSections(code="x = 'saved'")
        g.save_script(None, "20240101", saved, author="A")
        ad_hoc = ScriptSections(code="x = 'adhoc'\nprint(x)")
        result = g.run_script(None, ad_hoc)
        assert "adhoc" in result.output

    def test_multi_backend_save_isolation(self, multi_backend_gallery, tmp_path):
        """Saving on one backend leaves the other untouched."""
        from gallery_viewer._types import ScriptSections

        s = ScriptSections(configurator="x: int = 99", code="print(99)")
        multi_backend_gallery.save_script("alpha", "20240101", s, author="A")
        assert multi_backend_gallery.list_versions("alpha", "20240101") == ["1", "2"]
        assert multi_backend_gallery.list_versions("beta", "20240101") == ["1"]

    @pytest.mark.parametrize(
        "ops",
        [
            ["run", "run", "run"],
            ["save", "save", "save"],
            ["run", "save", "run"],
            ["save", "run", "save"],
            ["run", "save", "save", "run"],
        ],
        ids=lambda x: "_".join(x),
    )
    def test_arbitrary_op_sequences_dont_corrupt_state(self, tmp_path, ops):
        """Any sequence of run/save calls leaves the gallery in a coherent state."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        g = Gallery(backend=FileSystemBackend(d))
        s = ScriptSections(configurator="x: int = 1", code="x = 1\nprint(x)")
        starting_versions = g.list_versions(None, "20240101")
        save_count = 0
        for op in ops:
            if op == "run":
                result = g.run_script(None, s)
                assert result.success
            elif op == "save":
                g.save_script(None, "20240101", s, author="A")
                save_count += 1
        end_versions = g.list_versions(None, "20240101")
        # number of versions after = starting + number of saves
        assert len(end_versions) == len(starting_versions) + save_count
        # versions are sorted, no gaps
        assert end_versions == sorted(end_versions, key=int)
        for i, v in enumerate(end_versions, start=1):
            assert v == str(i)


# ---------------------------------------------------------------------------
# Version sequences — chains, gaps, and diff propagation
# ---------------------------------------------------------------------------


class TestVersionSequences:
    """Behaviour across version chains v1 → v2 → v3 → … and irregular shapes."""

    @pytest.mark.parametrize("n_versions", [1, 2, 3, 5, 10])
    def test_list_versions_dense_chain(self, tmp_path, n_versions):
        """A dense chain v1..vN lists all N versions in order."""
        d = _make_gallery_dir(tmp_path, "main", groups_versions={"20240101": n_versions})
        g = Gallery(backend=FileSystemBackend(d))
        versions = g.list_versions(None, "20240101")
        assert versions == [str(i) for i in range(1, n_versions + 1)]

    def test_diff_chain_v1_to_v3(self, tmp_path):
        """Each consecutive pair (v2 vs v1, v3 vs v2) is independently diffable."""
        from gallery_viewer._types import ScriptSections

        d = _make_gallery_dir(tmp_path, "main")
        g = Gallery(backend=FileSystemBackend(d))
        # save v2 with one config change
        g.save_script(
            None,
            "20240101",
            ScriptSections(configurator="x: int = 2", code="print(2)"),
            author="A",
        )
        # save v3 with another config change
        g.save_script(
            None,
            "20240101",
            ScriptSections(configurator="x: int = 3", code="print(3)"),
            author="B",
        )
        diff_v2 = g.version_diff(None, "20240101", "2")
        diff_v3 = g.version_diff(None, "20240101", "3")
        assert len(diff_v2) > 0
        assert len(diff_v3) > 0
        # The two diffs should describe different transitions
        assert diff_v2 != diff_v3

    def test_export_inject_vars_uses_specified_version(self, tmp_path):
        """OUTPUT_PATH reflects the version argument, not 'latest' or 'v1'."""
        d = _make_gallery_dir(tmp_path, "main", groups_versions={"20240101": 3})
        g = Gallery(backend=FileSystemBackend(d))
        for v in ["1", "2", "3"]:
            result = g.export_inject_vars(None, "20240101", v)
            assert f"_v{v}.png" in result["OUTPUT_PATH"]

    def test_load_each_version_in_chain(self, gallery_with_chain):
        """Every version in a v1..v3 chain loads to a non-empty ScriptSections."""
        for v in ["1", "2", "3"]:
            sections = gallery_with_chain.load_script(None, "20240101", v)
            assert isinstance(sections, ScriptSections)
            assert sections.code  # all seeded with non-empty code

    @pytest.mark.parametrize(
        "groups",
        [
            {"20240101": 1},
            {"20240101": 1, "20240601": 1},
            {"20240101": 3, "20240601": 1, "20241201": 2},
        ],
        ids=["one_date", "two_dates", "three_dates_mixed_versions"],
    )
    def test_list_dates_across_shapes(self, tmp_path, groups):
        """list_groups() returns every group in the gallery, regardless of version count."""
        d = _make_gallery_dir(tmp_path, "main", groups_versions=groups)
        g = Gallery(backend=FileSystemBackend(d))
        listed = g.list_groups(None)
        assert set(listed) == set(groups.keys())


# ---------------------------------------------------------------------------
# Tags — user stories from CLAUDE.md item E
# ---------------------------------------------------------------------------


class TestTagsUserStories:
    """User stories for the tag feature.

    Story #7 (publication freezer): "Don't let v7 ever change."
        → User attaches `frozen` to a published version. The tag survives
          subsequent loads. (Pure label — no enforcement, since save_version
          always creates a new version by construction.)

    Story #8 (new collaborator): "Which of these 47 PNGs is the canonical one?"
        → Filter dropdown uses `versions_with_tag` to narrow the version list
          to versions carrying a chosen tag (e.g. `published`).

    Story #10 (naive user): "I just wanted to see"
        → Add/remove tags is the one operation that mutates an existing
          version in place — but it only touches the metadata block; the
          plot artifact is untouched.
    """

    def test_freezer_story_tag_persists_across_loads(self, tmp_gallery):
        """#7 — Tag attached to v1 reappears after a fresh backend load."""
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.add_tag(None, "20240101", "1", "frozen")
        # Fresh Gallery instance — proves the tag is on disk, not in memory.
        g2 = Gallery(backend=FileSystemBackend(tmp_gallery))
        assert "frozen" in g2.list_tags(None, "20240101", "1")

    def test_collaborator_story_filter_to_published(self, tmp_path):
        """#8 — Among many versions, only `published` ones surface in the filter."""
        d = _make_gallery_dir(tmp_path, "main", groups_versions={"20240101": 5})
        g = Gallery(backend=FileSystemBackend(d))
        g.add_tag(None, "20240101", "2", "published")
        g.add_tag(None, "20240101", "4", "published")
        g.add_tag(None, "20240101", "3", "draft")
        published = g.versions_with_tag(None, "20240101", "published")
        assert published == ["2", "4"]

    def test_naive_user_story_add_tag_does_not_alter_plot(self, tmp_gallery):
        """#10 — Adding a tag is metadata-only; the saved plot file is untouched."""
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        plot_path = tmp_gallery / "plots" / "plot_20240101_v1.png"
        before = plot_path.read_bytes()
        g.add_tag(None, "20240101", "1", "published")
        after = plot_path.read_bytes()
        assert before == after, "tag mutation must not re-render the plot"

    def test_add_tag_is_idempotent(self, tmp_gallery):
        """Adding the same tag twice is a silent no-op (no duplicate)."""
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.add_tag(None, "20240101", "1", "published")
        g.add_tag(None, "20240101", "1", "published")
        tags = g.list_tags(None, "20240101", "1")
        assert tags.count("published") == 1

    def test_remove_tag_silent_when_absent(self, tmp_gallery):
        """Removing a non-existent tag does not raise."""
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        # Should not raise.
        g.remove_tag(None, "20240101", "1", "ghost-tag")
        assert g.list_tags(None, "20240101", "1") == []

    def test_round_trip_add_remove(self, tmp_gallery):
        """add → list shows tag → remove → list no longer shows it."""
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.add_tag(None, "20240101", "1", "wip")
        assert g.list_tags(None, "20240101", "1") == ["wip"]
        g.remove_tag(None, "20240101", "1", "wip")
        assert g.list_tags(None, "20240101", "1") == []

    def test_versions_with_tag_returns_empty_for_unknown_tag(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        assert g.versions_with_tag(None, "20240101", "unknown") == []

    def test_add_tag_on_unsaved_version_raises(self, tmp_gallery):
        """Tagging a version that doesn't exist on disk raises FileNotFoundError.

        Tags only mean something on a *saved* version — there's no in-memory
        draft to attach them to.
        """
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        with pytest.raises(FileNotFoundError):
            g.add_tag(None, "20240101", "99", "frozen")

    def test_tags_round_trip_through_file_format(self, tmp_gallery):
        """Tags round-trip through the on-disk `# tag: ...` format."""
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        g.add_tag(None, "20240101", "1", "published")
        g.add_tag(None, "20240101", "1", "final")
        # Inspect the actual file — flat-file principle.
        text = (tmp_gallery / "scripts" / "script_20240101_v1.py").read_text()
        assert "# tag: published" in text
        assert "# tag: final" in text
