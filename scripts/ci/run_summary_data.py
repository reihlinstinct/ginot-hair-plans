"""Standard-library data helpers for the best-effort CI run summary."""

import datetime
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

# Section: Job metadata and durations


def job_durations(env):
    """job name -> seconds, from the public jobs API. Empty on any failure."""
    token = env.get("GITHUB_TOKEN", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    api = env.get("GITHUB_API_URL", "")
    if not repo or not run_id or not api:
        return {}
    url = f"{api}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return {}
    durations = {}
    if not isinstance(data, dict):
        return durations
    for job in data.get("jobs", []):
        if not isinstance(job, dict):
            continue
        started, completed = job.get("started_at"), job.get("completed_at")
        if not started or not completed:
            continue
        try:
            t0 = datetime.datetime.fromisoformat(started)
            t1 = datetime.datetime.fromisoformat(completed)
        except ValueError:
            continue
        durations[job.get("name", "")] = (t1 - t0).total_seconds()
    return durations


def load_job_meta(env):
    """Job metadata parsed from the workflow file named by
    GITHUB_WORKFLOW_REF."""
    ref = env.get("GITHUB_WORKFLOW_REF", "")
    path = ref.split("@")[0].split("/", 2)[-1] if "@" in ref else ""
    if not path or not os.path.exists(path):
        return {}, {}
    try:
        with open(path, encoding="utf-8") as fh:
            return _parse_job_meta_lines(fh)
    except OSError:
        return {}, {}


def _parse_job_meta_lines(lines):
    """(job id -> `if:` expression, job id -> static display name) parsed
    from workflow file lines. Only a nonblank, noncomment column-0 line
    ends the jobs block: blank lines and column-0 comments between jobs
    are common and must not drop the later jobs."""
    conditions = {}
    names = {}
    current = None
    in_jobs = False
    for line in lines:
        if re.match(r"^jobs:\s*(?:#.*)?$", line):
            in_jobs = True
            continue
        if in_jobs:
            m = re.match(
                r"^  (?:'([^']*)'|\"([^\"]*)\"|([A-Za-z0-9_.-]+))"
                r":\s*(?:#.*)?$",
                line,
            )
            if m:
                # YAML permits quoted keys; a quoted job id is the id
                # without its quotes.
                current = m.group(1) or m.group(2) or m.group(3)
                continue
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not line.startswith(" "):
                in_jobs = False
                current = None
                continue
            if stripped and not stripped.startswith("#") and re.match(r"^  \S", line):
                # Unrecognized job-level key (e.g. a quoted id): do not
                # attribute later if:/name: lines to the previous job.
                current = None
                continue
            m = re.match(r"^    if:\s*(.+?)\s*$", line)
            if m and current:
                conditions[current] = m.group(1)
                continue
            m = re.match(r"^    name:\s*(.+?)\s*$", line)
            if m and current:
                name = _job_display_name(m.group(1))
                if name:
                    names[current] = name
    return conditions, names


def _job_display_name(raw):
    """Static job display name from a raw `name:` value, or None.

    Plain-scalar comments are stripped first: a comment containing an
    expression (name: X # ${{ ... }}) does not make the static name
    dynamic; a real expression in the value rejects the name."""
    name = _yaml_plain_scalar(raw)
    return None if "${{" in name else name


def _yaml_plain_scalar(text):
    """Strip a trailing comment from an unquoted YAML scalar: in a plain
    scalar, ` #` starts a comment (name: X (issue #14) parses as X
    (issue). Quoted scalars are returned unchanged."""
    if text.startswith(("'", '"')):
        return text
    return text.split(" #", 1)[0].rstrip()


def duration_for(job_id, durations, display_names):
    """Seconds for one needs-context job id, matched against API display
    names: exact id, then a static workflow `name:`, then matrix children
    ("<id> (<value>)"). None when nothing matches."""
    candidates = [job_id]
    disp = display_names.get(job_id)
    if disp and disp != job_id:
        candidates.append(disp)
    total = 0.0
    found = False
    for cand in candidates:
        if cand in durations:
            total += durations[cand]
            found = True
        else:
            children = [v for n, v in durations.items() if n.startswith(cand + " (")]
            if children:
                total += sum(children)
                found = True
    return total if found else None


def fmt_dur(seconds):
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


# Section: Event ranges and coverage


def load_event(env):
    path = env.get("GITHUB_EVENT_PATH", "")
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def changed_ranges(env, event):
    """(log range, diff range) for this run, or None.

    On pull_request, GITHUB_SHA is the synthetic merge commit, so it
    would add a "Merge ..." entry to the commit list: list commits
    base..head and diff files base...head (merge base) instead. On push,
    before..after serves both."""
    name = env.get("GITHUB_EVENT_NAME", "")
    if name == "pull_request":
        pr = event.get("pull_request") or {}
        base = (pr.get("base") or {}).get("sha", "")
        head = (pr.get("head") or {}).get("sha", "")
        if base and head:
            return f"{base}..{head}", f"{base}...{head}"
        return None
    if name == "push":
        # Use the payload's after, not GITHUB_SHA: on a branch deletion
        # after is all zeros while GITHUB_SHA points at the default
        # branch, which would list and diff unrelated commits.
        before = event.get("before", "")
        after = event.get("after", "")
        if before and set(before) != {"0"} and after and set(after) != {"0"}:
            return f"{before}..{after}", f"{before}..{after}"
    return None


def _no_range_reason(env, event):
    """Why there is no change range, for the summary body."""
    after = event.get("after", "") if isinstance(event, dict) else ""
    if env.get("GITHUB_EVENT_NAME", "") == "push" and after and set(after) == {"0"}:
        return (
            "This push deleted the ref (`after` is all zeros), "
            "so there is no change range to diff."
        )
    return "No change range is available for this run."


def _parse_needs(raw):
    """job id -> needs context dict, from NEEDS_JSON; {} unless the
    payload is an object whose values are objects."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _map_entries(data):
    """(regex, pattern, checks) per well-formed mapping entry; anything
    else in the file is ignored so a broken map degrades the coverage
    section instead of failing the job."""
    mappings = []
    entries = data.get("mappings", []) if isinstance(data, dict) else []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("pattern", "")
        checks = entry.get("checks", [])
        if not isinstance(pattern, str) or not pattern:
            continue
        if not isinstance(checks, list):
            checks = []
        else:
            checks = [c for c in checks if isinstance(c, str) and c]
        try:
            rx = glob_to_regex(pattern)
        except re.error:
            continue
        mappings.append((rx, pattern, checks))
    return mappings


def glob_to_regex(pattern):
    """Translate a gitignore-style glob to a regex. `**` crosses directories,
    `*` and `?` stay within one path segment."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = pattern.find("]", i)
            out.append(pattern[i : j + 1] if j != -1 else "\\[")
            i = j + 1 if j != -1 else i + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


# Section: Literal summary text and raw git records


def md_escape(text):
    """Render untrusted text (commit subjects, file paths, if-conditions)
    as literal text in the step summary: control characters, newlines
    and the Unicode line/paragraph separators (U+2028/U+2029, which
    str.splitlines also splits on) become spaces, HTML metacharacters
    become entities (the summary renders raw HTML), and the Markdown
    metacharacters that could break out of a table cell, code span or
    link are backslash-escaped."""
    text = "".join(
        ch if (ch >= " " and ch not in "\x7f\x85\u2028\u2029") else " " for ch in text
    )
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _log_rows(log):
    """(short hash, subject) per raw git-log record. The byte split on
    b"\n" happens before decoding, so CR/U+2028/U+2029 in a subject
    cannot forge an extra row."""
    for raw in log.split(b"\n") if log else [b"(none)"]:
        line = raw.decode("utf-8", "replace")
        short, _, subject = line.partition(" ")
        yield short, subject


def sh(*args):
    """Raw bytes. Decoding and splitting happen at the call site, so an
    embedded carriage return or invalid UTF-8 in a commit subject or
    filename cannot forge an extra record (text=True would translate
    CR to a line break)."""
    return subprocess.run(list(args), capture_output=True, check=True).stdout
