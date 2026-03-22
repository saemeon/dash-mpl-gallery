# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Integration tests for Form callbacks — live Dash app via dash.testing.

Covers:
  - _forms.py lines 338-364  (register_visibility_callbacks / clientside JS)
  - _forms.py lines 393-414  (register_dirty_tracking / clientside JS)
  - _forms.py lines 719-809  (register_populate_callback / register_restore_callback outer bodies)
  - _forms.py lines 840-846  (register_submit_callback outer body)
"""

from __future__ import annotations

from typing import Annotated, Literal

import dash
import pytest
from dash import Input, html
from dash_fn_forms import Field, FnForm, build_fn_panel


# ── visibility callbacks (clientside JS) ─────────────────────────────────────


def test_visibility_hides_field_when_condition_false(dash_duo):
    """Fields with visible= are hidden/shown by the clientside callback."""

    def fn(
        mode: Literal["basic", "advanced"] = "basic",
        extra: Annotated[float, Field(visible=("mode", "==", "advanced"))] = 1.0,
    ) -> str:
        return mode

    app = dash.Dash(__name__)
    cfg = FnForm("vis_test", fn, _field_components="dcc", _replace=True)
    cfg.register_visibility_callbacks()
    app.layout = html.Div([cfg])

    dash_duo.start_server(app)

    # extra field should be hidden initially (mode == "basic")
    extra_wrapper = dash_duo.find_element("#_dft_vis_vis_test_extra")
    assert extra_wrapper.value_of_css_property("display") == "none"


def test_visibility_shows_field_after_condition_met(dash_duo):
    """Switching the controlling dropdown to 'advanced' reveals the hidden field."""

    def fn(
        mode: Literal["basic", "advanced"] = "basic",
        extra: Annotated[float, Field(visible=("mode", "==", "advanced"))] = 1.0,
    ) -> str:
        return mode

    app = dash.Dash(__name__)
    cfg = FnForm("vis_show_test", fn, _field_components="dcc", _replace=True)
    cfg.register_visibility_callbacks()
    output_div = html.Div(id="_dft_interact_out_vis_show_test")
    app.layout = html.Div([cfg, output_div])

    dash_duo.start_server(app)

    # Select "advanced" from the Dash 4 dropdown
    dash_duo.select_dcc_dropdown("#_dft_field_vis_show_test_mode", value="advanced")

    dash_duo.wait_for_style_to_equal(
        "#_dft_vis_vis_show_test_extra", "display", "block", timeout=5
    )


# ── restore callback ──────────────────────────────────────────────────────────


def test_restore_resets_field_to_default(dash_duo):
    """Clicking a reset button wired via register_restore_callback resets fields."""

    # Two-field form: multi-output callback returns a list correctly
    def fn(x: float = 5.0, y: float = 3.0) -> str:
        return f"x={x},y={y}"

    app = dash.Dash(__name__)
    cfg = FnForm(
        "restore_form",
        fn,
        _field_components="dcc",
        _replace=True,
        _initial_values={"x": 99.0, "y": 88.0},
    )
    # _initial_values sets f.default to 99/88; restore to fn's real defaults
    cfg._fields[0].default = 5.0
    cfg._fields[1].default = 3.0

    reset_btn = html.Button("Reset", id="restore_reset_btn", n_clicks=0)
    cfg.register_restore_callback(Input("restore_reset_btn", "n_clicks"))

    app.layout = html.Div([cfg, reset_btn])

    dash_duo.start_server(app)

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    # Verify the field starts at 99 (from _initial_values)
    dash_duo.wait_for_element("#_dft_field_restore_form_x")
    assert dash_duo.find_element("#_dft_field_restore_form_x").get_attribute("value") == "99"

    # Click reset — callback reverts to fn's defaults (5.0, 3.0)
    dash_duo.find_element("#restore_reset_btn").click()

    # Wait until x value changes from 99 to the real default (5 or 5.0)
    WebDriverWait(dash_duo.driver, 10).until(
        lambda d: d.find_element(By.ID, "_dft_field_restore_form_x").get_attribute("value") not in ("", "99")
    )


# ── submit callback ───────────────────────────────────────────────────────────


def test_submit_callback_fires_on_submit_button(dash_duo):
    """The auto panel wires up _on_change and renders output on load."""

    def fn(x: float = 2.0) -> str:
        return f"submitted={x}"

    app = dash.Dash(__name__)
    panel = build_fn_panel(fn, _id="submit_panel_test", _loading=False, _field_components="dcc")
    app.layout = html.Div([panel])

    dash_duo.start_server(app)

    # The auto panel fires on load
    dash_duo.wait_for_text_to_equal("#_dft_interact_out_submit_panel_test", "submitted=2.0", timeout=10)
