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
