"""Gallery page — branch view at ``/branch/<branch_path>``.

The branch path is URL-encoded so that nested branches like
``finance/sub`` survive Dash's single-segment ``path_template`` capture
(see PAGES_MIGRATION.md §2 for why we couldn't use ``<path:path>``).

Card rendering moves here in Step 3; for now this is a placeholder that
proves routing + URL decoding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote

import dash
from dash import html

if TYPE_CHECKING:
    from gallery_viewer.gallery import Gallery

_gallery: Gallery | None = None


def bind(gallery: Gallery) -> None:
    """Attach the host Gallery and register page-scoped callbacks."""
    global _gallery
    _gallery = gallery
    # No callbacks today — gallery work happens in _layout(branch_path=...).


def _layout(branch_path: str | None = None, **_kwargs: object) -> html.Div:
    """Render the branch gallery for *branch_path*.

    Decoded `branch_path` is the slash-delimited group path (e.g.
    ``"finance/sub"``). Empty string renders the root view (all top-level
    items + subfolder cards). The host Gallery must have been bound first.

    ``**_kwargs`` swallows query-string params (e.g. ``?id=...`` left over
    from the detail page's URL) that Dash forwards into the layout call.
    """
    from gallery_viewer.config import load_config
    from gallery_viewer.gallery import _build_sidebar_tree, _render_gallery_view

    if _gallery is None:
        return html.Div("gallery page used before bind()", style={"color": "#888"})

    decoded = unquote(branch_path or "")
    descriptions: dict[str, str] = {}
    if _gallery._config_path:
        config = load_config(_gallery._config_path)
        for name, cfg in config.get("plots", {}).items():
            desc = cfg.get("description", "")
            if desc:
                descriptions[name] = desc
    tree = _build_sidebar_tree(_gallery.item_ids)
    return html.Div(
        _render_gallery_view(tree, decoded, descriptions),
        id="gv-gallery-page",
        style={"padding": "8px"},
    )


dash.register_page(__name__, path_template="/branch/<branch_path>", layout=_layout)
