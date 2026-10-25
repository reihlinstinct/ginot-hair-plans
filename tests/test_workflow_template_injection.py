"""Regression: no attacker-influenceable GitHub context interpolated directly
inside run: blocks of ci.yml (issue #475; zizmor template-injection class).

Exploitability note: github.base_ref is only controllable by someone who can
create branches here, but the class is enforced regardless - env indirection
is the repo pattern (#473 step)."""

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent

# Contexts an external or insider actor can influence, dot and bracket forms:
#   github.base_ref / github['base_ref'] / github.head_ref / github['head_ref']
#   github.event.<pr/issue/comment/...> / github.event['pull_request'] etc.
RISKY = re.compile(
    r"\$\{\{(?:(?!\}\}).)*?\bgithub\s*(?:"
    r"\.\s*(?:base_ref|head_ref)\b"
    r"|\[\s*['\"](?:base_ref|head_ref)['\"]\s*\]"
    r"|(?:\.\s*event|\[\s*['\"]event['\"]\s*\])\s*"
    r"(?:\.\s*(?:pull_request|issue|issue_comment|comment|review|discussion)\b"
    r"|\[\s*['\"](?:pull_request|issue|issue_comment|comment|review|discussion)['\"]\s*\])"
    r")"
)

RUN_LINE = re.compile(r"^(\s*)(?:-\s*)?run:\s*(.*)$")
BLOCK_MARKERS = {"|", "|-", "|+", ">", ">-", ">+"}


def scan_lines(lines):
    """Return [(lineno, matched_context)] for risky interpolations inside
    run: bodies. Handles block scalars (run: |) and single-line runs; env:
    values are the SAFE location and are not scanned. Folded scalars
    (run: >) join lines with spaces, so block content is ALSO scanned
    joined - a risky expression split across lines only matches folded.
    Block membership is decided by indent BEFORE matching a new run: key,
    so a shell line inside the block that starts with "run:" stays content."""
    hits = []
    in_run = False
    content_indent = None
    block_start = 0
    block_lines = []

    def flush_block():
        if block_lines and not any(ln > block_start for ln, _ in hits):
            m = RISKY.search(" ".join(block_lines))
            if m:
                hits.append((block_start, m.group(0)))
        block_lines.clear()

    for i, line in enumerate(lines, 1):
        if in_run:
            if not line.strip():
                continue  # blank line stays inside the block
            indent = len(line) - len(line.lstrip())
            if content_indent is None:
                content_indent = indent  # first block line sets the baseline
            if indent >= content_indent:
                block_lines.append(line.strip())
                m = RISKY.search(line)
                if m:
                    hits.append((i, m.group(0)))
                continue
            flush_block()
            in_run = False  # back at step level (env:, if:, next step, ...)
        m_run = RUN_LINE.match(line)
        if m_run:
            rest = re.sub(r"\s+#.*$", "", m_run.group(2)).strip()
            if rest in BLOCK_MARKERS:
                in_run = True
                content_indent = None
                block_start = i
                continue
            if rest:  # single-line run: scan the comment-stripped command
                m = RISKY.search(rest)
                if m:
                    hits.append((i, m.group(0)))
    flush_block()
    return hits


def test_no_risky_interpolation_in_ci_run_blocks():
    lines = (ROOT / ".github" / "workflows" / "ci.yml").read_text().splitlines()
    hits = scan_lines(lines)
    assert hits == [], f"risky GitHub context in ci.yml run blocks: {hits}"


def test_scanner_catches_block_run():
    lines = [
        "      - run: |",
        "          git fetch origin \"${{ github.base_ref }}\"",
    ]
    assert scan_lines(lines) != []


def test_scanner_catches_single_line_run():
    lines = ['      - run: git fetch origin "${{ github.base_ref }}"']
    assert scan_lines(lines) != []


def test_scanner_catches_bracket_form():
    lines = ['      - run: echo "${{ github[\'base_ref\'] }}"']
    assert scan_lines(lines) != []
    lines_ev = ['      - run: echo "${{ github.event[\'pull_request\'].number }}"']
    assert scan_lines(lines_ev) != []


def test_scanner_ignores_env_values():
    lines = [
        "      - run: |",
        "          git fetch origin \"$BASE_REF\"",
        "        env:",
        "          BASE_REF: ${{ github.base_ref }}",
    ]
    assert scan_lines(lines) == []


def test_scanner_ignores_repository_constant():
    lines = ['      - run: echo "repo is ${{ github.repository }}"']
    assert scan_lines(lines) == []


def test_scanner_catches_commented_block_header():
    lines = [
        "      - run: | # fetch the base ref",
        '          git fetch origin "${{ github.base_ref }}"',
    ]
    assert scan_lines(lines) != []


def test_scanner_catches_nested_expression():
    lines = ["""      - run: echo "${{ format('{0}', github.base_ref) }}" """]
    assert scan_lines(lines) != []


def test_scanner_catches_bracket_event_access():
    lines = ["""      - run: echo "${{ github['event'].pull_request.title }}" """]
    assert scan_lines(lines) != []


def test_scanner_ignores_unrelated_github_word():
    # a non-risky output name containing "github" must not match
    lines = ["""      - run: echo "${{ steps.x.outputs.github_url }}" """]
    assert scan_lines(lines) == []


def test_scanner_catches_folded_split_expression():
    # YAML folds run: > lines with spaces, so a split expression becomes a
    # valid single-line command; only the joined scan can catch it.
    lines = [
        "      - run: >",
        '          git fetch origin "${{',
        '          github.base_ref }}"',
    ]
    assert scan_lines(lines) != []


def test_scanner_ignores_comment_after_single_line_command():
    lines = ["      - run: echo safe # ${{ github.base_ref }}"]
    assert scan_lines(lines) == []


def test_scanner_block_content_run_key_stays_in_block():
    # a shell line starting with "run:" inside a block scalar is content,
    # not a new step key; the block must keep scanning after it
    lines = [
        "      - run: |",
        "          run: echo starting",
        '          git fetch origin "${{ github.base_ref }}"',
    ]
    assert scan_lines(lines) != []
