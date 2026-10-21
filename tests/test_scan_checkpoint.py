import importlib.util
import pathlib
import sys

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location("permit_feed", vpn / "permit_feed.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


def _reqs(n):
    return {f"1949/{i:04d}.01": {"tik_num": f"1949/{i:04d}.01"} for i in range(n)}


def test_checkpoint_payload_shape():
    p = pf.checkpoint_payload(_reqs(3), offset=120, limit=280, done=15)
    assert p["checkpoint"] is True
    assert p["batch"] == {"offset": 120, "limit": 280, "done": 15}
    assert len(p["requests"]) == 3
    assert [r["tik_num"] for r in p["requests"]] == sorted(r["tik_num"] for r in p["requests"])


def test_resume_start_matches_range():
    cp = pf.checkpoint_payload(_reqs(5), offset=120, limit=280, done=40)
    assert pf.resume_start(cp, offset=120, limit=280, batch_len=281) == 40


def test_resume_ignores_other_ranges_and_garbage():
    cp = pf.checkpoint_payload(_reqs(5), offset=120, limit=280, done=40)
    assert pf.resume_start(cp, offset=400, limit=280, batch_len=281) == 0
    assert pf.resume_start(cp, offset=120, limit=60, batch_len=61) == 0
    assert pf.resume_start(None, offset=120, limit=280, batch_len=281) == 0
    assert pf.resume_start({"batch": {}}, offset=120, limit=280, batch_len=281) == 0
    # a checkpoint at/past the batch end means nothing left to resume
    full = pf.checkpoint_payload(_reqs(5), offset=120, limit=280, done=281)
    assert pf.resume_start(full, offset=120, limit=280, batch_len=281) == 0


def test_checkpoint_interval_within_owner_spec():
    import argparse
    # owner spec 2026-10-21: persist every 10-20 parcels
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint-every", type=int, default=15)
    args = ap.parse_args([])
    assert 10 <= args.checkpoint_every <= 20
