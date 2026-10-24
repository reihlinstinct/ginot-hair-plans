from pathlib import Path


def test_probe_step_preserves_probe_tik_through_sudo():
    """Regression (#406): plain `sudo python3` resets the environment, so the
    PROBE_TIK dispatch input never reached the script and run 40110177057
    silently probed the default tik. The step must preserve it explicitly."""
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/permit-publication-probe.yml"
    ).read_text()
    assert "PROBE_TIK: ${{ inputs.tik }}" in workflow
    assert "sudo --preserve-env=PROBE_TIK python3 scripts/vpn/permit_publication_probe.py" in workflow
    unguarded = [
        line
        for line in workflow.splitlines()
        if "sudo python3 scripts/vpn/permit_publication_probe.py" in line
        and "--preserve-env=PROBE_TIK" not in line
    ]
    assert not unguarded
