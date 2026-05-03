"""Storage backend abstraction for gallery-viewer.

The ``StorageBackend`` base class defines the interface for loading and saving
versioned scripts, data, and plots.  Subclass it or override individual methods
to plug in company-specific storage (S3, database, git, ...).

``FileSystemBackend`` is the default implementation that works with a flat
directory layout::

    base_dir/
        data/   data_{group}.csv
        plots/  plot_{group}_v{version}.png
        scripts/script_{group}_v{version}.py

Script execution uses a **manifest-based capture** system: after running the
user's code, an epilogue introspects the namespace for matplotlib figures,
Plotly figures, and pandas DataFrames.  Each is serialized to a temp directory
and returned as ``OutputItem`` instances in ``RunResult.items``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from gallery_viewer._types import OutputItem, RunResult, ScriptSections


class StorageBackend:
    """Base class for gallery storage.

    Override any method to customise discovery, loading, saving, or execution.
    """

    # -- Discovery -----------------------------------------------------------

    def list_groups(self) -> list[str]:
        """Return available groups, newest first."""
        return []

    def list_versions(self, group: str) -> list[str]:
        """Return available versions for *group*, ascending."""
        return []

    # -- Loading -------------------------------------------------------------

    def load_script(self, group: str, version: str) -> ScriptSections:
        """Load script content for a given group/version."""
        return ScriptSections()

    def load_data(self, group: str) -> pd.DataFrame | None:
        """Load a data preview for *group* (may return ``None``)."""
        return None

    def load_artifact(self, group: str, version: str) -> bytes | None:
        """Load the saved artifact (e.g. image bytes) for *group*/*version*."""
        return None

    # -- Saving --------------------------------------------------------------

    def save_version(self, group: str, sections: ScriptSections) -> str:
        """Persist *sections* and return the new version identifier."""
        raise NotImplementedError

    # -- Tags ----------------------------------------------------------------
    #
    # Tag operations are the **only** path that mutates an existing saved
    # version in place — everything else (Save) creates a new version. The
    # default implementations go through ``load_script`` + a backend-specific
    # in-place writer (``_write_script``) so subclasses only need to override
    # the writer.

    def list_tags(self, group: str, version: str) -> list[str]:
        """Return tags attached to *group*/*version*, in insertion order."""
        return list(self.load_script(group, version).tags)

    def add_tag(self, group: str, version: str, tag: str) -> list[str]:
        """Attach *tag* to *group*/*version* in place. Returns the new tag list.

        Idempotent: adding an existing tag is a no-op. Whitespace is stripped.
        """
        tag = tag.strip()
        if not tag:
            return self.list_tags(group, version)
        sections = self.load_script(group, version)
        if tag in sections.tags:
            return list(sections.tags)
        sections = sections.with_tags([tag])
        self._write_script(group, version, sections)
        return list(sections.tags)

    def remove_tag(self, group: str, version: str, tag: str) -> list[str]:
        """Remove *tag* from *group*/*version* in place. Returns the new tag list.

        Silently no-ops if the tag isn't present.
        """
        sections = self.load_script(group, version)
        if tag not in sections.tags:
            return list(sections.tags)
        new_tags = [t for t in sections.tags if t != tag]
        sections = sections.with_tags(new_tags, replace=True)
        self._write_script(group, version, sections)
        return list(sections.tags)

    def versions_with_tag(self, group: str, tag: str) -> list[str]:
        """Return versions of *group* carrying *tag*, in ``list_versions`` order."""
        return [v for v in self.list_versions(group) if tag in self.list_tags(group, v)]

    def _write_script(self, group: str, version: str, sections: ScriptSections) -> None:
        """Overwrite the stored script for *group*/*version* with *sections*.

        Used by :meth:`add_tag` / :meth:`remove_tag` to mutate an existing
        version's metadata in place without re-running the script. The base
        class raises — backends that support tag editing must override.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support in-place script writes "
            "(needed for tag editing)."
        )

    # -- Execution -----------------------------------------------------------

    def run_preview(
        self,
        sections: ScriptSections,
        inject_vars: dict[str, object] | None = None,
    ) -> RunResult:
        """Run Configurator + Code, capture a preview image, return result."""
        return _run_sections(sections, include_save=False, inject_vars=inject_vars)

    def run_full(
        self,
        sections: ScriptSections,
        inject_vars: dict[str, object] | None = None,
    ) -> RunResult:
        """Run Configurator + Code + Save, return result."""
        return _run_sections(sections, include_save=True, inject_vars=inject_vars)

    def list_uncharted_groups(self) -> list[str]:
        """Return data groups that have no scripts yet, newest first."""
        return []

    # -- Templates -----------------------------------------------------------

    def template_for_group(self, group: str) -> ScriptSections:
        """Return a script template for *group*, copying from the latest existing version.

        Picks the newest prior group, then its latest version.
        Falls back to ``starter_template(group)`` if no prior versions exist.
        Override to customise how new-group templates are seeded.
        """
        for prev_group in self.list_groups():
            versions = self.list_versions(prev_group)
            if not versions:
                continue
            sections = self.load_script(prev_group, versions[-1])
            return ScriptSections(
                configurator=sections.configurator,
                code=sections.code.replace(f'"{prev_group}"', f'"{group}"'),
                save=sections.save,
            )
        return self.starter_template(group)

    def starter_template(self, group: str) -> ScriptSections:
        """Return a blank starter script for a new group (override for branding)."""
        return ScriptSections(
            code=(
                "import pandas as pd\n"
                "import matplotlib\n"
                'matplotlib.use("Agg")\n'
                "import matplotlib.pyplot as plt\n"
                "\n"
                "fig, ax = plt.subplots(figsize=(8, 5))\n"
                "# ax.plot(...)\n"
                "plt.tight_layout()"
            ),
        )

    def export_inject_vars(self, group: str, version: str) -> dict[str, str]:
        """Return path-related variables to inject into a standalone export script.

        Override in filesystem-backed implementations to provide ``BASE_DIR``
        and ``OUTPUT_PATH``.  The default returns an empty dict — non-filesystem
        backends simply omit the path variables.
        """
        return {}

    def data_hash(self, group: str) -> str | None:
        """Return a content hash of the data file for *group*, or ``None``.

        The hash is used for provenance stamping ("what data produced this
        chart?"). The default returns ``None`` — backends without an obvious
        single-file data source need not compute a hash. Filesystem-backed
        implementations should return a string like ``"sha256:abc123..."``.
        """
        return None


# ---------------------------------------------------------------------------
# Default subprocess runner (shared by all backends)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Capture epilogue — appended to every subprocess script
# ---------------------------------------------------------------------------
# After the user's CODE (and optionally SAVE) section runs, this epilogue
# scans the subprocess namespace for recognizable output types:
#   1. matplotlib figures → saved as PNG
#   2. plotly.graph_objects.Figure → serialized as JSON
#   3. pandas DataFrames (non-private) → exported as CSV (first 200 rows)
# Results are written to a temp directory with a manifest.json that the
# runner reads back into OutputItem instances.
_CAPTURE_EPILOGUE = """
import json as _json, pathlib as _pathlib

_out_dir = _pathlib.Path(r"{out_dir}")
_out_dir.mkdir(exist_ok=True)
_manifest = []

# 1. Matplotlib figures
try:
    import matplotlib.pyplot as _plt
    for _i, _fignum in enumerate(_plt.get_fignums()):
        _fig = _plt.figure(_fignum)
        _path = _out_dir / f"fig_{{_i}}.png"
        _fig.savefig(str(_path), dpi=100, bbox_inches="tight")
        _manifest.append({{"mime": "image/png", "file": _path.name}})
except ImportError:
    pass

# 2. Plotly figures
try:
    import plotly.graph_objects as _go
    for _name, _obj in list(locals().items()):
        if isinstance(_obj, _go.Figure):
            _path = _out_dir / f"plotly_{{_name}}.json"
            _path.write_text(_obj.to_json())
            _manifest.append({{"mime": "application/vnd.plotly+json", "file": _path.name}})
except ImportError:
    pass

# 3. Pandas DataFrames (non-private variables)
try:
    import pandas as _pd
    for _name, _obj in list(locals().items()):
        if isinstance(_obj, _pd.DataFrame) and not _name.startswith("_"):
            _path = _out_dir / f"df_{{_name}}.csv"
            _obj.head(200).to_csv(str(_path), index=False)
            _manifest.append({{"mime": "text/csv", "file": _path.name, "name": _name}})
except ImportError:
    pass

(_out_dir / "manifest.json").write_text(_json.dumps(_manifest))
"""


def _run_sections(
    sections: ScriptSections,
    include_save: bool,
    timeout: int = 60,
    cwd: Path | None = None,
    inject_vars: dict[str, object] | None = None,
) -> RunResult:
    """Execute script sections in a subprocess, capturing outputs."""
    out_dir = Path(tempfile.mkdtemp(prefix="gv_out_"))

    if include_save:
        code = sections.to_full(inject_vars=inject_vars)
    else:
        code = sections.to_preview(inject_vars=inject_vars)

    # Append the capture epilogue
    code += "\n\n" + _CAPTURE_EPILOGUE.format(out_dir=out_dir)

    # Write script inside cwd/scripts/ so Path(__file__).parent.parent == cwd
    script_dir = (cwd / "scripts") if cwd else Path(tempfile.gettempdir())
    script_dir.mkdir(parents=True, exist_ok=True)
    _fd, _tmp_path_str = tempfile.mkstemp(suffix=".py", dir=str(script_dir))
    tmp_path = Path(_tmp_path_str)
    with os.fdopen(_fd, "w") as _tmp:
        _tmp.write(code)

    try:
        result = subprocess.run(
            [sys.executable, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        output = result.stdout or ""
        error = result.stderr or ""
        success = result.returncode == 0
    except subprocess.TimeoutExpired:
        output = ""
        error = f"Script timed out after {timeout} seconds."
        success = False
    finally:
        tmp_path.unlink(missing_ok=True)

    # Read captured outputs from manifest
    items: list[OutputItem] = []
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            for entry in manifest:
                file_path = out_dir / entry["file"]
                if file_path.exists():
                    items.append(
                        OutputItem(mime=entry["mime"], data=file_path.read_bytes())
                    )
        except (json.JSONDecodeError, KeyError):
            pass

    # Clean up temp output directory
    shutil.rmtree(out_dir, ignore_errors=True)

    return RunResult(
        output=output.strip(),
        error=error.strip(),
        items=items,
        success=success,
    )


# ---------------------------------------------------------------------------
# FileSystemBackend
# ---------------------------------------------------------------------------


class FileSystemBackend(StorageBackend):
    """Default backend: versioned files in ``data/``, ``plots/``, ``scripts/``.

    Parameters
    ----------
    base_dir :
        Root directory containing data/, plots/, scripts/ subdirectories.
    data_pattern :
        Regex with a ``group`` named-capture for data files.
    script_pattern :
        Regex with ``group`` and ``version`` named-captures for script files.
    plot_pattern :
        Regex with ``group`` and ``version`` named-captures for plot files.
    starter_template_fn :
        Optional callable ``(group, base_dir) -> ScriptSections`` for custom
        script templates.
    """

    def __init__(
        self,
        base_dir: str | Path = ".",
        data_pattern: str = r"data_(?P<group>[^.]+?)\.(csv|parquet)$",
        script_pattern: str = r"script_(?P<group>.+?)_v(?P<version>\d+)\.py$",
        plot_pattern: str = r"plot_(?P<group>.+?)_v(?P<version>\d+)\.png$",
        starter_template_fn: Callable[[str, Path], ScriptSections] | None = None,
    ):
        self.base_dir = Path(base_dir).resolve()
        self.data_dir = self.base_dir / "data"
        self.artifacts_dir = self.base_dir / "plots"
        self.scripts_dir = self.base_dir / "scripts"

        self._data_re = re.compile(data_pattern)
        self._script_re = re.compile(script_pattern)
        self._plot_re = re.compile(plot_pattern)
        self._starter_template_fn = starter_template_fn

    @classmethod
    def discover(
        cls,
        base_dir: str | Path,
        **kwargs,
    ) -> dict[str, FileSystemBackend]:
        """Auto-discover sub-plots from a directory.

        Each subdirectory of *base_dir* that contains a ``data/`` or
        ``scripts/`` folder is treated as a separate plot.  Returns a dict
        mapping plot name → backend.

        Parameters
        ----------
        base_dir :
            Parent directory to scan.
        **kwargs :
            Extra arguments forwarded to each ``FileSystemBackend()``.
        """
        base = Path(base_dir).resolve()
        backends: dict[str, FileSystemBackend] = {}
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if (child / "data").is_dir() or (child / "scripts").is_dir():
                backends[child.name] = cls(child, **kwargs)
        return backends

    # -- Discovery -----------------------------------------------------------

    def list_groups(self) -> list[str]:
        groups: set[str] = set()
        if self.data_dir.exists():
            for f in self.data_dir.iterdir():
                m = self._data_re.match(f.name)
                if m:
                    groups.add(m.group("group"))
        if self.scripts_dir.exists():
            for f in self.scripts_dir.iterdir():
                m = self._script_re.match(f.name)
                if m:
                    groups.add(m.group("group"))
        return sorted(groups, reverse=True)

    def list_versions(self, group: str) -> list[str]:
        versions: list[int] = []
        if self.scripts_dir.exists():
            for f in self.scripts_dir.iterdir():
                m = self._script_re.match(f.name)
                if m and m.group("group") == group:
                    versions.append(int(m.group("version")))
        return [str(v) for v in sorted(versions)] or ["1"]

    # -- Loading -------------------------------------------------------------

    def load_script(self, group: str, version: str) -> ScriptSections:
        path = self.scripts_dir / f"script_{group}_v{version}.py"
        if path.exists():
            return ScriptSections.from_text(path.read_text())
        return self.starter_template(group)

    def load_data(self, group: str) -> pd.DataFrame | None:
        for ext in ("csv", "parquet"):
            p = self.data_dir / f"data_{group}.{ext}"
            if p.exists():
                return pd.read_parquet(p) if ext == "parquet" else pd.read_csv(p)
        return None

    def load_artifact(self, group: str, version: str) -> bytes | None:
        path = self.artifacts_dir / f"plot_{group}_v{version}.png"
        if path.exists():
            return path.read_bytes()
        return None

    # -- Saving --------------------------------------------------------------

    def save_version(self, group: str, sections: ScriptSections) -> str:
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        existing = []
        if self.scripts_dir.exists():
            for f in self.scripts_dir.iterdir():
                m = self._script_re.match(f.name)
                if m and m.group("group") == group:
                    existing.append(int(m.group("version")))
        new_version = max(existing, default=0) + 1

        # Save the script as-is (clean, no patching)
        path = self.scripts_dir / f"script_{group}_v{new_version}.py"
        path.write_text(sections.to_text())

        # Inject group/version/paths as execution-time variables
        plot_path = self.artifacts_dir / f"plot_{group}_v{new_version}.png"
        inject = {
            "group": group,
            "version": new_version,
            "BASE_DIR": str(self.base_dir),
            "OUTPUT_PATH": str(plot_path),
        }

        result = self.run_full(sections, inject_vars=inject)

        if not plot_path.exists() and result.image_bytes:
            plot_path.write_bytes(result.image_bytes)

        return str(new_version)

    # -- In-place writes (for tag edits) ------------------------------------

    def _write_script(self, group: str, version: str, sections: ScriptSections) -> None:
        """Overwrite the stored script file with *sections*.

        Does **not** re-run the script — used only for metadata-only mutations
        like adding/removing tags. The plot artifact is left untouched, since
        tags are pure labels and don't change script output.
        """
        path = self.scripts_dir / f"script_{group}_v{version}.py"
        if not path.exists():
            raise FileNotFoundError(f"No saved script for {group}/v{version} at {path}")
        path.write_text(sections.to_text())

    # -- Execution (override to set cwd) ------------------------------------

    def run_preview(
        self,
        sections: ScriptSections,
        inject_vars: dict[str, object] | None = None,
    ) -> RunResult:
        return _run_sections(
            sections, include_save=False, cwd=self.base_dir, inject_vars=inject_vars
        )

    def run_full(
        self,
        sections: ScriptSections,
        inject_vars: dict[str, object] | None = None,
    ) -> RunResult:
        return _run_sections(
            sections, include_save=True, cwd=self.base_dir, inject_vars=inject_vars
        )

    def list_uncharted_groups(self) -> list[str]:
        data_groups: set[str] = set()
        if self.data_dir.exists():
            for f in self.data_dir.iterdir():
                m = self._data_re.match(f.name)
                if m:
                    data_groups.add(m.group("group"))
        script_groups: set[str] = set()
        if self.scripts_dir.exists():
            for f in self.scripts_dir.iterdir():
                m = self._script_re.match(f.name)
                if m:
                    script_groups.add(m.group("group"))
        return sorted(data_groups - script_groups, reverse=True)

    # -- Templates -----------------------------------------------------------

    def export_inject_vars(self, group: str, version: str) -> dict[str, str]:
        return {
            "BASE_DIR": str(self.base_dir),
            "OUTPUT_PATH": str(self.artifacts_dir / f"plot_{group}_v{version}.png"),
        }

    def data_hash(self, group: str) -> str | None:
        """Return ``"sha256:<hex>"`` of the data file for *group*, or ``None``.

        Looks for ``data/data_{group}.csv`` then ``data/data_{group}.parquet``.
        Returns ``None`` if neither exists.
        """
        import hashlib

        for ext in ("csv", "parquet"):
            p = self.data_dir / f"data_{group}.{ext}"
            if p.exists():
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                return f"sha256:{h}"
        return None

    def starter_template(self, group: str) -> ScriptSections:
        if self._starter_template_fn is not None:
            return self._starter_template_fn(group, self.base_dir)

        data_path = self.data_dir / f"data_{group}.csv"
        return ScriptSections(
            configurator=(f'title: str = "{group}"\ndpi: int = 100'),
            code=(
                "import pandas as pd\n"
                "import matplotlib\n"
                'matplotlib.use("Agg")\n'
                "import matplotlib.pyplot as plt\n"
                "from pathlib import Path\n"
                "\n"
                f'BASE_DIR = Path(r"{self.base_dir}")\n'
                f'group = "{group}"\n'
                "\n"
                f'df = pd.read_csv(r"{data_path}")\n'
                "\n"
                "fig, ax = plt.subplots(figsize=(8, 5))\n"
                "ax.plot(df.iloc[:, 0], df.iloc[:, 1], marker='o', linewidth=2)\n"
                "ax.set_title(title)\n"
                "ax.set_xlabel(df.columns[0])\n"
                "ax.set_ylabel(df.columns[1])\n"
                "ax.grid(True, alpha=0.3)\n"
                "plt.tight_layout()"
            ),
            save=(
                "# The gallery injects: group, version, BASE_DIR, OUTPUT_PATH\n"
                "# Add optional post-processing here (e.g. extra exports).\n"
                "# The plot image is saved automatically by the gallery."
            ),
        )
