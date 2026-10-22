# Recent Bug regression audit

Audited 2026-10-22. Every listed fix already had a targeted regression in its
fixing PR. This audit adds stronger asset and mobile close/restore checks.
The standing rule is in CONTRIBUTING.md and the Bug/PR templates.

| Bug | Fix PR | Existing automated regression | Added in audit |
| --- | --- | --- | --- |
| #251 checkpoint/resume | #252 | `test_scan_checkpoint.py`: `test_complete_scan_resumes_details_and_checkpoints_them`, retry-success and three-failure stop tests | None needed |
| #256 invisible stats bars | #257 | `test_site_browser.py::test_statistics_have_visible_tracks_and_fills`, widths390/1280 | None needed |
| #260 favicon fallbacks | #261 | `test_page.py::test_favicon_subpath_links_on_root_and_review` | Decode committed ICO16/32/48, PNG32, Apple180, SVG existence |
| #264 visible-table map mismatch | #266 | `test_map_browser.py::test_map_lazy_filter_legend_and_live_boundary`; default20 query IDs, expand/search/empty | None needed |
| #265 permit chips/default closed | #266 | `test_site_browser.py::test_permit_closed_chip_is_explicit_and_does_not_change_plan_filter`, committed-script check | Existing dedicated map/permit isolation test also covers it |
| #269 citywide polygon swallows clicks | #270 | `test_map_browser.py::test_map_overlap_prefers_smallest_and_excludes_holes_and_hidden_rows`; actual click, smallest first, holes, hidden rows | None needed |
| #273 popup mobile overlap | #274 | `test_map_browser.py::test_popup_layer_above_controls_and_overlap_summary_compact` | Mobile/desktop popup width,44px nested summary, zoom hidden while open and restored after close |

Map coverage was split into a dedicated module and CI target by #272.
No test-only follow-up issue is needed for these fixes: all are automated.

- #285: `tests/test_permit_pipeline.py::test_checkpoint_large_payload_uses_stdin_not_argv` covers oversized checkpoint transport; `test_feed_reuses_only_complete_same_day_unchanged_details` covers freshness and changed/missing detail rejection. `tests/test_scan_checkpoint.py::test_complete_scan_resumes_details_and_checkpoints_them` covers durable detail resume.
