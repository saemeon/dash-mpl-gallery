# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

"""dash-fn-interact — introspect a typed callable into a Dash form."""

from dash_fn_interact._config_builder import Config, FieldRef, build_config, field_id
from dash_fn_interact._interact import interact
from dash_fn_interact._spec import Field, FieldHook, FromComponent, fixed
from dash_fn_interact.backends import (
    ComponentBackend,
    DBCBackend,
    DCCBackend,
    DMCBackend,
)

__all__ = [
    "ComponentBackend",
    "Config",
    "DBCBackend",
    "DCCBackend",
    "DMCBackend",
    "Field",
    "FieldHook",
    "FieldRef",
    "FromComponent",
    "build_config",
    "field_id",
    "fixed",
    "interact",
]
