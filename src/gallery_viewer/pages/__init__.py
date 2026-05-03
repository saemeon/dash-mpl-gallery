"""Dash Pages for gallery-viewer.

Each page module calls ``dash.register_page`` at import time and exposes a
``bind(gallery)`` function that the host ``Gallery`` calls during
``_build_app`` to (a) attach a Gallery reference for callbacks to close
over, and (b) register page-scoped callbacks via ``@dash.callback``.

The host ``Gallery`` instantiates Dash with ``use_pages=True,
pages_folder=""`` and explicitly imports + binds these modules. We do not
use auto-discovery — see PAGES_MIGRATION.md §1 for rationale.
"""
