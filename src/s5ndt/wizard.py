# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import dash
from dash import Input, Output, dcc, html


@dataclass
class Wizard:
    """Return value of :func:`build_wizard`.

    Attributes
    ----------
    div :
        Self-contained component; place anywhere in the layout.
    open_input :
        ``Input(store_id, "data")`` — pass to
        :meth:`Config.register_populate_callback` to populate hooked fields
        when the wizard opens.
    """

    div: html.Div
    open_input: Input


def build_wizard(
    wizard_id: str,
    body: Any,
    trigger: str | Any = "Open",
    title: str = "",
    header_actions: Any = None,
) -> Wizard:
    """Wrap *body* in a modal wizard popup.

    Parameters
    ----------
    wizard_id :
        Unique namespace for component IDs.
    body :
        Any Dash component rendered inside the dialog, below the header.
    trigger :
        Either a string label (creates a plain ``html.Button``) or a custom
        Dash component with an ``id`` attribute that responds to ``n_clicks``.
    title :
        Text shown in the dialog header.
    header_actions :
        Optional component(s) rendered in the header row between the title
        and the ✕ close button.

    Returns
    -------
    Wizard
        ``.div`` — place anywhere in the layout.
        ``.open_input`` — pass to :meth:`Config.register_populate_callback`
        so hooked fields are populated when the wizard opens.
    """
    default_trigger_id = f"_s5ndt_wiz_trigger_{wizard_id}"
    close_id = f"_s5ndt_wiz_close_{wizard_id}"
    store_id = f"_s5ndt_wiz_store_{wizard_id}"
    modal_id = f"_s5ndt_wiz_modal_{wizard_id}"
    open_input = Input(store_id, "data")

    if isinstance(trigger, str):
        trigger_component = html.Button(trigger, id=default_trigger_id)
    else:
        if not hasattr(trigger, "id") or not trigger.id:
            raise ValueError("Custom trigger component must have an 'id' attribute.")
        trigger_component = trigger
    trigger_listen_id = trigger_component.id

    modal = html.Div(
        id=modal_id,
        style={"display": "none"},
        children=[
            # overlay — blocks interaction with underlying UI while open
            html.Div(
                style={
                    "position": "fixed",
                    "inset": "0",
                    "background": "rgba(0,0,0,0.4)",
                    "zIndex": 1000,
                }
            ),
            # dialog
            html.Div(
                style={
                    "position": "fixed",
                    "top": "50%",
                    "left": "50%",
                    "transform": "translate(-50%, -50%)",
                    "background": "white",
                    "padding": "24px",
                    "zIndex": 1001,
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "16px",
                    "minWidth": "600px",
                },
                children=[
                    html.Div(
                        style={
                            "display": "flex",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                        },
                        children=[
                            html.Strong(title),
                            html.Div(
                                style={
                                    "display": "flex",
                                    "gap": "4px",
                                    "alignItems": "center",
                                },
                                children=[
                                    *(
                                        [header_actions]
                                        if header_actions is not None
                                        else []
                                    ),
                                    html.Button("✕", id=close_id),
                                ],
                            ),
                        ],
                    ),
                    body,
                ],
            ),
        ],
    )

    store = dcc.Store(id=store_id, data=False)

    @dash.callback(
        Output(store_id, "data"),
        Input(trigger_listen_id, "n_clicks"),
        Input(close_id, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_store(open_clicks, close_clicks):
        return dash.ctx.triggered_id == trigger_listen_id

    @dash.callback(
        Output(modal_id, "style"),
        open_input,
    )
    def update_visibility(is_open):
        return {"display": "block"} if is_open else {"display": "none"}

    # When the trigger is a custom component, the user places it in the layout
    # themselves. Return only the store + modal so there's no duplicate render.
    children = (
        [store, modal]
        if not isinstance(trigger, str)
        else [trigger_component, store, modal]
    )
    return Wizard(
        div=html.Div(children),
        open_input=open_input,
    )
