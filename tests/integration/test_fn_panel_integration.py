# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Integration tests for FnPanel — live Dash app via dash.testing.

Covers the callback bodies that cannot be reached in unit tests:
  - fn_interact.py lines 194-195  (_on_apply callback body)
  - fn_interact.py lines 206-207  (_on_change callback body)
"""

from __future__ import annotations

import dash
import pytest
from dash import html
from dash_fn_forms import build_fn_panel


# ── auto-update panel (_on_change callback) ──────────────────────────────────


def test_auto_panel_renders_output(dash_duo):
    """Changing a field value triggers _on_change and updates the output div."""

    def double(x: float = 1.0) -> str:
        return f"result={x * 2}"

    app = dash.Dash(__name__)
    panel = build_fn_panel(double, _id="auto_test", _loading=False)
    app.layout = html.Div([panel])

    dash_duo.start_server(app)

    # Initial render — callback fires on load
    output_sel = "#_dft_interact_out_auto_test"
    dash_duo.wait_for_text_to_equal(output_sel, "result=2.0", timeout=10)


def test_auto_panel_updates_on_input_change(dash_duo):
    """Typing a new value into the input re-fires _on_change."""

    def triple(x: float = 1.0) -> str:
        return f"val={x * 3}"

    app = dash.Dash(__name__)
    panel = build_fn_panel(triple, _id="triple_test", _loading=False, _field_components="dcc")
    app.layout = html.Div([panel])

    dash_duo.start_server(app)

    # Clear, type a new value, and press Enter to fire the debounced input
    from selenium.webdriver.common.keys import Keys

    inp = dash_duo.find_element("#_dft_field_triple_test_x")
    inp.clear()
    inp.send_keys("4")
    inp.send_keys(Keys.RETURN)

    output_sel = "#_dft_interact_out_triple_test"
    dash_duo.wait_for_text_to_equal(output_sel, "val=12.0", timeout=10)


def test_auto_panel_exception_shows_error_pre(dash_duo):
    """If fn raises, the output shows an html.Pre with 'Error:'."""

    def boom(x: float = 1.0) -> str:
        raise ValueError("kaboom")

    app = dash.Dash(__name__)
    panel = build_fn_panel(boom, _id="boom_test", _loading=False)
    app.layout = html.Div([panel])

    dash_duo.start_server(app)

    output_sel = "#_dft_interact_out_boom_test"
    dash_duo.wait_for_contains_text(output_sel, "Error:", timeout=10)


# ── manual panel (_on_apply callback) ────────────────────────────────────────


def test_manual_panel_does_not_fire_on_load(dash_duo):
    """Manual panel: output is empty before Apply is clicked."""

    def add(x: float = 1.0, y: float = 2.0) -> str:
        return f"sum={x + y}"

    app = dash.Dash(__name__)
    panel = build_fn_panel(add, _id="manual_test", _manual=True, _loading=False)
    app.layout = html.Div([panel])

    dash_duo.start_server(app)

    output_sel = "#_dft_interact_out_manual_test"
    # Output div should be empty (no initial call for manual panels)
    dash_duo.wait_for_element(output_sel)
    elem = dash_duo.find_element(output_sel)
    assert elem.text == ""


def test_manual_panel_fires_on_apply_click(dash_duo):
    """Clicking Apply fires _on_apply and fills the output."""

    def add(x: float = 3.0, y: float = 4.0) -> str:
        return f"sum={x + y}"

    app = dash.Dash(__name__)
    panel = build_fn_panel(add, _id="manual_click_test", _manual=True, _loading=False)
    app.layout = html.Div([panel])

    dash_duo.start_server(app)

    btn_sel = "#_dft_interact_btn_manual_click_test"
    dash_duo.find_element(btn_sel).click()

    output_sel = "#_dft_interact_out_manual_click_test"
    dash_duo.wait_for_text_to_equal(output_sel, "sum=7.0", timeout=10)
