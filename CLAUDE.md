# dash-mpl-gallery

A Dash dashboard for **versioned, scripted matplotlib charts** — built so that
the chart, its source script, its data, and its history all live as plain files
that any human or pipeline can inspect.

This file documents the *identity* of the tool, the *user stories* that drive
its design, and the *near-term roadmap*. For workspace-level architecture
(packages, dependencies, conventions), see the top-level `CLAUDE.md`.

---

## Identity — three principles

The package was designed around three principles, each implied by a primary
user story:

1. **The tool is for thinking, not just rendering.**
   *Story: an analyst iterating on a chart for a paper.*
   The answer is rarely v1. The user needs to compare v3 vs v7 and remember
   why. Versioning is first-class, diffs are visible, history is browsable.

2. **The tool has no skill floor.**
   *Story: the boss fixes a typo in the chart title.*
   Anyone who can read `title = "Foo"` is enabled. No IDE setup, no
   environment, no pipeline. The form fields lift typed assignments out of
   the script for non-coders; the script editor is there for power users.

3. **The tool floats above plain files.**
   *Story: someone tar's the directory and emails it.*
   No DB, no proprietary format, no "export to share." The plot, script, and
   data are all on disk in obvious filenames. The Gallery is *orchestration
   plus standardisation* over a directory tree, not a wrapper around state
   that lives somewhere else.

These principles are the test for any new feature: does it respect the
versioning model, does it stay accessible, does it keep the filesystem
self-describing?

---

## User stories

The three above plus the additional ones that surfaced during design review:

### 4. **The reproducer** — "Send me the chart from your Tuesday slide"
The consumer wants to see what the chart was made from. The standalone export
(`export_standalone` callback + `export_inject_vars` facade) is the answer:
one self-contained `.py` file that runs on a clean Python install and writes
the same PNG. **Implication:** every chart should be trivially reproducible
from a single file.

### 5. **The annotator** — "I want to record WHY I made this change in v4"
The Author field is the seed. The natural extension is a per-version commit
message — not just "Saved by Alice" but "Switched to log scale because client
said the linear view buried the small categories." This is where the
analytical *thinking* lives, and right now it has nowhere to go.

### 6. **The reviewer** — "Show me what changed between Tuesday and today"
`version_diff` covers parameter changes. The real reviewer question is "did
the chart change, and how?" — implying side-by-side image diff, possibly a
perceptual diff badge. Today the reviewer mentally A/Bs v3 and v4.

### 7. **The publication-time freezer** — "Don't let v7 ever change"
Once a chart ships in a paper, every future operation must be non-destructive.
Versioning helps, but there's no "this is locked" marker. A frozen flag, or
just a convention (`script_..._v7_FINAL.py`) the UI respects.

### 8. **The new collaborator** — "I just got added, what's going on?"
A new analyst lands in the directory. The plot dir has 47 PNGs and the README
is empty. They don't know which is current, which was rejected, which was a
draft. Wants to grow into a *project state* layer (a `status.md` per date, or
a "current" pointer).

### 9. **The auditor / stickler** — "Show me the data lineage"
For regulated contexts: "what data file produced this exact PNG?" Today the
linkage is convention (`data_YYYYMMDD.csv` → `script_YYYYMMDD_vN.py` →
`plot_YYYYMMDD_vN.png`). An auditor wants a **hash**. Stamp the data hash
into the script's frontmatter at save time.

### 10. **The naive user who shouldn't break things** — "I just wanted to see"
The boss again, but more dangerous. They edit, hit Save, and now v8 is "boss's
experiment" instead of "the canonical chart." Want a sandbox/draft mode, or
auto-save-as-branch behavior.

### 11. **The CI / pipeline integrator** — "Run this chart from a Makefile"
The standalone export gives a runnable script. What's missing is a stable
**interface contract**: `BASE_DIR/data/...` in, `OUTPUT_PATH` out. If a user
rewires those in their script, downstream pipelines break silently.
`export_inject_vars` is the start of this contract.

### 12. **The forgetful self of three months from now** — "What is this?"
You open a folder you haven't touched since January. Configurator says
`threshold: float = 0.42`. Why 0.42? The author comment helps a little. The
methodology lives outside the gallery. Want a `notes/` companion or a
free-form "purpose" field.

---

## Cross-cutting patterns

What the stories together imply about *missing dimensions*:

