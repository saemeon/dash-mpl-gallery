"""Tests for the sidebar tree helpers."""

from __future__ import annotations

import pytest
from dash import html

from gallery_viewer.gallery import _build_sidebar_tree, _render_tree_node


# ---------------------------------------------------------------------------
# _build_sidebar_tree
# ---------------------------------------------------------------------------


class TestBuildSidebarTree:
    def test_flat_names(self):
        tree = _build_sidebar_tree(["alpha", "beta"])
        assert tree["__leaves__"] == ["alpha", "beta"]
        assert set(tree.keys()) == {"__leaves__"}

    def test_single_group(self):
        tree = _build_sidebar_tree(["g/x", "g/y"])
        assert tree["__leaves__"] == []
        assert "g" in tree
        assert tree["g"]["__leaves__"] == ["g/x", "g/y"]

    def test_mixed_flat_and_grouped(self):
        tree = _build_sidebar_tree(["standalone", "g/x", "g/y"])
        assert tree["__leaves__"] == ["standalone"]
        assert tree["g"]["__leaves__"] == ["g/x", "g/y"]

    def test_two_levels(self):
        tree = _build_sidebar_tree(["a/b/c", "a/b/d", "a/e"])
        assert tree["__leaves__"] == []
        assert tree["a"]["__leaves__"] == ["a/e"]
        assert tree["a"]["b"]["__leaves__"] == ["a/b/c", "a/b/d"]

    def test_three_levels(self):
        tree = _build_sidebar_tree(["x/y/z/leaf"])
        assert tree["x"]["y"]["z"]["__leaves__"] == ["x/y/z/leaf"]

    def test_max_depth_clamped(self):
        """Keys deeper than MAX_TREE_DEPTH are flattened into the last group."""
        tree = _build_sidebar_tree(["a/b/c/d/e"])
        # MAX_TREE_DEPTH=4 → parts becomes ["a", "b", "c", "d/e"]
        assert tree["a"]["b"]["c"]["__leaves__"] == ["a/b/c/d/e"]

    def test_empty_list(self):
        tree = _build_sidebar_tree([])
        assert tree == {"__leaves__": []}

    def test_multiple_groups_same_level(self):
        tree = _build_sidebar_tree(["finance/rev", "marketing/roi", "standalone"])
        assert tree["__leaves__"] == ["standalone"]
        assert tree["finance"]["__leaves__"] == ["finance/rev"]
        assert tree["marketing"]["__leaves__"] == ["marketing/roi"]

    def test_preserves_order(self):
        names = ["z/b", "z/a", "a/x"]
        tree = _build_sidebar_tree(names)
        assert tree["z"]["__leaves__"] == ["z/b", "z/a"]
        assert tree["a"]["__leaves__"] == ["a/x"]

    def test_deep_nesting_four_levels(self):
        tree = _build_sidebar_tree(["l1/l2/l3/leaf"])
        node = tree["l1"]["l2"]["l3"]
        assert node["__leaves__"] == ["l1/l2/l3/leaf"]


# ---------------------------------------------------------------------------
# _render_tree_node
# ---------------------------------------------------------------------------


