"""Core data types for gallery-viewer.

Defines ``ScriptSections`` (script model with docstring/metadata/configurator/
code/save), ``OutputItem`` (typed multi-output capture), and ``RunResult``
(execution outcome with a list of captured outputs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScriptSections:
    """A script split into Docstring, Metadata, Configurator, Code, Save.

    - **Docstring**: Module-level prose describing the plot (stable across
      versions). Edited by the user directly in the file — *not* rewritten by
      Save. Surfaces via Python's ``__doc__`` at runtime.
    - **Metadata**: Per-version structured key/value pairs stamped at save
      time (author, save timestamp, change note, provenance). Tags are
      multi-valued and live here too, as one ``# tag: <name>`` line per tag.
    - **Configurator**: Typed variable assignments rendered as form fields.
    - **Code**: The main script logic (imports, data, plotting).
    - **Save**: Only executed on "Save Version" (writes files to disk).

    RUN  = Configurator + Code  (preview only)
    SAVE = Configurator + Code + Save  (writes to disk)

    On disk, the file looks like::

        \"\"\"Plot-level docstring.\"\"\"
        # === METADATA ===
        # author: Alice
        # saved: 2026-04-29 14:32
        # change: Switched to log scale.
        # tag: published
        # tag: final
        # data_hash: sha256:abc...

        # === CONFIGURATOR ===
        title: str = "Quarterly Revenue"

        # === CODE ===
        ...
    """

    docstring: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    configurator: str = ""
    code: str = ""
    save: str = ""

    MARKER_METADATA = "# === METADATA ==="
    MARKER_CONFIGURATOR = "# === CONFIGURATOR ==="
    MARKER_CODE = "# === CODE ==="
    MARKER_SAVE = "# === SAVE ==="

    # Reserved metadata key for tags — multi-valued.
    TAG_KEY = "tag"

    @classmethod
    def from_text(cls, text: str) -> ScriptSections:
        """Parse a script with optional docstring + section markers.

        Recognised structure (all parts optional except Code):

            <docstring>?
            # === METADATA ===
            # key: value
            # tag: ...
            # === CONFIGURATOR ===
            ...
            # === CODE ===
            ...
            # === SAVE ===
            ...
        """
        docstring, body = _split_docstring(text)

        if cls.MARKER_METADATA not in body and cls.MARKER_CONFIGURATOR not in body \
                and cls.MARKER_CODE not in body:
            # No markers at all — treat the whole body as code.
            return cls(docstring=docstring, code=body.strip())

        parts: dict[str, list[str]] = {
            "metadata": [],
            "configurator": [],
            "code": [],
            "save": [],
        }
        current: str | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if stripped == cls.MARKER_METADATA:
                current = "metadata"
            elif stripped == cls.MARKER_CONFIGURATOR:
                current = "configurator"
            elif stripped == cls.MARKER_CODE:
                current = "code"
            elif stripped == cls.MARKER_SAVE:
                current = "save"
            elif current:
                parts[current].append(line)

        metadata, tags = _parse_metadata_block(parts["metadata"])

        return cls(
            docstring=docstring,
            metadata=metadata,
            tags=tags,
            configurator="\n".join(parts["configurator"]).strip(),
            code="\n".join(parts["code"]).strip(),
            save="\n".join(parts["save"]).strip(),
        )

    def to_text(self) -> str:
        """Join all parts into a single script."""
        chunks: list[str] = []
        if self.docstring:
            chunks.append(_format_docstring(self.docstring))
        if self.metadata or self.tags:
            chunks.append(
                f"{self.MARKER_METADATA}\n"
                + _format_metadata_block(self.metadata, self.tags)
            )
        if self.configurator:
            chunks.append(f"{self.MARKER_CONFIGURATOR}\n{self.configurator}")
        chunks.append(f"{self.MARKER_CODE}\n{self.code}")
        if self.save:
            chunks.append(f"{self.MARKER_SAVE}\n{self.save}")
        return "\n\n".join(chunks) + "\n"

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

    def with_params(self, params: dict[str, object]) -> ScriptSections:
        """Return a copy with typed assignments in the configurator replaced by *params*.

        Only replaces lines of the form ``name: type = value``.  Unrecognised
        names in *params* are silently ignored.
        """
        if not params or not self.configurator:
            return self
        new_lines = []
        for line in self.configurator.splitlines():
            replaced = False
            for name, value in params.items():
                pattern = re.compile(rf"^({re.escape(name)}\s*:\s*\w+\s*=\s*)(.+)$")
                m = pattern.match(line.strip())
                if m:
                    if isinstance(value, str):
                        new_lines.append(f'{m.group(1)}"{value}"')
                    else:
                        new_lines.append(f"{m.group(1)}{value}")
                    replaced = True
                    break
            if not replaced:
                new_lines.append(line)
        return self._replace(configurator="\n".join(new_lines))

    def with_metadata(
        self, metadata: dict[str, str], *, replace: bool = False
    ) -> ScriptSections:
        """Return a copy with *metadata* merged into (or replacing) the metadata dict.

        Empty / ``None`` values are dropped (the key is omitted).  Keys equal
        to :attr:`TAG_KEY` are routed to :attr:`tags` instead — use
        :meth:`with_tags` for clarity.

        Parameters
        ----------
        metadata :
            ``{key: value}`` pairs to stamp.
        replace :
            If ``True``, the existing metadata dict is discarded first.  If
            ``False`` (default), incoming keys *update* existing ones and
            preserve insertion order for any new keys.
        """
        new_meta: dict[str, str] = {} if replace else dict(self.metadata)
        new_tags = list(self.tags)
        for key, value in metadata.items():
            if value is None or value == "":
                continue
            value_str = str(value).strip()
            if not value_str:
                continue
            if key == self.TAG_KEY:
                if value_str not in new_tags:
                    new_tags.append(value_str)
            else:
                new_meta[key] = value_str
        return self._replace(metadata=new_meta, tags=new_tags)

    def with_tags(
        self, tags: list[str] | tuple[str, ...], *, replace: bool = False
    ) -> ScriptSections:
        """Return a copy with *tags* added to (or replacing) :attr:`tags`.

        Duplicates are silently de-duplicated; insertion order is preserved.
        """
        existing = [] if replace else list(self.tags)
        for t in tags:
            t = t.strip()
            if t and t not in existing:
                existing.append(t)
        return self._replace(tags=existing)

    def with_docstring(self, docstring: str) -> ScriptSections:
        """Return a copy with :attr:`docstring` replaced by *docstring*."""
        return self._replace(docstring=docstring or "")

    def with_author(self, author: str) -> ScriptSections:
        """Return a copy with author + saved-timestamp metadata.

        Convenience equivalent to::

            self.with_metadata({"author": author, "saved": <timestamp>})
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        return self.with_metadata({"author": author, "saved": timestamp})

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

    # -- internal -------------------------------------------------------------

    def _replace(self, **changes: object) -> ScriptSections:
        """Return a copy with the given attributes overridden."""
        return ScriptSections(
            docstring=changes.get("docstring", self.docstring),  # type: ignore[arg-type]
            metadata=changes.get("metadata", self.metadata),  # type: ignore[arg-type]
            tags=changes.get("tags", self.tags),  # type: ignore[arg-type]
            configurator=changes.get("configurator", self.configurator),  # type: ignore[arg-type]
            code=changes.get("code", self.code),  # type: ignore[arg-type]
            save=changes.get("save", self.save),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Parsing / formatting helpers
# ---------------------------------------------------------------------------

_DOCSTRING_RE = re.compile(
    r'\A\s*(?P<quote>"""|\'\'\')(?P<body>.*?)(?P=quote)\s*',
    re.DOTALL,
)


def _split_docstring(text: str) -> tuple[str, str]:
    """Strip a leading module docstring from *text*.

    Returns ``(docstring_body, remaining_text)``.  If no docstring is present,
    ``docstring_body`` is empty and *text* is returned unchanged (apart from
    a leading-whitespace trim of the remainder).
    """
    m = _DOCSTRING_RE.match(text)
    if not m:
        return "", text
    body = m.group("body")
    # Trim a single leading/trailing newline added by the formatter — keep
    # internal blank lines intact.
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]
    rest = text[m.end():]
    return body, rest.lstrip("\n")


