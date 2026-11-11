"""Shared bootstrap for repo scripts: add the repo's src/ to sys.path.

Imported for its side effect so every script resolves the ginot package the
same way, instead of each computing the path with its own os.path/Path
spell (#972):

    scripts/*.py:            import _src_path  # noqa: F401
    scripts/<sub>/*.py:      sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                             import _src_path  # noqa: F401
"""

import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
