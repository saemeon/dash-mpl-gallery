# Architecture

## Three-section script model

Every gallery script is split into three sections, delimited by markers:

```python
# === CONFIGURATOR ===
title: str = "Q4 Revenue"
show_target: bool = True
dpi: int = 150

# === CODE ===
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot(df["x"], df["y"])
ax.set_title(title)

# === SAVE ===
# Optional post-processing (gallery handles plot saving automatically)
```

| Section | Purpose | When it runs |
|---------|---------|-------------|
| **CONFIGURATOR** | Typed variable assignments rendered as form fields | Always (before CODE) |
| **CODE** | Main script: imports, data loading, plotting | RUN and SAVE |
| **SAVE** | Optional post-processing (extra exports, prints) | SAVE only |

**RUN** = CONFIGURATOR + CODE (preview, nothing saved to disk)

**Save Version** = CONFIGURATOR + CODE + SAVE (persisted to disk)

## Multi-output capture

After the script runs, the gallery appends a **capture epilogue** that scans the subprocess namespace:

| Output type | Detection | Rendering |
|------------|-----------|-----------|
| matplotlib figure | Any open `plt` figure | PNG image |
| Plotly figure | `plotly.graph_objects.Figure` instance | Interactive `dcc.Graph` |
| pandas DataFrame | Non-private DataFrame variables | Data table |

Multiple outputs render stacked in the preview panel. A single script can produce two charts and a summary table.

## Execution model

```
User clicks RUN
  |
  +-- Parse editor text into ScriptSections
  +-- Inject form field values (at execution time, NOT in the editor)
  +-- Write to temp .py file
  +-- subprocess.run(python, temp_file, timeout=60s)
  +-- Capture epilogue scans namespace -> writes manifest.json
  +-- Runner reads manifest -> list[OutputItem]
  +-- Gallery renders OutputItems as Dash components
```

Key design decisions:

- **The editor is the source of truth.** RUN never modifies the editor text.
- **Form values are injected at execution time** as prepended variable assignments.
- **Save uses the selected date**, not today's date.
- **Saved scripts are clean** -- no injected date/version/path variables in the file.

## Date / version model

```
my_project/
  data/
    data_20260101.csv      # January data release
    data_20260325.csv      # March data release
  scripts/
    script_20260101_v1.py  # Author's initial version
    script_20260101_v2.py  # Reviewer fixed the title
    script_20260325_v1.py  # New data, same script structure
  plots/
    plot_20260101_v1.png
    plot_20260101_v2.png
    plot_20260325_v1.png
```

- **Date** = which data release the chart is based on.
- **Version** = iterations on the chart for that data release. Append-only.
- **Save** always creates the next version for the selected date.

## Backend abstraction

```python
class StorageBackend:
    def list_dates(self) -> list[str]: ...
    def list_versions(self, date: str) -> list[str]: ...
    def load_script(self, date, version) -> ScriptSections: ...
    def load_data(self, date) -> DataFrame | None: ...
    def load_plot(self, date, version) -> bytes | None: ...
    def save_version(self, date, sections) -> str: ...
    def run_preview(self, sections, inject_vars=None) -> RunResult: ...
    def run_full(self, sections, inject_vars=None) -> RunResult: ...
```

`FileSystemBackend` is the default. Subclass `StorageBackend` for S3, databases, or git-backed storage.

## Gallery config

Multi-plot galleries use a `gallery.json`:

```json
{
  "title": "My Gallery",
  "plots": {
    "revenue": {"path": "./revenue", "description": "Quarterly revenue"},
    "inflation": {"path": "./inflation", "description": "CPI tracking"}
  }
}
```

The dashboard reads and writes this file (e.g. when adding plots via the UI).
