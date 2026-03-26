"""Tests for gallery-viewer storage backends."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from gallery_viewer import FileSystemBackend, ScriptSections, StorageBackend


@pytest.fixture
def tmp_gallery(tmp_path):
    """Create a minimal gallery directory structure."""
    (tmp_path / "data").mkdir()
    (tmp_path / "plots").mkdir()
    (tmp_path / "scripts").mkdir()

    # Create data files
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    df.to_csv(tmp_path / "data" / "data_20240101.csv", index=False)
    df.to_csv(tmp_path / "data" / "data_20240601.csv", index=False)

    # Create scripts
    script = ScriptSections(
        configurator='title: str = "test"',
        code="import pandas as pd\nprint('hello')",
    )
    (tmp_path / "scripts" / "script_20240101_v1.py").write_text(script.to_text())
    (tmp_path / "scripts" / "script_20240101_v2.py").write_text(script.to_text())
    (tmp_path / "scripts" / "script_20240601_v1.py").write_text(script.to_text())

    # Create a plot
    (tmp_path / "plots" / "plot_20240101_v1.png").write_bytes(b"\x89PNG fake")

    return tmp_path


# ---------------------------------------------------------------------------
# ScriptSections
# ---------------------------------------------------------------------------

class TestScriptSections:
    def test_from_text_with_new_markers(self):
        text = '# === CONFIGURATOR ===\ntitle: str = "hi"\n\n# === CODE ===\nprint(title)\n'
        s = ScriptSections.from_text(text)
        assert s.configurator == 'title: str = "hi"'
        assert s.code == "print(title)"

    def test_from_text_legacy_markers(self):
        text = "# === LOAD ===\nload code\n\n# === PLOT ===\nplot code\n\n# === SAVE ===\nsave code\n"
        s = ScriptSections.from_text(text)
        assert "load code" in s.code
        assert "plot code" in s.code
        assert "save code" in s.save
        assert s.configurator == ""

    def test_from_text_without_markers(self):
        s = ScriptSections.from_text("just some code")
        assert s.configurator == ""
        assert s.code == "just some code"

    def test_roundtrip(self):
        original = ScriptSections(configurator='x: int = 1', code="print(x)")
        restored = ScriptSections.from_text(original.to_text())
        assert restored.configurator == original.configurator
        assert restored.code == original.code


# ---------------------------------------------------------------------------
# StorageBackend (base)
# ---------------------------------------------------------------------------

class TestStorageBackendBase:
    def test_defaults_return_empty(self):
        b = StorageBackend()
        assert b.list_dates() == []
        assert b.list_versions("x") == []
        assert b.load_data("x") is None
        assert b.load_plot("x", "1") is None

    def test_save_not_implemented(self):
        with pytest.raises(NotImplementedError):
            StorageBackend().save_version("x", ScriptSections())


# ---------------------------------------------------------------------------
# FileSystemBackend
# ---------------------------------------------------------------------------

class TestFileSystemBackend:
    def test_list_dates(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        dates = b.list_dates()
        assert dates == ["20240601", "20240101"]

    def test_list_versions(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        assert b.list_versions("20240101") == ["1", "2"]
        assert b.list_versions("20240601") == ["1"]

    def test_list_versions_nonexistent(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        assert b.list_versions("99991231") == ["1"]  # default

    def test_load_script(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        s = b.load_script("20240101", "1")
        assert "title" in s.configurator
        assert "pandas" in s.code

    def test_load_script_fallback_to_template(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        s = b.load_script("20240601", "99")
        assert "plt" in s.code  # starter template

    def test_load_data(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        df = b.load_data("20240101")
        assert df is not None
        assert list(df.columns) == ["x", "y"]
        assert len(df) == 3

    def test_load_data_missing(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        assert b.load_data("99991231") is None

    def test_load_plot(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        data = b.load_plot("20240101", "1")
        assert data is not None
        assert data.startswith(b"\x89PNG")

    def test_load_plot_missing(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        assert b.load_plot("20240101", "99") is None

    def test_save_version(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            configurator='title: str = "test"',
            code=(
                "import matplotlib\nmatplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\nax.plot([1,2,3])\n"
                "version = 1\ndate = '20240101'"
            ),
        )
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        v = b.save_version(today, sections)
        assert v == "1"
        # saved script file exists
        path = tmp_gallery / "scripts" / f"script_{today}_v1.py"
        assert path.exists()
        # saved plot file exists
        plot_path = tmp_gallery / "plots" / f"plot_{today}_v1.png"
        assert plot_path.exists()
        # save again → v2
        v2 = b.save_version(today, sections)
        assert v2 == "2"

    def test_custom_starter_template(self, tmp_gallery):
        def my_template(date, base_dir):
            return ScriptSections(configurator="custom_var: str = 'x'", code="print('custom')")

        b = FileSystemBackend(tmp_gallery, starter_template_fn=my_template)
        s = b.load_script("99991231", "1")
        assert s.configurator == "custom_var: str = 'x'"

    def test_run_preview(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            code="import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot([1,2,3])",
        )
        result = b.run_preview(sections)
        assert result.success
        assert result.plot_bytes is not None
        assert result.plot_bytes[:4] == b"\x89PNG"

    def test_run_preview_error(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(code="raise ValueError('boom')\n")
        result = b.run_preview(sections)
        assert not result.success
        assert "boom" in result.error


# ---------------------------------------------------------------------------
# Subclassing
# ---------------------------------------------------------------------------

class TestSubclassing:
    def test_override_single_method(self, tmp_gallery):
        class MyBackend(FileSystemBackend):
            def list_dates(self):
                return ["custom_date"]

        b = MyBackend(tmp_gallery)
        assert b.list_dates() == ["custom_date"]
        # other methods still work
        assert b.load_data("20240101") is not None