def _format_docstring(docstring: str) -> str:
    """Render a module docstring with triple double-quotes."""
    body = docstring.rstrip("\n")
    if "\n" in body:
        return f'"""{body}\n"""'
    return f'"""{body}"""'


def _parse_metadata_block(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """Parse a list of raw lines from a METADATA block.

    Recognises::

        # key: value          → metadata["key"] = "value"
        # tag: <name>         → tags.append(name)
        # key:                → multi-line value; collect indented continuation
        #   continuation
        #   continuation

    Lines that are not ``#``-comments are silently ignored (the user might
    have stuck a stray blank in there).  Empty values are dropped.
    """
    metadata: dict[str, str] = {}
    tags: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s.startswith("#"):
            i += 1
            continue
        body = s[1:].lstrip()
        if ":" not in body:
            i += 1
            continue
        key, _, value = body.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            i += 1
            continue

        # Multi-line value: empty after the colon, look for indented `#  ...`
        # continuation lines.
        if not value:
            collected: list[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                ns = nxt.strip()
                if not ns.startswith("#"):
                    break
                nbody = ns[1:]
                # Continuation lines start with whitespace after the `#`
                # (e.g. `#  text`).  A `#` immediately followed by `key:`
                # ends the multi-line value.
                if not nbody.startswith(" ") and not nbody.startswith("\t"):
                    break
                if ":" in nbody.lstrip()[:40] and re.match(
                    r"^\s*\w+\s*:\s*\S", nbody
                ):
                    # Looks like another key, even if indented — bail.
                    break
                collected.append(nbody.lstrip())
                j += 1
            value = "\n".join(collected).strip()
            i = j
        else:
            i += 1

        if not value:
            continue
        if key == ScriptSections.TAG_KEY:
            if value not in tags:
                tags.append(value)
        else:
            metadata[key] = value

    return metadata, tags


def _format_metadata_block(metadata: dict[str, str], tags: list[str]) -> str:
    """Render metadata + tags as ``# key: value`` comment lines.

    Order: metadata in insertion order, then tags (one per line).  Multi-line
    values are stamped as::

        # key:
        #   line 1
        #   line 2
    """
    lines: list[str] = []
    for key, value in metadata.items():
        if value is None or value == "":
            continue
        value_str = str(value)
        if "\n" in value_str:
            lines.append(f"# {key}:")
            lines.extend(f"#   {line}" for line in value_str.splitlines())
        else:
            lines.append(f"# {key}: {value_str}")
    for tag in tags:
        if tag:
            lines.append(f"# {ScriptSections.TAG_KEY}: {tag}")
    return "\n".join(lines)


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
    ``image_bytes`` convenience property returns the first image item,
    used when persisting a PNG to disk.
    """

    output: str = ""
    error: str = ""
    items: list[OutputItem] = field(default_factory=list)
    success: bool = True

    @property
    def image_bytes(self) -> bytes | None:
        """First image output (for saving to disk)."""
        for item in self.items:
            if item.mime.startswith("image/"):
                return item.data
        return None
