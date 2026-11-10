"""Archive-fetch probe: pure helpers and the workflow's privacy contract.

No network and no tunnel: the helpers are exercised on literals, and the
workflow file is read as text. The contract under test is that the public run
log carries no body content and that nothing but an encrypted archive is
uploaded.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC = importlib.util.spec_from_file_location(
    "permit_archive_fetch", ROOT / "scripts/vpn/permit_archive_fetch.py"
)
pf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pf)
WORKFLOW = (ROOT / ".github/workflows/permit-archive-fetch.yml").read_text()


# Section: helpers
def test_find_guids_dedups_and_lowercases():
    text = "x 16E57A23-0D2B-464C-ACAD-30895F07B87D y 16e57a23-0d2b-464c-acad-30895f07b87d z"
    assert pf.find_guids(text) == ["16e57a23-0d2b-464c-acad-30895f07b87d"]


def test_archive_procs_need_an_archive_word_nearby_and_skip_denied():
    js = "a" * 500 + "getArchivList:{ProcName:242700460}" + "b" * 500
    js += "c" * 500 + "ProcName:242700461" + "d" * 500
    js += "archiv ProcName:242700447"
    assert pf.archive_procs_in_bundle(js) == [242700460]


def test_shape_prints_key_names_never_values():
    shape = pf.shape_of([{"name": "SECRET", "id": 1}])
    assert shape == "list[1] keys=['id', 'name']"
    assert "SECRET" not in shape
    assert pf.shape_of({"a": 1}) == "dict keys=['a']"


def test_challenge_detection():
    assert pf.is_challenge(b"<html>Please solve this CAPTCHA</html>")
    assert pf.is_challenge(b"Access Denied ... errors.edgesuite.net", markers=False)
    assert not pf.is_challenge(b"var x='recaptcha';", markers=False)
    assert not pf.is_challenge(b"[]")


def test_tik_format_and_variants():
    assert pf.TIK_RE.fullmatch("2025/0147.00")
    assert not pf.TIK_RE.fullmatch("2025/0147.00; rm -rf /")
    assert pf.tik_variants("2025/0147.00") == ["2025/0147.00", "2025/0147"]
    assert pf.tik_variants("2025/0147") == ["2025/0147"]


def test_details_procedure_with_personal_data_is_never_called():
    assert 242700447 in pf.DENIED_PROCS


# Section: workflow privacy contract
def test_workflow_uploads_only_the_encrypted_archive_and_metadata_log():
    block = WORKFLOW.split("Upload the encrypted archive")[1].split("Tear down")[0]
    assert "archive.tar.gz.gpg" in block and "fetch-log.txt" in block
    assert "archive-work" not in block
    assert "retention-days: 3" in block


def test_workflow_pins_the_owner_key_and_encrypts_before_upload():
    assert "D9AD033086DA866791E1616FFFEAA024C5F45CBA" in WORKFLOW
    enc = WORKFLOW.index("--encrypt")
    assert enc < WORKFLOW.index("upload-artifact")
    assert "sudo rm -rf /tmp/archive-work" in WORKFLOW


def test_dispatch_inputs_reach_the_script_through_env_only():
    run_lines = [ln for ln in WORKFLOW.splitlines() if "${{ inputs" in ln]
    assert all(ln.strip().startswith("PROBE_") for ln in run_lines)
    assert (
        "sudo --preserve-env=PROBE_TIK,PROBE_EXTRA_CALLS,PROBE_EXTRA_GUIDS "
        "python3 scripts/vpn/permit_archive_fetch.py"
    ) in WORKFLOW