class TestRenderTreeNode:
    def test_flat_renders_nav_items(self):
        tree = _build_sidebar_tree(["alpha", "beta"])
        result = _render_tree_node(tree, [], None, {})
        assert len(result) == 2
        # Both should be nav items with correct IDs
        assert result[0].id == {"type": "gv-nav-item", "index": "alpha"}
        assert result[1].id == {"type": "gv-nav-item", "index": "beta"}

    def test_group_renders_header_and_children(self):
        tree = _build_sidebar_tree(["g/x", "g/y"])
        result = _render_tree_node(tree, [], None, {})
        # group header, then injected Overview leaf, then the two leaves
        assert result[0].id == {"type": "gv-tree-group", "index": "g"}
        assert result[1].id == {"type": "gv-overview", "index": "g"}
        assert result[2].id == {"type": "gv-nav-item", "index": "g/x"}
        assert result[3].id == {"type": "gv-nav-item", "index": "g/y"}

    def test_collapsed_group_hides_children(self):
        tree = _build_sidebar_tree(["g/x", "g/y"])
        result = _render_tree_node(tree, ["g"], None, {})
        # Only the group header, no children
        assert len(result) == 1
        assert result[0].id == {"type": "gv-tree-group", "index": "g"}

    def test_nested_group_headers(self):
        tree = _build_sidebar_tree(["a/b/leaf"])
        result = _render_tree_node(tree, [], None, {})
        # a header, a Overview, b header, a/b Overview, leaf
        assert len(result) == 5
        assert result[0].id == {"type": "gv-tree-group", "index": "a"}
        assert result[1].id == {"type": "gv-overview", "index": "a"}
        assert result[2].id == {"type": "gv-tree-group", "index": "a/b"}
        assert result[3].id == {"type": "gv-overview", "index": "a/b"}
        assert result[4].id == {"type": "gv-nav-item", "index": "a/b/leaf"}

    def test_collapsing_parent_hides_all_descendants(self):
        tree = _build_sidebar_tree(["a/b/leaf1", "a/leaf2"])
        result = _render_tree_node(tree, ["a"], None, {})
        # Only the 'a' group header
        assert len(result) == 1
        assert result[0].id == {"type": "gv-tree-group", "index": "a"}

    def test_collapsing_child_only(self):
        tree = _build_sidebar_tree(["a/b/leaf1", "a/leaf2"])
        result = _render_tree_node(tree, ["a/b"], None, {})
        # a header, a Overview, b header (collapsed), a/leaf2
        assert len(result) == 4
        assert result[0].id == {"type": "gv-tree-group", "index": "a"}
        assert result[1].id == {"type": "gv-overview", "index": "a"}
        assert result[2].id == {"type": "gv-tree-group", "index": "a/b"}
        assert result[3].id == {"type": "gv-nav-item", "index": "a/leaf2"}

    def test_active_leaf_marked(self):
        tree = _build_sidebar_tree(["alpha", "beta"])
        result = _render_tree_node(tree, [], "alpha", {})
        # NavLink uses the `active` prop directly; no manual borderLeft.
        assert result[0].active is True
        assert result[1].active is False

    def test_leaf_label_uses_last_segment(self):
        tree = _build_sidebar_tree(["group/my_plot"])
        result = _render_tree_node(tree, [], None, {})
        # group header, group Overview, then the leaf
        leaf = result[2]
        assert leaf.label == "My Plot"

    def test_indentation_increases_with_depth(self):
        tree = _build_sidebar_tree(["a/b/leaf"])
        result = _render_tree_node(tree, [], None, {})
        # result[0]: a group header (depth=0) — paddingLeft = 0*14+8 = 8
        assert result[0].style["paddingLeft"] == "8px"
        # result[2]: b group header (depth=1) — paddingLeft = 1*14+8 = 22
        assert result[2].style["paddingLeft"] == "22px"
        # result[4]: leaf (depth=2) — paddingLeft = 2*14+12 = 40
        assert result[4].style["paddingLeft"] == "40px"

    def test_chevron_in_left_section(self):
        tree = _build_sidebar_tree(["g/x"])
        expanded = _render_tree_node(tree, [], None, {})
        collapsed = _render_tree_node(tree, ["g"], None, {})
        # leftSection is a dmc.Text wrapper (so the glyph adopts theme
        # color); the actual char is the wrapper's first child.
        assert expanded[0].leftSection.children == "\u25be"
        assert collapsed[0].leftSection.children == "\u25b8"

    def test_empty_tree(self):
        tree = _build_sidebar_tree([])
        result = _render_tree_node(tree, [], None, {})
        assert result == []

    def test_mixed_groups_and_flat(self):
        tree = _build_sidebar_tree(["standalone", "finance/rev", "finance/cost"])
        result = _render_tree_node(tree, [], None, {})
        # Group, then its Overview, then group leaves, then root leaves
        assert result[0].id == {"type": "gv-tree-group", "index": "finance"}
        assert result[1].id == {"type": "gv-overview", "index": "finance"}
        assert result[2].id == {"type": "gv-nav-item", "index": "finance/rev"}
        assert result[3].id == {"type": "gv-nav-item", "index": "finance/cost"}
        assert result[4].id == {"type": "gv-nav-item", "index": "standalone"}

    def test_three_level_nesting(self):
        tree = _build_sidebar_tree(["a/b/c/deep_leaf"])
        result = _render_tree_node(tree, [], None, {})
        # a, a-overview, b, ab-overview, c, abc-overview, leaf
        assert len(result) == 7
        assert result[0].id == {"type": "gv-tree-group", "index": "a"}
        assert result[1].id == {"type": "gv-overview", "index": "a"}
        assert result[2].id == {"type": "gv-tree-group", "index": "a/b"}
        assert result[3].id == {"type": "gv-overview", "index": "a/b"}
        assert result[4].id == {"type": "gv-tree-group", "index": "a/b/c"}
        assert result[5].id == {"type": "gv-overview", "index": "a/b/c"}
        assert result[6].id == {"type": "gv-nav-item", "index": "a/b/c/deep_leaf"}
