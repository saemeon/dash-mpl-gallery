# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""Tests for dash_fn_forms.utils."""

from __future__ import annotations

from dash_fn_forms.utils import _caller_name, _in_jupyter


def test_caller_name_returns_string():
    result = _caller_name(set())
    assert isinstance(result, str)


def test_caller_name_skips_listed_modules():
    # Skip everything — falls back to "__main__"
    result = _caller_name({"__main__", __name__})
    assert isinstance(result, str)


def test_caller_name_not_in_skip_set():
    skip = {"nonexistent_module_xyz"}
    result = _caller_name(skip)
    assert result not in skip


def test_in_jupyter_returns_bool():
    result = _in_jupyter()
    assert isinstance(result, bool)


def test_in_jupyter_false_in_pytest():
    # We're in pytest, not a ZMQInteractiveShell
    assert _in_jupyter() is False
