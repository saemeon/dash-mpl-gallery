"""Tests for gallery-viewer JSON config."""

import json
from pathlib import Path

import pytest

from gallery_viewer.config import (
    add_plot_to_config,
    backends_from_config,
    load_config,
    remove_plot_from_config,
    save_config,
)
from gallery_viewer.backend import FileSystemBackend


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary gallery.json."""
    config = {
        "title": "Test Gallery",
        "plots": {
            "chart_a": {"path": "./chart_a", "description": "Chart A"},
            "chart_b": {"path": "./chart_b", "description": "Chart B"},
        },
    }
    config_path = tmp_path / "gallery.json"
    with open(config_path, "w") as f:
        json.dump(config, f)

    # Create directory structure for chart_a
    (tmp_path / "chart_a" / "data").mkdir(parents=True)
    (tmp_path / "chart_a" / "scripts").mkdir(parents=True)
    (tmp_path / "chart_a" / "plots").mkdir(parents=True)
    (tmp_path / "chart_b" / "data").mkdir(parents=True)
    (tmp_path / "chart_b" / "scripts").mkdir(parents=True)
    (tmp_path / "chart_b" / "plots").mkdir(parents=True)

    return config_path


class TestLoadConfig:
    def test_load_existing(self, tmp_config):
        config = load_config(tmp_config)
        assert config["title"] == "Test Gallery"
        assert "chart_a" in config["plots"]
        assert "chart_b" in config["plots"]

    def test_load_nonexistent_returns_default(self, tmp_path):
        config = load_config(tmp_path / "missing.json")
        assert config["title"] == "Gallery Viewer"
        assert config["plots"] == {}


class TestSaveConfig:
    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "gallery.json"
        config = {"title": "Saved", "plots": {"x": {"path": "./x"}}}
        save_config(config, path)
        loaded = load_config(path)
        assert loaded["title"] == "Saved"
        assert "x" in loaded["plots"]

    def test_atomic_write(self, tmp_path):
        path = tmp_path / "gallery.json"
        save_config({"title": "v1", "plots": {}}, path)
        save_config({"title": "v2", "plots": {}}, path)
        loaded = load_config(path)
        assert loaded["title"] == "v2"


class TestBackendsFromConfig:
    def test_creates_backends(self, tmp_config):
        config = load_config(tmp_config)
        backends = backends_from_config(config, base_dir=tmp_config.parent)
        assert "chart_a" in backends
        assert "chart_b" in backends
        assert isinstance(backends["chart_a"], FileSystemBackend)

    def test_relative_paths_resolved(self, tmp_config):
        config = load_config(tmp_config)
        backends = backends_from_config(config, base_dir=tmp_config.parent)
        assert backends["chart_a"].base_dir == (tmp_config.parent / "chart_a").resolve()

    def test_empty_config(self, tmp_path):
        config = {"title": "Empty", "plots": {}}
        backends = backends_from_config(config, base_dir=tmp_path)
        assert backends == {}


class TestAddPlot:
    def test_add_creates_dirs(self, tmp_path):
        config = {"plots": {}}
        plot_path = tmp_path / "new_plot"
        add_plot_to_config(config, "new_plot", str(plot_path), description="A new plot")
        assert "new_plot" in config["plots"]
        assert (plot_path / "data").is_dir()
        assert (plot_path / "plots").is_dir()
        assert (plot_path / "scripts").is_dir()

    def test_add_without_dirs(self, tmp_path):
        config = {"plots": {}}
        plot_path = tmp_path / "nodirs"
        add_plot_to_config(config, "nodirs", str(plot_path), create_dirs=False)
        assert "nodirs" in config["plots"]
        assert not (plot_path / "data").exists()

    def test_add_preserves_existing(self, tmp_path):
        config = {"plots": {"existing": {"path": "./existing"}}}
        add_plot_to_config(config, "new", str(tmp_path / "new"))
        assert "existing" in config["plots"]
        assert "new" in config["plots"]


class TestRemovePlot:
    def test_remove(self):
        config = {"plots": {"a": {"path": "./a"}, "b": {"path": "./b"}}}
        remove_plot_from_config(config, "a")
        assert "a" not in config["plots"]
        assert "b" in config["plots"]

    def test_remove_nonexistent(self):
        config = {"plots": {"a": {"path": "./a"}}}
        remove_plot_from_config(config, "missing")
        assert "a" in config["plots"]


class TestDiscoverBackends:
    def test_discover(self, tmp_path):
        (tmp_path / "plot1" / "data").mkdir(parents=True)
        (tmp_path / "plot1" / "scripts").mkdir(parents=True)
        (tmp_path / "plot2" / "data").mkdir(parents=True)
        (tmp_path / "not_a_plot").mkdir()

        backends = FileSystemBackend.discover(tmp_path)
        assert "plot1" in backends
        assert "plot2" in backends
        assert "not_a_plot" not in backends

    def test_discover_empty(self, tmp_path):
        backends = FileSystemBackend.discover(tmp_path)
        assert backends == {}
