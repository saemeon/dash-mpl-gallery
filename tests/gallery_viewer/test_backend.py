"""Tests for gallery-viewer storage backends."""

from __future__ import annotations

import pandas as pd
import pytest

from gallery_viewer import FileSystemBackend, OutputItem, ScriptSections, StorageBackend
from gallery_viewer._types import RunResult


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
        original = ScriptSections(configurator="x: int = 1", code="print(x)")
        restored = ScriptSections.from_text(original.to_text())
        assert restored.configurator == original.configurator
        assert restored.code == original.code

    def test_with_params_replaces_values(self):
        s = ScriptSections(configurator='title: str = "old"\ndpi: int = 100', code="pass")
        result = s.with_params({"title": "new", "dpi": 150})
        assert 'title: str = "new"' in result.configurator
        assert "dpi: int = 150" in result.configurator
        assert result.code == "pass"

    def test_with_params_unknown_name_ignored(self):
        s = ScriptSections(configurator='title: str = "x"', code="pass")
        result = s.with_params({"unknown": "y"})
        assert result.configurator == s.configurator

    def test_with_params_empty_configurator_returns_self(self):
        s = ScriptSections(code="pass")
        result = s.with_params({"title": "x"})
        assert result is s

    def test_with_params_empty_dict_returns_self(self):
        s = ScriptSections(configurator='title: str = "x"', code="pass")
        result = s.with_params({})
        assert result is s


# ---------------------------------------------------------------------------
# StorageBackend (base)
# ---------------------------------------------------------------------------


class TestOutputItem:
    def test_basic(self):
        item = OutputItem(mime="image/png", data=b"\x89PNG")
        assert item.mime == "image/png"
        assert item.data == b"\x89PNG"


class TestRunResult:
    def test_image_bytes_from_items(self):
        items = [
            OutputItem(mime="text/csv", data=b"x,y\n1,2"),
            OutputItem(mime="image/png", data=b"\x89PNG fake"),
        ]
        result = RunResult(items=items)
        assert result.image_bytes == b"\x89PNG fake"

    def test_image_bytes_none_when_no_images(self):
        items = [OutputItem(mime="text/csv", data=b"x,y\n1,2")]
        result = RunResult(items=items)
        assert result.image_bytes is None

    def test_image_bytes_none_when_empty(self):
        result = RunResult()
        assert result.image_bytes is None

    def test_image_bytes_first_image(self):
        items = [
            OutputItem(mime="image/png", data=b"first"),
            OutputItem(mime="image/png", data=b"second"),
        ]
        result = RunResult(items=items)
        assert result.image_bytes == b"first"


class TestScriptSectionsInjectVars:
    def test_to_preview_with_inject(self):
        s = ScriptSections(configurator='title: str = "old"', code="print(title)")
        code = s.to_preview(inject_vars={"title": "new"})
        assert "title = 'new'" in code
        # injected vars come before configurator
        assert code.index("title = 'new'") < code.index('title: str = "old"')

    def test_to_full_with_inject(self):
        s = ScriptSections(code="print(x)", save="print('saved')")
        code = s.to_full(inject_vars={"x": 42})
        assert "x = 42" in code
        assert "print('saved')" in code

    def test_to_preview_without_inject(self):
        s = ScriptSections(code="print('hi')")
        code = s.to_preview()
        assert code == "print('hi')"

    def test_inject_bool(self):
        s = ScriptSections(code="print(flag)")
        code = s.to_preview(inject_vars={"flag": True})
        assert "flag = True" in code

    def test_inject_int(self):
        s = ScriptSections(code="print(n)")
        code = s.to_preview(inject_vars={"n": 150})
        assert "n = 150" in code


