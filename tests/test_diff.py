from ginot import diff


def row(num, st, name="n"):
    return {"pl_number": num, "pl_name": name, "station_desc": st, "mavat_url": "u"}


def test_new_removed_changed():
    old = [row("1", "אישור"), row("2", "הפקדה")]
    new = [row("2", "אישור"), row("3", "בבדיקה תכנונית")]
    ev = diff.diff_snapshots(old, new)
    kinds = {(e["kind"], e["pl_number"]) for e in ev}
    assert ("new", "3") in kinds
    assert ("removed", "1") in kinds
    assert ("status_change", "2") in kinds
    sc = [e for e in ev if e["kind"] == "status_change"][0]
    assert sc["from"] == "הפקדה" and sc["to"] == "אישור"


def test_no_changes():
    assert diff.diff_snapshots([row("1", "אישור")], [row("1", "אישור")]) == []
