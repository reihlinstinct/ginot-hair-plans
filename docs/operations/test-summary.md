# Test job summaries (#649)

The JUnit/coverage reporter keeps the step summary at or below 960 KiB of
UTF-8, including existing content. This leaves 64 KiB below GitHub's upload
limit. Oversized reports keep complete lines and close open detail sections,
then show a truncation note. The complete already-redacted report is printed
in the same step log with REPORT prefixes so diagnostic text cannot become a
workflow command. Existing summary content is never overwritten; when too
little room remains even for a note, the report and notice are log-only.

This bounds the upload, not the test results. A missing report remains unknown,
not zero tests or a successful run. Required test checks still decide CI status.

GitHub token diagnostics are treated as opaque values, including stateless
installation tokens with dot-separated JWT segments, underscores and hyphens
(#643). Redaction runs before display-length truncation and full-log retention.
The regression uses invented tokens only; this fix is not evidence of a leak.
