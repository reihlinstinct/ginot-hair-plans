# Version and release standard

The single version source is `src/ginot/__init__.py::__version__`.
Current prepared version:0.2.0, following the existing0.1.0 package baseline.
Continuous deployment stays independent; releases are lightweight labeled snapshots.

- Bug fix: increment PATCH (0.2.0 -> 0.2.1).
- Feature: increment MINOR and reset PATCH (0.2.1 -> 0.3.0).
- Breaking compatibility: increment MAJOR and reset others (0.3.0 -> 1.0.0).
- Keep existing APIs compatible unless the release explicitly documents a break.
- Each approved release gets annotated git tag `vMAJOR.MINOR.PATCH`, a dated
  CHANGELOG section, and release notes in Hebrew and English under releases/.
- The root, About and review footers show the version from the same source.
- Data refreshes alone do not bump the product version.
- Prepare version/notes/tests in an issue and PR. Green CI is required.
- Standing authority permits frequent tested releases, including several per day.
  Do not wait for a manual approval ceremony when CI is green.
- Tag the reviewed merge commit, publish its bilingual notes,
  record the release date and verify the displayed version. Do not tag unrelated
  later changes. No release action may trigger a data scan without its approval.

## Lightweight automation

Use `scripts/releases/prepare.py --prs merged-prs.json --date YYYY-MM-DD` with
merged PR metadata since the previous tag. It chooses major/minor/patch from
`breaking`/`release:major`, `enhancement`/`feature`/`release:minor`, otherwise
patch; updates the one version source, bilingual notes, CHANGELOG and committed
footers together. Review titles for private information before publication.
CI remains the release gate; the helper never pushes tags or delays deployment.
