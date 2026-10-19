"""Snapshot diff: which plans are new / removed / changed status since last run."""


def diff_snapshots(old_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    old = {r["pl_number"]: r for r in old_rows}
    new = {r["pl_number"]: r for r in new_rows}
    events = []
    for num, r in new.items():
        if num not in old:
            events.append({"kind": "new", "pl_number": num, "pl_name": r["pl_name"],
                           "station_desc": r["station_desc"], "mavat_url": r["mavat_url"]})
        elif old[num]["station_desc"] != r["station_desc"]:
            events.append({"kind": "status_change", "pl_number": num, "pl_name": r["pl_name"],
                           "from": old[num]["station_desc"], "to": r["station_desc"],
                           "mavat_url": r["mavat_url"]})
    for num, r in old.items():
        if num not in new:
            events.append({"kind": "removed", "pl_number": num, "pl_name": r["pl_name"],
                           "station_desc": r["station_desc"], "mavat_url": r["mavat_url"]})
    return events
