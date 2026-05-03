"""Shared fixtures and helpers for gallery_viewer tests.

Note: each test module may also define its own ``tmp_gallery`` fixture with a
specific scenario shape (number of groups, versions, etc.). Those local fixtures
are intentionally scenario-specific and not consolidated here. This module
holds fixtures and helpers that benefit from being shared across modules.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gallery_viewer import FileSystemBackend, ScriptSections
from gallery_viewer.gallery import Gallery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_gallery_dir(
    root: Path,
    name: str,
    *,
    dates_versions: dict[str, int] | None = None,
    with_data: bool = True,
    with_plots: bool = True,
) -> Path:
    """Create a minimal valid gallery directory under ``root/name``.

    Parameters
    ----------
    root: parent directory (typically ``tmp_path``).
    name: subdirectory name; also embedded into the script's configurator
          so multi-backend tests can verify routing by content.
    dates_versions: ``{"YYYYMMDD": n_versions}``. Default = ``{"20240101": 1}``.
    with_data: if True, write a CSV per group.
    with_plots: if True, write a fake PNG for v1 of each group.

    Returns
    -------
    The created subdirectory path.
    """
    if dates_versions is None:
        dates_versions = {"20240101": 1}

    d = root / name
    d.mkdir()
    (d / "data").mkdir()
    (d / "plots").mkdir()
    (d / "scripts").mkdir()

    for group, n_versions in dates_versions.items():
        if with_data:
            df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
            df.to_csv(d / "data" / f"data_{group}.csv", index=False)
        if with_plots:
            (d / "plots" / f"plot_{group}_v1.png").write_bytes(b"\x89PNG fake")
        for v in range(1, n_versions + 1):
            sections = ScriptSections(
                configurator=f'name: str = "{name}"\nversion: int = {v}',
                code=f"print({name!r}, {v})",
            )
            (d / "scripts" / f"script_{group}_v{v}.py").write_text(sections.to_text())

    return d


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_dir(tmp_path):
    """Factory fixture wrapping :func:`make_gallery_dir` so tests can build
    multiple gallery dirs under one ``tmp_path``."""

    def _factory(name: str, **kwargs):
        return make_gallery_dir(tmp_path, name, **kwargs)

    return _factory


@pytest.fixture
def multi_backend_gallery(tmp_path):
    """A Gallery with two FileSystemBackends ('alpha' and 'beta'), each at v1."""
    dir_a = make_gallery_dir(tmp_path, "alpha")
    dir_b = make_gallery_dir(tmp_path, "beta")
    return Gallery(
        backends={
            "alpha": FileSystemBackend(dir_a),
            "beta": FileSystemBackend(dir_b),
        }
    )


@pytest.fixture
def gallery_with_chain(tmp_path):
    """A single-backend Gallery with one group and v1, v2, v3 — for diff/chain tests."""
    d = make_gallery_dir(tmp_path, "main", dates_versions={"20240101": 3})
    return Gallery(backend=FileSystemBackend(d))


@pytest.fixture
def empty_gallery():
    """Gallery() with no backends configured — for empty-state robustness."""
    return Gallery(backends={})