class TestStorageBackendBase:
    def test_defaults_return_empty(self):
        b = StorageBackend()
        assert b.list_dates() == []
        assert b.list_versions("x") == []
        assert b.load_data("x") is None
        assert b.load_artifact("x", "1") is None

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

    def test_list_dates_includes_script_only_dates(self, tmp_gallery):
        """Dates with scripts but no data files should appear."""
        script = ScriptSections(code="print('hello')")
        (tmp_gallery / "scripts" / "script_20241225_v1.py").write_text(script.to_text())
        b = FileSystemBackend(tmp_gallery)
        dates = b.list_dates()
        assert "20241225" in dates

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

    def test_load_artifact(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        data = b.load_artifact("20240101", "1")
        assert data is not None
        assert data.startswith(b"\x89PNG")

    def test_load_artifact_missing(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        assert b.load_artifact("20240101", "99") is None

    def test_save_version(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            configurator='title: str = "test"',
            code=(
                "import matplotlib\nmatplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\nax.plot([1,2,3])"
            ),
        )
        save_date = "20240101"
        v = b.save_version(save_date, sections)
        assert v == "3"  # v1 and v2 already exist for 20240101
        # saved script file exists
        path = tmp_gallery / "scripts" / f"script_{save_date}_v3.py"
        assert path.exists()
        # saved script is clean (no patched date/version lines)
        script_text = path.read_text()
        assert script_text.count("date =") == 0  # no injected date
        assert script_text.count("version =") == 0  # no injected version
        # saved plot file exists
        plot_path = tmp_gallery / "plots" / f"plot_{save_date}_v3.png"
        assert plot_path.exists()
        # save again → v4
        v2 = b.save_version(save_date, sections)
        assert v2 == "4"

    def test_save_version_uses_provided_date(self, tmp_gallery):
        """Save should use the date passed in, not today's date."""
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            code=(
                "import matplotlib\nmatplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\nax.plot([1,2,3])"
            ),
        )
        v = b.save_version("20991231", sections)
        assert v == "1"
        assert (tmp_gallery / "scripts" / "script_20991231_v1.py").exists()

    def test_custom_starter_template(self, tmp_gallery):
        def my_template(date, base_dir):
            return ScriptSections(
                configurator="custom_var: str = 'x'", code="print('custom')"
            )

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
        assert result.image_bytes is not None
        assert result.image_bytes[:4] == b"\x89PNG"

    def test_run_preview_captures_items(self, tmp_gallery):
        """run_preview should populate result.items with OutputItem objects."""
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            code="import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot([1,2,3])",
        )
        result = b.run_preview(sections)
        assert result.success
        assert len(result.items) >= 1
        assert result.items[0].mime == "image/png"
        assert result.items[0].data[:4] == b"\x89PNG"

    def test_run_preview_multiple_figures(self, tmp_gallery):
        """Multiple matplotlib figures should produce multiple items."""
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            code=(
                "import matplotlib\nmatplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "fig1, ax1 = plt.subplots()\nax1.plot([1,2,3])\n"
                "fig2, ax2 = plt.subplots()\nax2.bar([1,2,3], [4,5,6])\n"
            ),
        )
        result = b.run_preview(sections)
        assert result.success
        png_items = [i for i in result.items if i.mime == "image/png"]
        assert len(png_items) == 2

    def test_run_preview_dataframe_capture(self, tmp_gallery):
        """DataFrames should be captured as text/csv items."""
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            code="import pandas as pd\nsummary = pd.DataFrame({'a': [1,2], 'b': [3,4]})\n",
        )
        result = b.run_preview(sections)
        assert result.success
        csv_items = [i for i in result.items if i.mime == "text/csv"]
        assert len(csv_items) >= 1
        assert b"a,b" in csv_items[0].data

    def test_run_preview_error(self, tmp_gallery):
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(code="raise ValueError('boom')\n")
        result = b.run_preview(sections)
        assert not result.success
        assert "boom" in result.error

    def test_save_version_only_one_subprocess(self, tmp_gallery):
        """save_version must not run the script twice."""
        b = FileSystemBackend(tmp_gallery)
        sections = ScriptSections(
            code=(
                "import matplotlib\nmatplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "fig, ax = plt.subplots()\nax.plot([1, 2], [3, 4])\n"
            ),
        )
        run_full_calls = []
        run_preview_calls = []
        original_run_full = b.run_full
        original_run_preview = b.run_preview

        def counting_run_full(s, inject_vars=None):
            run_full_calls.append(1)
            return original_run_full(s, inject_vars=inject_vars)

        def counting_run_preview(s, inject_vars=None):
            run_preview_calls.append(1)
            return original_run_preview(s, inject_vars=inject_vars)

        b.run_full = counting_run_full
        b.run_preview = counting_run_preview

        b.save_version("20240101", sections)

        assert len(run_full_calls) == 1
        assert len(run_preview_calls) == 0

    def test_template_for_date_uses_latest_version(self, tmp_gallery):
        """template_for_date picks the latest version of the most recent date."""
        b = FileSystemBackend(tmp_gallery)
        # Fixture has 20240601/v1 and 20240101/v1,v2 — newest date is 20240601
        template = b.template_for_date("20250101")
        # Should be based on 20240601/v1 (newest date)
        assert isinstance(template, ScriptSections)

    def test_template_for_date_replaces_date_string(self, tmp_gallery):
        """template_for_date substitutes the old date literal with the new one."""
        b = FileSystemBackend(tmp_gallery)
        # Write a script whose code contains the source date as a string literal
        script = ScriptSections(
            configurator='title: str = "chart"',
            code='date = "20240601"\nprint(date)',
        )
        (tmp_gallery / "scripts" / "script_20240601_v2.py").write_text(script.to_text())

        template = b.template_for_date("20250601")
        assert '"20250601"' in template.code
        assert '"20240601"' not in template.code

    def test_template_for_date_no_prior_versions(self, tmp_path):
        """template_for_date falls back to starter_template when no dates exist."""
        b = FileSystemBackend(tmp_path)
        template = b.template_for_date("20250101")
        assert "matplotlib" in template.code


