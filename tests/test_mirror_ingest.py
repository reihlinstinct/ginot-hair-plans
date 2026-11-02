import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "mirror_ingest",
    pathlib.Path(__file__).parent.parent / "scripts" / "mirror_ingest.py",
)
mirror_ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror_ingest)


def test_parcel_interval():
    assert mirror_ingest.parcel_interval({"מחלקה": "126", "עד חלקה": "126"}) == (
        set(),
        (126, 126),
    )
    assert mirror_ingest.parcel_interval({"מחלקה": "49", "עד חלקה": "50"}) == (
        set(),
        (49, 50),
    )


def test_parcel_interval_garbage_range_degrades_to_points():
    assert mirror_ingest.parcel_interval({"מחלקה": "216", "עד חלקה": "2"}) == (
        {216, 2},
        None,
    )
    assert mirror_ingest.parcel_interval({"מחלקה": "", "עד חלקה": ""}) == (set(), None)


def test_huge_common_property_range_matches_by_interval():
    parcels = {30002: {4000, 6000}}
    row = {"גוש": "30002", "מחלקה": "22", "עד חלקה": "5032"}
    _, hits = mirror_ingest.matching_parcels(row, parcels)
    assert hits == [4000]


def test_matching_parcels_intersects_council_set():
    parcels = {30025: {126, 127, 130}}
    row = {"גוש": "30025", "מחלקה": "125", "עד חלקה": "128"}
    gush, hits = mirror_ingest.matching_parcels(row, parcels)
    assert gush == 30025 and hits == [126, 127]
    row = {"גוש": "30025", "מחלקה": "1", "עד חלקה": "2"}
    _, hits = mirror_ingest.matching_parcels(row, parcels)
    assert hits == []


def test_map_record_drops_personal_and_shapes_fields():
    row = {
        "מספר תיק": "2026/0001.00",
        "סטטוס": "נפתח תיק רישוי",
        "תאריך סטטוס": "2026-10-01T00:00:00",
        "סוג בקשה": "בניה חדשה",
        "מהות הבקשה": " בניין  ",
        "רחוב": "י. אלפסי",
        "מספר בית": "9",
        "שכונה": "גינות העיר",
        "תאריך דגימה": "2026-10-17T21:55:48Z",
        "first_seen": "2026-10-17T21:55:58+00:00",
        "last_seen": None,
        "בעלי עניין": "שם פרטי (בעל הנכס)",
    }
    rec = mirror_ingest.map_record(row, 30025, [126])
    assert rec["tik_num"] == "2026/0001.00"
    assert rec["status_date"] == "2026-10-01"
    assert rec["address"] == "י. אלפסי 9 גינות העיר"
    assert rec["mahut"] == "בניין"
    assert "שם פרטי" not in str(rec) and "בעלי עניין" not in rec


def test_diff_records():
    old = [
        {"tik_num": "1", "status": "a", "status_date": "2026-01-01"},
        {"tik_num": "2", "status": "a", "status_date": "2026-01-01"},
        {"tik_num": "3", "status": "a", "status_date": "2026-01-01"},
    ]
    new = [
        {"tik_num": "2", "status": "b", "status_date": "2026-02-01"},
        {"tik_num": "3", "status": "a", "status_date": "2026-01-01"},
        {"tik_num": "4", "status": "a", "status_date": "2026-01-01"},
    ]
    d = mirror_ingest.diff_records(old, new)
    assert d == {"new_tiks": ["4"], "changed_tiks": ["2"], "gone_tiks": ["1"]}


def test_preserve_enriched_fields_keeps_publication_dates():
    old = [
        {
            "tik_num": "A/1",
            "publication_start": "2026-10-18",
            "publication_end_planned": "2026-11-24",
        },
        {"tik_num": "B/2", "publication_start": "", "publication_end_planned": ""},
        {"tik_num": "C/3", "status": "x"},
    ]
    new = {t: {"tik_num": t} for t in ("A/1", "B/2", "C/3", "D/4")}
    mirror_ingest.preserve_enriched_fields(new, old)
    assert new["A/1"]["publication_start"] == "2026-10-18"
    assert new["A/1"]["publication_end_planned"] == "2026-11-24"
    # empty-string markers (enriched, no dates found) survive too, so the
    # include-unenriched backfill does not refetch them
    assert new["B/2"]["publication_start"] == ""
    assert "publication_start" not in new["C/3"]
    assert "publication_start" not in new["D/4"]


def mock_pages(monkeypatch, pages):
    import json
    import types
    from urllib.parse import parse_qs, urlparse

    calls = []
    iterator = iter(pages)

    def fetch(command, **kwargs):
        params = parse_qs(urlparse(command[-1]).query)
        assert params["sort"] == ["מספר תיק asc"]
        assert command[:2] == ["curl", "-fsS"]
        assert kwargs["check"] is False
        calls.append(int(params["offset"][0]))
        total, keys = next(iterator)
        body = {
            "success": True,
            "result": {"total": total, "records": [{"מספר תיק": k} for k in keys]},
        }
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(body))

    monkeypatch.setattr(mirror_ingest.subprocess, "run", fetch)
    monkeypatch.setattr(mirror_ingest.time, "sleep", lambda _: None)
    monkeypatch.setattr(mirror_ingest, "PAGE", 2)
    return calls


def test_fetch_rows_ordered_unique_and_short_page_offsets(monkeypatch):
    calls = mock_pages(monkeypatch, [(3, ["A"]), (3, ["B", "C"])])
    assert len(mirror_ingest.fetch_rows([30007])) == 3
    assert calls == [0, 1]