- **Provenance** (data hash, brand version, library versions) — for #9, #11
- **Intent capture** (why this version exists) — for #5, #6, #8, #12
- **Diff visualization** (image diff, not just config diff) — for #6
- **State markers** (final / draft / locked) — for #7, #10

The cheapest, highest-leverage of these is **intent capture**. One free-form
`description` field per version unlocks #5, #6, #8, and #12 with a single
feature.

---

## Near-term roadmap

### A. Intent capture — per-version description / commit message
**Why:** unlocks four user stories at once (#5, #6, #8, #12). Today the
"Saved by Alice" line is the only metadata; it answers *who*, never *why*.

**Shape:**
- New free-form text field on the Save modal ("What changed in this version?").
- Persisted as a comment block at the top of the saved script (keeping the
  flat-file principle — anyone reading the `.py` directly sees the rationale).
- Surfaced in the version dropdown / diff label as a tooltip or inline hint.

**Cost:** ~half day. Low-risk.

### B. Provenance stamping
**Why:** unlocks #9 (audit) and #11 (CI). Makes the chart self-describing in
ways that survive even after the gallery is gone.

**Shape:**
- At save time, hash the data file (sha256 of `data_YYYYMMDD.csv`) and stamp
  into the script's frontmatter.
- Stamp `mpl_brandpacker` version (and any other brand-determining deps).
- Optionally stamp Python version + key library versions (matplotlib, pandas).
- Surface a "Provenance" section in the gallery UI.

**Cost:** ~1 day. Medium-risk: needs a stable convention for the frontmatter
shape so downstream consumers can parse it.

### C. Current-user registration
**Why:** small but high-quality-of-life. Makes the Author field auto-fill so
the user doesn't type their name every save. Pairs naturally with #5 (intent
capture) — if the user is registered, the modal becomes "describe what
changed" and the author is implicit.

**Shape:**
```python
g = Gallery(user="Paul")     # at construction
g.user = "Alice"             # later, e.g. from a Dash login callback
```
- `Gallery.user: str | None` attribute, settable.
- `save_script(..., author=None)` — if `author is None`, fall back to
  `self.user`.
- Save modal pre-fills the author field from `g.user`.

**Multi-user nuance (deferred):** for a deployed Dash app with multiple
concurrent sessions, a process-wide `g.user` would leak across sessions. The
right shape there is a per-session Dash `Store` populated by the login
callback, then the modal reads from the Store. **Not in scope for v1** —
local/single-user is the dominant story today.

**Cost:** ~1 hour. Low-risk.

---

## Out of scope (deliberately)

- **Bulk operations** (CLI runners, rerun-all-charts after a brand update,
  matrix re-execution). Tempting, but not the current pain point.
- **Image diff / perceptual diff badges** (#6). Useful, but second-priority
  to intent capture, which addresses the underlying need ("what changed?")
  more cheaply.
- **Frozen / final markers** (#7). Convention-based for now; revisit if the
  publication workflow becomes painful.
- **Multi-user session model.** See #C nuance above.

---

## Architectural notes

### Facade pattern
`Gallery` exposes a thin facade over `StorageBackend` for every operation
the UI needs (`list_dates`, `load_script`, `save_script`, `run_script`,
`version_diff`, `export_inject_vars`, `apply_params_to_script`,
`version_diff_label`, …). Callbacks are kept thin: parse Dash inputs,
delegate to a facade method, format the result for Dash outputs.

**Rule of thumb:** if a callback grows more than ~5 lines of inline logic,
extract that logic into a facade method. The facade is unit-testable; the
callback is not. The current test suite (~240 tests) exists *because* the
facade exists.

### Backends
`StorageBackend` is the abstraction; `FileSystemBackend` is the concrete
flat-file implementation. The facade and the UI never assume filesystem —
they go through the backend. A future S3 / cloud backend would slot in here
without UI changes.

### Tests
- `tests/gallery_viewer/` — unit + integration tests, ~240
- `tests/gallery_viewer/conftest.py` — shared fixtures (`make_dir`,
  `multi_backend_gallery`, `gallery_with_chain`, `empty_gallery`)
- Coverage strategy: aim for *thorough scenario coverage* on the facade;
  accept lower line coverage on callbacks (they're UI glue and self-checking
  visually). The right test investment is parametrized matrices over
  configurations × workflows × orderings, not exhaustive callback tests.
