"""Stage scoped public watch data for independent review; never self-merge."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/
import _src_path  # noqa: F401  (shared bootstrap: adds the repo src/ to sys.path)

from ginot.publications import write_projection

FILES = (
    "data/publications_active.json",
    "data/publications_new_latest.json",
    "docs/publications_active.json",
    "docs/index.json",
    "docs/permits-default.html",
)


def staged_files() -> list[str]:
    # Every non-default language's default fragment regenerates with the root
    # one (render_permits_page.py), so stage it too (i18n pages, #942).
    from ginot import i18n

    return list(FILES) + [
        f"docs/{code}/permits-default.html"
        for code in i18n.lang_codes()
        if code != i18n.default_lang()
    ]


def gh(*args, payload=None):
    cmd = ["gh", *args]
    if payload is not None:
        cmd += ["--input", "-"]
    try:
        result = subprocess.run(
            cmd,
            input=json.dumps(payload) if payload is not None else None,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        # Never echo stderr or command/payload: credentials and source data may
        # occur there. Retain only a bounded numeric HTTP status, when present.
        status = re.search(r"\bHTTP ([1-5][0-9]{2})\b", exc.stderr or "")
        detail = f"; HTTP {status.group(1)}" if status else "; HTTP status unavailable"
        raise RuntimeError(
            f"GitHub API command failed (exit {exc.returncode}{detail})"
        ) from None
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def pending_publication_prs(repo):
    # Paginated same-repo heads only. API/JSON errors propagate: fail closed.
    prs = gh(
        "api",
        "--paginate",
        "--slurp",
        f"repos/{repo}/pulls?state=open&base=main&per_page=100",
    )
    if not isinstance(prs, list) or any(not isinstance(page, list) for page in prs):
        raise RuntimeError("Invalid pending PR response")
    return [
        pr["number"]
        for page in prs
        for pr in page
        if ((pr.get("head") or {}).get("repo") or {}).get("full_name") == repo
        and (pr.get("head") or {}).get("ref", "").startswith("publications/")
    ]


def main():
    subprocess.run(
        ["python3", "scripts/build_site_index.py", "data", "docs/index.json"],
        check=True,
    )
    # Public deadline-only projection follows every daily publication refresh.
    if not write_projection(
        "data/publications_active.json", "docs/publications_active.json"
    ):
        raise RuntimeError(
            "Publication source unavailable; refusing to publish a data PR"
        )
    # #629: daily evidence changes the default subset as well as the projection.
    subprocess.run(
        ["python3", "scripts/render_permits_page.py", "--default-only"], check=True
    )
    repo = os.environ["GITHUB_REPOSITORY"]
    pending = pending_publication_prs(repo)
    if pending:
        print(f"publication PR(s) awaiting review: {pending}; no new PR or head update")
        return
    root = f"repos/{repo}"
    base = gh("api", f"{root}/git/ref/heads/main")["object"]["sha"]
    tree = gh("api", f"{root}/git/commits/{base}")["tree"]["sha"]
    entries = [
        {
            "path": path,
            "mode": "100644",
            "type": "blob",
            "content": Path(path).read_text(encoding="utf-8"),
        }
        for path in staged_files()
    ]
    updated = gh(
        "api", f"{root}/git/trees", payload={"base_tree": tree, "tree": entries}
    )
    if updated["sha"] == tree:
        print("no publication changes")
        return
    commit = gh(
        "api",
        f"{root}/git/commits",
        payload={
            "message": "Daily publication baseline refresh (refs #527)",
            "tree": updated["sha"],
            "parents": [base],
        },
    )
    branch = (
        "publications/"
        + os.environ["GITHUB_RUN_ID"]
        + "-"
        + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    )
    gh(
        "api",
        f"{root}/git/refs",
        payload={"ref": "refs/heads/" + branch, "sha": commit["sha"]},
    )
    pr = gh(
        "api",
        f"{root}/pulls",
        payload={
            "title": "Daily publications refresh",
            "head": branch,
            "base": "main",
            "body": "Automated public publication baseline and alert payload (refs #527). Text-only data update. Requires independent and exact-head Claude reviews, green CI and eligible approval before normal manual merge.",
        },
    )
    print(pr["html_url"], flush=True)
    print(
        "awaiting independent and exact-head Claude reviews, green CI and eligible approval; "
        "staged PR is not publication",
        flush=True,
    )


if __name__ == "__main__":
    main()