def test_fetch_rows_empty_dataset(monkeypatch):
    mock_pages(monkeypatch, [(0, [])])
    assert mirror_ingest.fetch_rows([30007]) == []


def test_fetch_rows_rejects_overlap_that_raw_count_mistakes_for_completion(monkeypatch):
    import pytest

    mock_pages(monkeypatch, [(4, ["A", "B"]), (4, ["B", "C"])])
    with pytest.raises(RuntimeError, match="duplicate"):
        mirror_ingest.fetch_rows([30007])


def test_fetch_rows_rejects_ignored_sort(monkeypatch):
    import pytest

    mock_pages(monkeypatch, [(2, ["B", "A"])])
    with pytest.raises(RuntimeError, match="sort not respected"):
        mirror_ingest.fetch_rows([30007])


def test_fetch_rows_rejects_changed_total(monkeypatch):
    import pytest

    mock_pages(monkeypatch, [(3, ["A", "B"]), (4, ["C", "D"])])
    with pytest.raises(RuntimeError, match="total changed"):
        mirror_ingest.fetch_rows([30007])


def test_fetch_rows_rejects_premature_empty_page(monkeypatch):
    import pytest

    mock_pages(monkeypatch, [(3, ["A", "B"]), (3, [])])
    with pytest.raises(RuntimeError, match="premature empty"):
        mirror_ingest.fetch_rows([30007])


def test_fetch_rows_rejects_invalid_key_total_and_count(monkeypatch):
    import pytest

    for total, keys, message in [
        (1, [None], "missing"),
        (None, [], "invalid mirror total"),
        (True, [], "invalid mirror total"),
        (1, ["A", "B"], "exceeds total"),
    ]:
        mock_pages(monkeypatch, [(total, keys)])
        with pytest.raises(RuntimeError, match=message):
            mirror_ingest.fetch_rows([30007])


def test_fetch_rows_transport_and_api_failure_do_not_echo_bodies(monkeypatch):
    import json
    import types

    import pytest

    for code, body, message in [
        (22, "PRIVATE RESPONSE", "transport failed"),
        (0, json.dumps({"success": False, "error": "PRIVATE RESPONSE"}), "API error"),
    ]:
        monkeypatch.setattr(
            mirror_ingest.subprocess,
            "run",
            lambda *a, code=code, body=body, **k: types.SimpleNamespace(
                returncode=code, stdout=body
            ),
        )
        with pytest.raises(RuntimeError, match=message) as error:
            mirror_ingest.fetch_rows([30007])
        assert "PRIVATE RESPONSE" not in str(error.value)


def test_main_preserves_existing_output_when_collection_fails(monkeypatch, tmp_path):
    import sys

    import pytest

    out, diff = tmp_path / "mirror.json", tmp_path / "diff.json"
    out.write_text('{"requests": []}')
    diff.write_text("previous diff")
    monkeypatch.setattr(
        sys, "argv", ["mirror_ingest.py", "--out", str(out), "--diff-out", str(diff)]
    )
    monkeypatch.setattr(mirror_ingest, "load_parcels", lambda _: {30007: {133}})

    def fail(_):
        raise RuntimeError("duplicate mirror permit key at offset 500")

    monkeypatch.setattr(mirror_ingest, "fetch_rows", fail)
    with pytest.raises(RuntimeError, match="duplicate"):
        mirror_ingest.main()
    assert out.read_text() == '{"requests": []}'
    assert diff.read_text() == "previous diff"


def test_fetch_rows_rejects_keys_equal_after_stripping(monkeypatch):
    import pytest

    # map_record strips tik_num later, so raw-distinct keys that collapse to
    # the same normalized key would silently overwrite downstream.
    mock_pages(monkeypatch, [(2, ["A", "A "])])
    with pytest.raises(RuntimeError, match="duplicate"):
        mirror_ingest.fetch_rows([1])


def test_main_refuses_empty_ingest_over_existing_data(monkeypatch, tmp_path):
    import sys

    import pytest

    out, diff = tmp_path / "mirror.json", tmp_path / "diff.json"
    out.write_text('{"requests": [{"tik_num": "A"}]}')
    diff.write_text("previous diff")
    monkeypatch.setattr(
        sys, "argv", ["mirror_ingest.py", "--out", str(out), "--diff-out", str(diff)]
    )
    monkeypatch.setattr(mirror_ingest, "load_parcels", lambda _: {30007: {133}})
    monkeypatch.setattr(mirror_ingest, "fetch_rows", lambda _: [])
    with pytest.raises(RuntimeError, match="zero council records"):
        mirror_ingest.main()
    assert out.read_text() == '{"requests": [{"tik_num": "A"}]}'
    assert diff.read_text() == "previous diff"


def test_main_allow_empty_flag_and_fresh_start(monkeypatch, tmp_path):
    import json
    import sys

    out, diff = tmp_path / "mirror.json", tmp_path / "diff.json"
    monkeypatch.setattr(mirror_ingest, "load_parcels", lambda _: {30007: {133}})
    monkeypatch.setattr(mirror_ingest, "fetch_rows", lambda _: [])

    # Fresh start (no existing data): an empty ingest writes normally.
    monkeypatch.setattr(
        sys, "argv", ["mirror_ingest.py", "--out", str(out), "--diff-out", str(diff)]
    )
    assert mirror_ingest.main() == 0
    assert json.loads(out.read_text())["requests"] == []

    # Existing data + explicit --allow-empty: the wipe is a stated choice.
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mirror_ingest.py",
            "--out",
            str(out),
            "--diff-out",
            str(diff),
            "--allow-empty",
        ],
    )
    assert mirror_ingest.main() == 0
    assert json.loads(out.read_text())["requests"] == []
