"""Tests for the Gallery dashboard builder."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gallery_viewer import FileSystemBackend, ScriptSections
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
        assert g._multi is True

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
        from gallery_viewer.gallery import _diff_configurator

        old = 'title: str = "old"\ndpi: int = 100'
        new = 'title: str = "new"\ndpi: int = 100'
        diff = _diff_configurator(old, new)
        assert len(diff) == 1
        assert "'old'" in diff[0] and "'new'" in diff[0]

    def test_no_changes(self):
        from gallery_viewer.gallery import _diff_configurator

        source = 'title: str = "same"'
        assert _diff_configurator(source, source) == []

    def test_added_param(self):
        from gallery_viewer.gallery import _diff_configurator

        old = 'title: str = "x"'
        new = 'title: str = "x"\ndpi: int = 150'
        diff = _diff_configurator(old, new)
        assert any("+dpi" in d for d in diff)

    def test_removed_param(self):
        from gallery_viewer.gallery import _diff_configurator

        old = 'title: str = "x"\ndpi: int = 150'
        new = 'title: str = "x"'
        diff = _diff_configurator(old, new)
        assert any("-dpi" in d for d in diff)

    def test_multiple_changes(self):
        from gallery_viewer.gallery import _diff_configurator

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
# Feature 3: New Date button + Feature 4: Copy from version
# ---------------------------------------------------------------------------


class TestNewDate:
    def test_new_date_btn_present(self, tmp_gallery):
        backend = FileSystemBackend(tmp_gallery)
        g = Gallery(backend=backend)
        layout_str = str(g.app.layout)
        assert "gv-new-date-btn" in layout_str

    def test_find_uncharted_dates(self, tmp_path):
        from gallery_viewer.gallery import _find_uncharted_dates

        (tmp_path / "data").mkdir()
        (tmp_path / "scripts").mkdir()
        # Data for two dates, scripts for only one
        pd.DataFrame({"x": [1]}).to_csv(
            tmp_path / "data" / "data_20240101.csv", index=False
        )
        pd.DataFrame({"x": [1]}).to_csv(
            tmp_path / "data" / "data_20240601.csv", index=False
        )
        script = ScriptSections(code="print('hi')")
        (tmp_path / "scripts" / "script_20240101_v1.py").write_text(script.to_text())

        backend = FileSystemBackend(tmp_path)
        uncharted = _find_uncharted_dates(backend)
        assert uncharted == ["20240601"]

    def test_find_uncharted_dates_all_charted(self, tmp_gallery):
        from gallery_viewer.gallery import _find_uncharted_dates

        backend = FileSystemBackend(tmp_gallery)
        uncharted = _find_uncharted_dates(backend)
        assert uncharted == []

    def test_template_from_latest(self, tmp_gallery):
        from gallery_viewer.gallery import _template_from_latest

        backend = FileSystemBackend(tmp_gallery)
        template = _template_from_latest(backend, "20240601")
        # Should copy from 20240101 v1 and replace the date
        assert "20240601" in template.code or template.configurator != ""

    def test_template_from_latest_fallback(self, tmp_path):
        from gallery_viewer.gallery import _template_from_latest

        (tmp_path / "data").mkdir()
        (tmp_path / "scripts").mkdir()
        backend = FileSystemBackend(tmp_path)
        template = _template_from_latest(backend, "20240101")
        # Should fall back to starter template
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
        from gallery_viewer.gallery import _add_author_comment

        sections = ScriptSections(
            configurator='title: str = "test"', code="print('hi')"
        )
        result = _add_author_comment(sections, "Alice")
        assert "# Saved by: Alice" in result.configurator
        assert result.code == sections.code

    def test_add_author_comment_no_configurator(self):
        from gallery_viewer.gallery import _add_author_comment

        sections = ScriptSections(code="print('hi')")
        result = _add_author_comment(sections, "Bob")
        assert "# Saved by: Bob" in result.code
        assert result.configurator == ""


# ---------------------------------------------------------------------------
# Internal helpers
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

    def test_build_plot_names(self, tmp_path):
        b1 = FileSystemBackend(tmp_path)
        b2 = FileSystemBackend(tmp_path)
        g = Gallery(backends={"x": b1, "y": b2})
        assert g._build_plot_names() == ["x", "y"]
