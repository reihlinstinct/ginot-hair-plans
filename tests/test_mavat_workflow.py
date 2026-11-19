from pathlib import Path


def test_mavat_result_waits_for_the_guarded_automerge_without_mutating_the_head():
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/mavat-watch.yml"
    ).read_text()
    assert "gh pr create" in workflow
    assert "awaiting the guarded data automerge" in workflow
    assert "gh pr update-branch" not in workflow
    assert "gh pr merge" not in workflow
    assert "--admin" not in workflow
