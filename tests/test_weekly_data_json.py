"""#591/#559: the freshness gate covers the public data API; the
weekly reconciliation flag still repairs it explicitly."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_include_data_json_detects_and_repairs_stale_reconciled_api(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "weekly_fresh", ROOT / "scripts/ci/check_docs_fresh.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.html").write_text("עודכן: 2026-10-27")
    (docs / "data.json").write_text(
        json.dumps({"generated": "2026-10-27", "permits": []})
    )

    def fake_render(out, date):
        out.mkdir(parents=True)
        (out / "index.html").write_text("עודכן: 2026-10-27")
        (out / "data.json").write_text(
            json.dumps({"generated": date, "permits": [{"tik_num": "new"}]})
        )

    monkeypatch.setattr(module, "render", fake_render)
    # #559: data.json is covered by default now that permit-feed batches
    # refresh its permits[] in the same run; --include-data-json remains
    # accepted for the weekly workflow's explicit regenerate step.
    assert any("data.json" in error for error in module.check(docs))
    assert any(
        "data.json" in error for error in module.check(docs, include_data_json=True)
    )
    assert module.check(docs, write=True, include_data_json=True) == []
    assert module.check(docs, include_data_json=True) == []
    assert json.loads((docs / "data.json").read_text())["permits"] == [
        {"tik_num": "new"}
    ]
