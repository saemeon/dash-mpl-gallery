"""Tests for the branch-click gallery view helpers.

Covers ``_descend_to_group``, ``_count_descendant_leaves``,
``_leaf_card``, ``_subfolder_card``, and ``_render_gallery_view``.
"""

from __future__ import annotations

from gallery_viewer.gallery import (
    _build_sidebar_tree,
    _count_descendant_leaves,
    _descend_to_group,
    _leaf_card,
    _render_gallery_view,
    _subfolder_card,
)


# ---------------------------------------------------------------------------
# _descend_to_group
# ---------------------------------------------------------------------------


class TestDescendToGroup:
    def test_empty_path_returns_root(self):
        tree = _build_sidebar_tree(["a", "g/x"])
        assert _descend_to_group(tree, "") is tree

    def test_single_segment(self):
        tree = _build_sidebar_tree(["g/x", "g/y"])
        node = _descend_to_group(tree, "g")
        assert node is not None
        assert node["__leaves__"] == ["g/x", "g/y"]

    def test_nested_path(self):
        tree = _build_sidebar_tree(["a/b/c"])
        node = _descend_to_group(tree, "a/b")
        assert node is not None
        assert node["__leaves__"] == ["a/b/c"]

    def test_missing_segment_returns_none(self):
        tree = _build_sidebar_tree(["g/x"])
        assert _descend_to_group(tree, "missing") is None
        assert _descend_to_group(tree, "g/nope") is None


# ---------------------------------------------------------------------------
# _count_descendant_leaves
# ---------------------------------------------------------------------------


class TestCountDescendantLeaves:
    def test_flat(self):
        tree = _build_sidebar_tree(["a", "b", "c"])
        assert _count_descendant_leaves(tree) == 3

    def test_nested(self):
        tree = _build_sidebar_tree(["a", "g/x", "g/y", "g/sub/z"])
        # 1 root + 2 in g + 1 in g/sub
        assert _count_descendant_leaves(tree) == 4

    def test_subgroup_only(self):
        tree = _build_sidebar_tree(["a", "g/x", "g/y", "g/sub/z"])
        g_node = _descend_to_group(tree, "g")
        assert g_node is not None
        # 2 direct + 1 in sub
        assert _count_descendant_leaves(g_node) == 3

    def test_empty_tree(self):
        assert _count_descendant_leaves({"__leaves__": []}) == 0


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


class TestLeafCard:
    def test_id_uses_full_name(self):
        card = _leaf_card("finance/revenue", "")
        assert card.id == {"type": "gv-nav-item", "index": "finance/revenue"}

    def test_label_uses_last_segment_titled(self):
        card = _leaf_card("finance/q4_revenue", "")
        # second child is the title div
        title = card.children[1]
        assert title.children == "Q4 Revenue"

    def test_description_renders(self):
        card = _leaf_card("a", "Quarterly revenue chart")
        desc = card.children[2]
        assert desc.children == "Quarterly revenue chart"


class TestSubfolderCard:
    def test_id_uses_group_path(self):
        card = _subfolder_card("finance", 3)
        assert card.id == {"type": "gv-overview", "index": "finance"}

    def test_count_text_singular(self):
        card = _subfolder_card("finance", 1)
        assert card.children[2].children == "1 item"

    def test_count_text_plural(self):
        card = _subfolder_card("finance", 5)
        assert card.children[2].children == "5 items"

    def test_count_text_zero(self):
        card = _subfolder_card("finance", 0)
        assert card.children[2].children == "0 items"


# ---------------------------------------------------------------------------
# _render_gallery_view
# ---------------------------------------------------------------------------


class TestRenderGalleryView:
    def test_root_with_mixed_content(self):
        tree = _build_sidebar_tree(["alpha", "g/x", "g/y"])
        view = _render_gallery_view(tree, "", {})
        # html.Div containing [title, grid]
        grid = view.children[1]
        cards = grid.children
        # one subfolder card (g) + one leaf card (alpha)
        assert len(cards) == 2
        assert cards[0].id == {"type": "gv-overview", "index": "g"}
        assert cards[1].id == {"type": "gv-nav-item", "index": "alpha"}

    def test_subgroup_renders_only_its_contents(self):
        tree = _build_sidebar_tree(["alpha", "g/x", "g/y", "g/sub/z"])
        view = _render_gallery_view(tree, "g", {})
        cards = view.children[1].children
        # one subfolder (g/sub) + two leaves (g/x, g/y)
        assert len(cards) == 3
        assert cards[0].id == {"type": "gv-overview", "index": "g/sub"}
        assert cards[1].id == {"type": "gv-nav-item", "index": "g/x"}
        assert cards[2].id == {"type": "gv-nav-item", "index": "g/y"}

    def test_leaf_descriptions_propagate(self):
        tree = _build_sidebar_tree(["alpha"])
        view = _render_gallery_view(tree, "", {"alpha": "the alpha"})
        leaf_card = view.children[1].children[0]
        assert leaf_card.children[2].children == "the alpha"

    def test_missing_group_returns_placeholder(self):
        tree = _build_sidebar_tree(["a"])
        view = _render_gallery_view(tree, "missing", {})
        # html.Span with text starting "Group not found"
        assert "Group not found" in view.children

    def test_empty_group_returns_placeholder(self):
        tree = {"__leaves__": [], "empty": {"__leaves__": []}}
        view = _render_gallery_view(tree, "empty", {})
        assert view.children == "Empty group"

    def test_subfolder_count_is_recursive(self):
        tree = _build_sidebar_tree(["g/a", "g/b", "g/sub/c", "g/sub/d"])
        view = _render_gallery_view(tree, "", {})
        # root has one subfolder card (g) with 4 descendants
        sub_card = view.children[1].children[0]
        assert sub_card.children[2].children == "4 items"
