# Accessibility statement

We want ginot-hair-plans to be usable by everyone. Our target is WCAG 2.1 level AA
(Israeli Standard 5568) for user-facing content and interfaces.

## What we do

- Semantic markup and keyboard-navigable interfaces.
- Readable contrast and scalable text.
- The project ships a web site. Automated browser tests run in CI in both Chromium and WebKit, including keyboard interaction and accessibility-relevant assertions on the site UI; visual changes are reviewed on desktop and mobile. A pinned axe-core build scans the four generated page types (index, about, email, accessibility statement) in every site language in CI and fails on any WCAG 2.0/2.1 A/AA violation. Review pages share the same stylesheets and components; they are not scanned individually.
- The site ships an on-site accessibility statement (SI 5568 regulation 35) linked from every page footer.

## Known limitations

- The map is a visual component; its data is also available in the site's text tables.
- Translations into languages other than Hebrew are machine-generated drafts.
- Automated scans are not a manual accessibility audit, and no manual or SI 5568 audit has been performed.

Accessibility work is ongoing. If something blocks you, we want to know.

## Feedback

Report an accessibility problem by opening an issue:
https://github.com/reihlinstinct/ginot-hair-plans/issues/new/choose
If the report is sensitive, use a private security advisory instead:
https://github.com/reihlinstinct/ginot-hair-plans/security/advisories/new
