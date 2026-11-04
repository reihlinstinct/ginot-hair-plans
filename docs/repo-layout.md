# Repository layout contract (Ginot adoption)

`.repo-layout.yml` at the repository root is the enforced layout contract:
required community-standards files, allowed top-level directories, the file
types permitted in each, and the rule that no code lives at the repository
root. The file uses JSON syntax (valid YAML as well) so the checker needs only
the Python standard library and can be reused in every reihlinstinct repo.

## Checker

```sh
python scripts/ci/check_repo_layout.py [--root DIR]
```

Exit 0 when the layout conforms; exit 1 with one `layout violation:` line per
problem otherwise. No network. Violations:

- a missing `required` file or directory (trailing `/` means directory);
- a tracked top-level directory not listed under `directories`;
- a root file matching a `root.deny` pattern (the contract denies `*.py`) or
  no `root.allow` pattern;
- a file under a listed directory matching none of its `allow` patterns
  (patterns match the basename).

A standalone `layout` CI job runs on every PR/push, and the Run summary gate
depends on it. The test suite also runs it via `tests/test_repo_layout.py`, which also pins the empty root
`.py` rule directly.

## Changing the layout

A new kind of file, a new top-level directory, or a new required file means
updating `.repo-layout.yml` in the same PR. Placement is decided before a
file is created, per CONTRIBUTING.md; the human-readable map is the
directory purposes recorded in `.repo-layout.yml`.

## Rollout

geni-uploader carries the reference implementation. Other reihlinstinct repos
adopt the same checker with their own contract file; each adoption is its own
issue + PR with green CI and independent review.
