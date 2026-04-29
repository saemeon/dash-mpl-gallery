"""Tests for gallery-viewer parameter detection."""

from gallery_viewer.params import (
    ParamSpec,
    detect_params,
    parse_typed_assignments,
)


class TestParseTypedAssignments:
    def test_str_default(self):
        params = parse_typed_assignments('title: str = "Q4 Revenue"')
        assert "title" in params
        assert params["title"].default == "Q4 Revenue"
        assert params["title"].annotation is str

    def test_int_default(self):
        params = parse_typed_assignments("dpi: int = 150")
        assert params["dpi"].default == 150
        assert params["dpi"].annotation is int

    def test_float_default(self):
        params = parse_typed_assignments("scale: float = 1.5")
        assert params["scale"].default == 1.5
        assert params["scale"].annotation is float

    def test_bool_default(self):
        params = parse_typed_assignments("verbose: bool = True")
        assert params["verbose"].default is True
        assert params["verbose"].annotation is bool

    def test_multiple_assignments(self):
        source = 'title: str = "Hello"\ndpi: int = 300\nscale: float = 2.0'
        params = parse_typed_assignments(source)
        assert len(params) == 3
        assert params["title"].default == "Hello"
        assert params["dpi"].default == 300
        assert params["scale"].default == 2.0

    def test_skips_private_names(self):
        params = parse_typed_assignments('_internal: str = "skip"')
        assert "_internal" not in params

    def test_skips_untyped_assignments(self):
        params = parse_typed_assignments("x = 42")
        assert len(params) == 0

    def test_skips_unsupported_types(self):
        params = parse_typed_assignments("data: list = []")
        assert len(params) == 0

    def test_skips_complex_expressions(self):
        params = parse_typed_assignments("value: int = 1 + 2")
        # BinOp is not a literal, should be skipped
        assert len(params) == 0

    def test_syntax_error_returns_empty(self):
        params = parse_typed_assignments("this is not valid python {{{}}")
        assert len(params) == 0

    def test_mixed_with_other_code(self):
        source = """
import pandas as pd
title: str = "My Chart"
df = pd.read_csv("data.csv")
dpi: int = 150
print("hello")
"""
        params = parse_typed_assignments(source)
        assert len(params) == 2
        assert params["title"].default == "My Chart"
        assert params["dpi"].default == 150


class TestDetectParams:
    def test_convention_params(self):
        source = 'title: str = "Q4 Revenue"\ndpi: int = 150'
        params = detect_params(source)
        assert "title" in params
        assert "dpi" in params

    def test_empty_source(self):
        params = detect_params("")
        assert len(params) == 0

    def test_no_params(self):
        source = "import pandas as pd\ndf = pd.read_csv('data.csv')"
        params = detect_params(source)
        assert len(params) == 0


class TestParamSpec:
    def test_type_name_str(self):
        p = ParamSpec(name="x", annotation=str)
        assert p.type_name == "str"

    def test_type_name_int(self):
        p = ParamSpec(name="x", annotation=int)
        assert p.type_name == "int"

    def test_type_name_none(self):
        p = ParamSpec(name="x", annotation=None)
        assert p.type_name == "str"
