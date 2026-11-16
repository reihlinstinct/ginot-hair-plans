"""The UI-discovery mode does not require a precomputed document list."""

import ast
from pathlib import Path


def test_missing_optional_list_is_allowed_only_for_clickdocs():
    source = Path("scripts/vpn/mavat_docs.py").read_text()
    tree = ast.parse(source)
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and "FileNotFoundError" in ast.unparse(node.test)
    ]
    assert len(guarded) == 1
    test = ast.unparse(guarded[0].test)
    assert "MAVAT_FETCH_MODE" in test and "clickdocs" in test
    assert any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and node.value.value == 1
        for stmt in guarded[0].orelse
        for node in ast.walk(stmt)
    )