# ---------------------------------------------------------------------------
# Subclassing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FileSystemBackend edge cases
# ---------------------------------------------------------------------------


class TestFileSystemBackendEdge:
    def test_list_dates_empty_dir(self, tmp_path):
        """list_dates on a fresh directory returns []."""
        b = FileSystemBackend(tmp_path)
        assert b.list_dates() == []

    def test_list_versions_missing_date_returns_default(self, tmp_path):
        """list_versions for a date with no scripts returns ['1'] as the default start."""
        b = FileSystemBackend(tmp_path)
        assert b.list_versions("99991231") == ["1"]

    def test_list_uncharted_dates_no_data(self, tmp_path):
        """list_uncharted_dates with no data files returns []."""
        b = FileSystemBackend(tmp_path)
        assert b.list_uncharted_dates() == []

    def test_list_uncharted_dates_all_charted(self, tmp_gallery):
        """list_uncharted_dates returns [] when every data date has a script."""
        b = FileSystemBackend(tmp_gallery)
        # fixture has data for 20240101 and 20240601, scripts for both
        uncharted = b.list_uncharted_dates()
        assert "20240101" not in uncharted
        assert "20240601" not in uncharted

    def test_load_artifact_missing_returns_none(self, tmp_path):
        """load_artifact for a nonexistent file returns None, no exception."""
        b = FileSystemBackend(tmp_path)
        assert b.load_artifact("20991231", "9") is None


# ---------------------------------------------------------------------------
# export_inject_vars
# ---------------------------------------------------------------------------


class TestExportInjectVars:
    def test_base_backend_returns_empty(self):
        """StorageBackend base implementation returns {} — no filesystem paths."""
        b = StorageBackend()
        assert b.export_inject_vars("20240101", "1") == {}

    def test_filesystem_backend_returns_base_dir(self, tmp_path):
        """FileSystemBackend returns BASE_DIR matching its root directory."""
        b = FileSystemBackend(tmp_path)
        result = b.export_inject_vars("20240101", "3")
        assert result["BASE_DIR"] == str(tmp_path)

    def test_filesystem_backend_returns_output_path(self, tmp_path):
        """FileSystemBackend OUTPUT_PATH encodes date and version."""
        b = FileSystemBackend(tmp_path)
        result = b.export_inject_vars("20240101", "3")
        assert "plot_20240101_v3.png" in result["OUTPUT_PATH"]

    def test_filesystem_output_path_under_artifacts_dir(self, tmp_path):
        """OUTPUT_PATH sits inside the backend's artifacts directory."""
        from pathlib import Path

        b = FileSystemBackend(tmp_path)
        result = b.export_inject_vars("20240601", "7")
        assert Path(result["OUTPUT_PATH"]).parent == b.artifacts_dir

    def test_path_strings_are_str_not_path(self, tmp_path):
        """Both values must be plain strings (they get baked into source code)."""
        b = FileSystemBackend(tmp_path)
        result = b.export_inject_vars("20240101", "1")
        assert isinstance(result["BASE_DIR"], str)
        assert isinstance(result["OUTPUT_PATH"], str)


class TestSubclassing:
    def test_override_single_method(self, tmp_gallery):
        class MyBackend(FileSystemBackend):
            def list_dates(self):
                return ["custom_date"]

        b = MyBackend(tmp_gallery)
        assert b.list_dates() == ["custom_date"]
        # other methods still work
        assert b.load_data("20240101") is not None
