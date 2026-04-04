# Parameters

The CONFIGURATOR section defines typed variables that the gallery auto-renders as form fields. Reviewers change these without touching code.

## Convention-based (recommended)

Type-annotated assignments at the top of the CONFIGURATOR section:

```python
# === CONFIGURATOR ===
title: str = "Q4 Revenue"
show_target: bool = True
dpi: int = 150
scale: float = 1.0
color: str = "#7CA3C6"
```

Supported types: `str`, `int`, `float`, `bool`.

| Type | Form field |
|------|-----------|
| `str` | Text input |
| `int` | Number input |
| `float` | Number input |
| `bool` | Checkbox |

## Decorator-based

For more complex setups, use the `@gallery_param` decorator:

```python
# === CONFIGURATOR ===
from gallery_viewer import gallery_param

@gallery_param
def configure(title: str = "Q4 Revenue", dpi: int = 150):
    pass
```

The decorator parses the function signature. If both convention and decorator params exist, the decorator takes precedence.

## How injection works

Form field values are **never written back into the editor** during RUN. Instead, they are injected as variable assignments prepended to the subprocess script at execution time.

Example: if the user changes `title` to "Updated Title" in the form:

```python
# Injected at execution time (not in the saved file):
title = 'Updated Title'

# Original CONFIGURATOR (unchanged):
title: str = "Q4 Revenue"
dpi: int = 150

# CODE section follows...
```

The injected value shadows the CONFIGURATOR default.

On **Save Version**, form values are written into the CONFIGURATOR section of the saved script file, so the file reflects the reviewer's changes.

## Update Script button

Explicitly writes current form values into the editor's CONFIGURATOR section. Useful when a reviewer wants to see the values reflected in the code before making additional manual edits.
