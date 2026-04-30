"""gallery-viewer — configurable versioned script gallery for Dash.

Framework-agnostic dashboard for browsing, editing, and executing versioned
data visualization scripts. Ships with a matplotlib starter template; works
with any charting library (Plotly, Altair, seaborn, etc.) that produces
PNG/JSON/CSV from a Python script.
"""

from gallery_viewer._types import OutputItem, RunResult, ScriptSections
from gallery_viewer.backend import FileSystemBackend, StorageBackend
from gallery_viewer.config import load_config, save_config
from gallery_viewer.gallery import Gallery
from gallery_viewer.params import (
    ParamSpec,
    detect_params,
    diff_configurator,
    parse_typed_assignments,
)

__all__ = [
    "Gallery",
    "StorageBackend",
    "FileSystemBackend",
    "ScriptSections",
    "RunResult",
    "OutputItem",
    "ParamSpec",
    "detect_params",
    "diff_configurator",
    "parse_typed_assignments",
    "load_config",
    "save_config",
]
