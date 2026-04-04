"""Core data types for gallery-viewer.

Defines ``ScriptSections`` (three-part script model), ``OutputItem``
(typed multi-output capture), and ``RunResult`` (execution outcome with
a list of captured outputs).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScriptSections:
    """A script split into Configurator, Code, and Save sections.

    - **Configurator**: Typed variable assignments rendered as form fields.
    - **Code**: The main script logic (imports, data, plotting).
    - **Save**: Only executed on "Save Version" (writes files to disk).

    RUN  = Configurator + Code  (preview only)
    SAVE = Configurator + Code + Save  (writes to disk)
    """

    configurator: str = ""
    code: str = ""
    save: str = ""

    MARKER_CONFIGURATOR = "# === CONFIGURATOR ==="
    MARKER_CODE = "# === CODE ==="
    MARKER_SAVE = "# === SAVE ==="

    # Legacy markers (backwards compat)
    _LEGACY_LOAD = "# === LOAD ==="
    _LEGACY_PLOT = "# === PLOT ==="

    @classmethod
    def from_text(cls, text: str) -> ScriptSections:
        """Parse a script with section markers."""
        # New format: CONFIGURATOR + CODE + SAVE
        if cls.MARKER_CONFIGURATOR in text or cls.MARKER_CODE in text:
            parts: dict[str, list[str]] = {"configurator": [], "code": [], "save": []}
            current = None
            for line in text.splitlines():
                stripped = line.strip()
                if stripped == cls.MARKER_CONFIGURATOR:
                    current = "configurator"
                elif stripped == cls.MARKER_CODE:
                    current = "code"
                elif stripped == cls.MARKER_SAVE:
                    current = "save"
                elif current:
                    parts[current].append(line)
            return cls(
                configurator="\n".join(parts["configurator"]).strip(),
                code="\n".join(parts["code"]).strip(),
                save="\n".join(parts["save"]).strip(),
            )

        # Legacy format: LOAD + PLOT + SAVE
        if cls._LEGACY_LOAD in text:
            parts_legacy: dict[str, list[str]] = {"load": [], "plot": [], "save": []}
            current = None
            for line in text.splitlines():
                stripped = line.strip()
                if stripped == cls._LEGACY_LOAD:
                    current = "load"
                elif stripped == cls._LEGACY_PLOT:
                    current = "plot"
                elif stripped == "# === SAVE ===" or stripped == cls.MARKER_SAVE:
                    current = "save"
                elif current:
                    parts_legacy[current].append(line)
            load = "\n".join(parts_legacy["load"]).strip()
            plot = "\n".join(parts_legacy["plot"]).strip()
            save = "\n".join(parts_legacy["save"]).strip()
            code_parts = [p for p in [load, plot] if p]
            return cls(configurator="", code="\n\n".join(code_parts), save=save)

        # No markers — everything is code
        return cls(code=text.strip())

    def to_text(self) -> str:
        """Join sections back into a single script."""
        parts = []
        if self.configurator:
            parts.append(f"{self.MARKER_CONFIGURATOR}\n{self.configurator}")
        parts.append(f"{self.MARKER_CODE}\n{self.code}")
        if self.save:
            parts.append(f"{self.MARKER_SAVE}\n{self.save}")
        return "\n\n".join(parts) + "\n"

    def to_preview(self, inject_vars: dict[str, object] | None = None) -> str:
        """Configurator + Code (for RUN — no Save).

        Parameters
        ----------
        inject_vars :
            Optional ``{name: value}`` dict prepended as Python assignments
            before the script code.  Used to override CONFIGURATOR defaults
            at execution time without modifying the stored script.
        """
        parts = []
        if inject_vars:
            parts.append(_format_inject_vars(inject_vars))
        if self.configurator:
            parts.append(self.configurator)
        parts.append(self.code)
        return "\n\n".join(parts)

    def to_full(self, inject_vars: dict[str, object] | None = None) -> str:
        """Configurator + Code + Save (for Save Version).

        Parameters
        ----------
        inject_vars :
            Optional ``{name: value}`` dict prepended as Python assignments.
        """
        parts = []
        if inject_vars:
            parts.append(_format_inject_vars(inject_vars))
        if self.configurator:
            parts.append(self.configurator)
        parts.append(self.code)
        if self.save:
            parts.append(self.save)
        return "\n\n".join(parts)


@dataclass
class OutputItem:
    """A single output captured from script execution.

    Supported ``mime`` values:

    - ``"image/png"`` -- matplotlib figure saved as PNG.
    - ``"application/vnd.plotly+json"`` -- Plotly figure serialised as JSON.
    - ``"text/csv"`` -- pandas DataFrame exported as CSV (first 200 rows).
    """

    mime: str  # "image/png", "application/vnd.plotly+json", "text/csv"
    data: bytes


def _format_inject_vars(vars: dict[str, object]) -> str:
    """Format *vars* as Python assignment lines (``name = repr(value)``).

    The resulting block is prepended to script code so that CONFIGURATOR
    defaults can be overridden at execution time without editing the script.
    """
    lines = []
    for name, value in vars.items():
        if isinstance(value, str):
            lines.append(f'{name} = {value!r}')
        elif isinstance(value, bool):
            lines.append(f"{name} = {value}")
        else:
            lines.append(f"{name} = {repr(value)}")
    return "\n".join(lines)


@dataclass
class RunResult:
    """Result of executing a script.

    ``items`` contains all captured outputs (images, Plotly JSON, CSVs)
    in the order they were discovered by the capture epilogue.  The
    ``plot_bytes`` convenience property returns the first image item,
    used when persisting a PNG to disk.
    """

    output: str = ""
    error: str = ""
    items: list[OutputItem] = field(default_factory=list)
    success: bool = True

    @property
    def plot_bytes(self) -> bytes | None:
        """First image output (for saving PNG to disk)."""
        for item in self.items:
            if item.mime.startswith("image/"):
                return item.data
        return None
