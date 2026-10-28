"""#612: every third-party module a test imports at collection time is in requirements.txt.

CI installs only ``requirements.txt`` (plus tool pins) before running pytest, so a
module-level ``import yaml`` that works in a developer venv broke collection on CI.
Imports inside functions (optional browser deps behind ``pytest.importorskip``) are
not collection-time and are not checked here.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Import name -> distribution name, where they differ.
DISTRIBUTION = {"PIL": "pillow", "yaml": "pyyaml"}


def _normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def required_distributions(requirements):
    names = set()
    for line in requirements.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        names.add(_normalize(re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0]))
    return names


def _local_modules(root):
    local = set()
    for base in (root / "tests", root / "src", root):
        local |= {p.stem for p in base.glob("*.py")}
        local |= {p.parent.name for p in base.glob("*/__init__.py")}
    local |= {p.stem for p in (root / "scripts").rglob("*.py")}
    return local


def collection_time_imports(source):
    """Collection-time imports, including module blocks/classes, not functions."""
    names = set()
    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(ast.parse(source))
    return names


def missing_test_dependencies(root):
    required = required_distributions((root / "requirements.txt").read_text())
    local = _local_modules(root)
    missing = set()
    for path in sorted((root / "tests").glob("*.py")):
        for name in collection_time_imports(path.read_text()):
            if name in sys.stdlib_module_names or name in local:
                continue
            if _normalize(DISTRIBUTION.get(name, name)) not in required:
                missing.add(f"{path.name}: {name}")
    return sorted(missing)


def test_collection_time_test_imports_are_in_requirements():
    assert missing_test_dependencies(ROOT) == []


def _repo(tmp_path, test_source, requirements="pytest>=9\n"):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts" / "ci").mkdir(parents=True)
    (tmp_path / "requirements.txt").write_text(requirements)
    (tmp_path / "tests" / "helper.py").write_text("")
    (tmp_path / "scripts" / "ci" / "tool.py").write_text("")
    (tmp_path / "tests" / "test_x.py").write_text(test_source)
    return tmp_path


@pytest.mark.parametrize(
    "source",
    [
        "import yaml\n",
        "from yaml import safe_load\n",
        "import PIL.Image\n",
        "import ezdxf.math\n",
    ],
)
def test_unlisted_module_level_import_is_reported(tmp_path, source):
    assert missing_test_dependencies(_repo(tmp_path, source)) != []


@pytest.mark.parametrize(
    "source,requirements",
    [
        ("import yaml\n", "PyYAML>=6.0.3\n"),
        ("from PIL import Image\n", "Pillow>=13 ; python_version >= '3.10'\n"),
        ("import json, re\nfrom pathlib import Path\n", ""),
        ("import helper\nimport tool\nfrom . import x\n", ""),
        ("def f():\n    from playwright.sync_api import expect\n", ""),
    ],
)
def test_listed_stdlib_local_and_function_level_imports_pass(
    tmp_path, source, requirements
):
    assert missing_test_dependencies(_repo(tmp_path, source, requirements)) == []


@pytest.mark.parametrize('source', [
    'if True:\n    import yaml\n',
    'try:\n    import yaml\nexcept ImportError:\n    pass\n',
    'with open("x"):\n    import yaml\n',
    'for x in []:\n    import yaml\n',
    'class A:\n    import yaml\n',
])
def test_collection_blocks_report_unlisted_imports(tmp_path, source):
    assert missing_test_dependencies(_repo(tmp_path, source)) != []


def test_nested_functions_stay_out_of_collection_imports():
    assert collection_time_imports('if True:\n    def f():\n        import yaml\n') == set()
    assert collection_time_imports('class A:\n    async def f(self):\n        import yaml\n') == set()
