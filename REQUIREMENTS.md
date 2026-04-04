# gallery-viewer — Requirements

## What is it?

A generic, configurable dashboard for browsing, editing, and running versioned data visualization scripts. Built on Dash, designed so that any company can wrap it with their own corporate design and storage backend.

Supports multiple output types (matplotlib, Plotly, DataFrames) from a single script, auto-detected at runtime.

## How it fits in the ecosystem

```
gallery-viewer (generic engine)
    |
    |-- used by --> corpframe.gallery (company wrapper)
    |                   |-- uses --> corpframe (corporate design)
    |                   |-- uses --> dash-capture (optional export)
    |
    |-- depends on --> dash, dash-bootstrap-components, pandas
    |-- optional ----> dash-ace (syntax highlighting)
    |-- optional ----> plotly (interactive chart rendering)
```

The gallery-viewer does NOT know about corporate design, capture pipelines, or Shiny. It only knows about backends, scripts, and outputs.

## Core concepts

- **Plot**: A named collection of versioned scripts, data files, and output images.
- **Backend**: Pluggable storage layer (filesystem, S3, database, git...).
- **Script**: A Python file with three sections — Configurator (typed parameters), Code (the logic), Save (optional post-processing).
- **Output**: Anything the script produces — matplotlib figures (PNG), Plotly figures (interactive), DataFrames (tables). Auto-detected by the capture epilogue.
- **gallery.json**: Config file listing available plots. The dashboard reads and writes it.

## User stories

### Chart reviewer

> As a reviewer, I want to open the dashboard, see the latest chart, tweak the title via a form field, hit RUN to preview, and Save Version — without editing Python code or understanding file paths.

### Chart author

> As the script maintainer, I want to write a matplotlib or Plotly script, expose configurable parameters via typed assignments, and have the gallery auto-generate form fields and render outputs — for any combination of figures, tables, and text.

### Team lead

> As a team lead, I want to add a new plot type to the gallery from the dashboard (click "+ Add Plot", give it a name) — without touching config files or creating folders manually.

### DevOps / IT

> As an IT admin, I want to plug in a custom storage backend (e.g. S3 or a shared network drive) by subclassing `StorageBackend` — without forking the gallery code.

### Company design owner

> As the person responsible for corporate design, I want to wrap the gallery with `corpframe` so all exported plots have our header/footer — by writing a 10-line `corp_gallery()` function.

## Script format

```python
# === CONFIGURATOR ===
title: str = "Q4 Revenue"
dpi: int = 150
show_target: bool = True

# === CODE ===
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot(df["x"], df["y"])
ax.set_title(title)

# === SAVE ===
# Optional post-processing. The gallery handles plot saving automatically.
# Gallery injects: date, version, BASE_DIR, PLOT_OUTPUT_PATH
```

- **Configurator**: Typed variable assignments rendered as form fields.
- **Code**: Main logic — produces figures, DataFrames, etc. Multiple outputs supported.
- **Save**: Runs only on "Save Version". For optional post-processing.

## Functional requirements

| # | Requirement | Status |
|---|---|---|
| F1 | Browse multiple named plots in a sidebar | Done |
| F2 | Select date and version for each plot | Done |
| F3 | View plot images and data tables | Done |
| F4 | Edit the script in a syntax-highlighted editor | Done (dash-ace) |
| F5 | Detect typed parameters and render form fields | Done |
| F6 | Run the script and show live preview | Done |
| F7 | Save as a new version (with confirmation + author) | Done |
| F8 | Refresh dates/versions from disk | Done |
| F9 | Search/filter plots by name | Done |
| F10 | Add new plots from the dashboard | Done (with gallery.json) |
| F11 | Pluggable storage backend | Done |
| F12 | JSON config file (read + write) | Done |
| F13 | Auto-discover plots from directory structure | Done |
| F14 | Optional export button (post-process with corpframe) | Done |
| F15 | Multi-output support (matplotlib, Plotly, DataFrames) | Done |
| F16 | Version diff labels (parameter changes between versions) | Done |
| F17 | Read-only mode (hide script editor) | Done |
| F18 | Export standalone .py script | Done |
| F19 | Author metadata on save | Done |
| F20 | New Date button (detect uncharted data dates) | Done |
| F21 | Copy from latest version when creating new date | Done |
| F22 | RUN does not modify editor (injection at execution time) | Done |
| F23 | Save uses selected date, not today | Done |

## Non-functional requirements

| # | Requirement | Status |
|---|---|---|
| N1 | No corporate-design dependency (generic) | Done |
| N2 | Works without dash-ace (falls back to textarea) | Done |
| N3 | Scripts execute in isolated subprocesses (60s timeout) | Done |
| N4 | Config file writes are atomic (temp + rename) | Done |
| N5 | Backwards-compatible with old 3-section scripts (LOAD/PLOT/SAVE) | Done |
| N6 | Plotly is optional (works without it installed) | Done |

## Future / backlog

| # | Item |
|---|---|
| B1 | Two-way binding: editing param fields auto-updates script AND vice versa |
| B2 | Delete plot / delete version from the dashboard |
| B3 | Authentication / access control |
| B4 | Git-backed storage backend |
| B5 | Scheduled script execution (cron-like) |
| B6 | Thumbnail previews in sidebar |
| B7 | Dirty-flag navigation warning (clientside JS) |
