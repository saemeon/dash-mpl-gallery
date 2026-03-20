# dash-fn-tools

An introspection-based UI generator for Plotly Dash. Automatically transform type-hinted Python functions into reactive Dash forms.

## Installation

```bash
pip install dash-fn-tools
```

## How it works

`build_config` inspects a function's signature and generates a matching Dash form. Parameters whose names start with `_` are skipped — use this convention to pass internal data (figure JSON, file handles, etc.) without exposing them to the user.

The result is a `Config` object with three things you need:

- **`.div`** — an `html.Div` with labeled inputs, ready to embed anywhere in your layout
- **`.states`** — a `list[State]` to include in your callback decorator
- **`.build_kwargs(values)`** — converts raw callback values back to typed Python kwargs

## Quickstart

```python
from dash import Dash, Input, Output, html
from dash_fn_tools import build_config

app = Dash(__name__)

def my_renderer(title: str = "Chart", dpi: int = 150, show_grid: bool = True):
    """Render a matplotlib figure."""
    ...

cfg = build_config("render", my_renderer)

app.layout = html.Div([
    cfg.div,
    html.Button("Apply", id="apply"),
    html.Div(id="result"),
])

@app.callback(Output("result", "children"), Input("apply", "n_clicks"), *cfg.states)
def on_apply(n, *values):
    if not n:
        return ""
    kwargs = cfg.build_kwargs(values)
    # {"title": "Chart", "dpi": 150, "show_grid": True}
    my_renderer(**kwargs)
    return "Done"

if __name__ == "__main__":
    app.run(debug=True)
```

## Type mapping

Each parameter type maps to a specific Dash component:

| Python type | Dash component |
|---|---|
| `str` | `dcc.Input(type="text")` |
| `int` | `dcc.Input(type="number", step=1)` |
| `float` | `dcc.Input(type="number", step="any")` |
| `bool` | `dcc.Checklist` |
| `date` | `dcc.DatePickerSingle` |
| `datetime` | `dcc.DatePickerSingle` + `dcc.Input` (HH:MM) |
| `Literal[A, B, C]` | `dcc.Dropdown` |
| `list[T]` / `tuple[T, ...]` | `dcc.Input(type="text")` — comma-separated |
| `T \| None` / `Optional[T]` | same as `T`, submits `None` when empty |

## Customization

### Per-field: `FieldSpec`

Pass a `FieldSpec` in the `field_specs` dict or embed it directly in the type annotation:

```python
from typing import Annotated
from dash_fn_tools import build_config, FieldSpec

def my_fn(
    name: Annotated[str, FieldSpec(label="Full name", col_span=2)],
    dpi: int = 150,
):
    ...

cfg = build_config("ex", my_fn, cols=2)
```

Or pass it externally (useful for functions you don't own):

```python
cfg = build_config("ex", my_fn, field_specs={
    "dpi": FieldSpec(min=72, max=600, step=1, description="Output resolution"),
})
```

Key `FieldSpec` options:

| Field | Description |
|---|---|
| `label` | Override the auto-generated label |
| `description` | Help text below the input |
| `col_span` | Column span in a multi-column grid |
| `style` | CSS dict for the input component |
| `class_name` | CSS class for the input component |
| `component` | Replace the component entirely |
| `component_prop` | Property to read from a custom component (default `"value"`) |
| `min` / `max` / `step` | Numeric constraints (int/float only) |
| `hook` | `FieldHook` for runtime defaults |

### Type-level styling

Apply CSS to all fields of a given type:

```python
cfg = build_config("ex", my_fn, styles={
    "int": {"width": "80px"},
    "str": {"width": "200px"},
    "label": {"fontWeight": "600"},
})
```

Valid keys: `"str"`, `"int"`, `"float"`, `"bool"`, `"date"`, `"datetime"`, `"literal"`, `"list"`, `"tuple"`, `"label"`.

### Runtime defaults: `FieldHook`

Use a `FieldHook` to populate a field from live Dash state when a dialog opens:

```python
from dash_fn_tools import build_config, FieldSpec, FromComponent

graph = dcc.Graph(id="my-graph", figure=...)

def my_renderer(title: str = ""):
    ...

cfg = build_config("render", my_renderer, field_specs={
    "title": FieldSpec(hook=FromComponent(graph, "figure")),
})

# Wire the populate callback (fires when a modal opens):
cfg.register_populate_callback(Input("modal", "is_open"))
```

`FromComponent(component, prop)` reads `component.prop` as the initial field value. The field is only populated when currently empty — existing user input is preserved.

Implement `FieldHook` yourself to pull defaults from any source:

```python
from dash_fn_tools import FieldHook
from dash import State

class FromStore(FieldHook):
    def required_states(self):
        return [State("my-store", "data")]

    def get_default(self, data):
        return (data or {}).get("title", "")
```

### Reset to defaults

Register a restore callback to reset all fields when a button is clicked:

```python
cfg.register_restore_callback(Input("reset-btn", "n_clicks"))
```

Non-hooked fields revert to their static defaults; hooked fields call `hook.get_default()` again.

## Multi-column grid

```python
cfg = build_config("ex", my_fn, cols=3)
# use FieldSpec(col_span=3) on a field to span the full width
```
