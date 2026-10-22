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

## Historical audit,2026-10-22

Reviewed27 recorded incidents:17 closed issues carrying `bug`, plus10 historical
fix/incident records missing that label. Follow-up tests use synthetic data and
mock commands, never trigger scans or change live settings.

| Records | Regression evidence |
| --- | --- |
| #44 job-level kill switch parsing | `test_historical_regressions.py::test_mavat_kill_switch_uses_valid_job_vars_context` |
| #45 curl content type contains spaces | `test_discovery_parses_content_type_with_spaces` |
| #59 browser install/launch path; #61 runner-user execution | `test_mavat_browser_install_launch_share_path_and_runner_user` |
| #79 timeout; #147 oversized batch | `test_refresh_timeout_and_bounded_scan_size`; `test_parcel_schedule.py` |
| #83 unexplained ~1h cancellation | `test_vpn_rekeys_before_default_one_hour_expiry`; `test_vpn_watch.py`. Preventive configuration/diagnostics covered. Remote cancellation cause remains unproved, cannot be reproduced offline or claimed fixed by this test. |
| #85 approval-gated CI; #132 attempted self-approval | `test_refresh_inline_tests_precede_merge_without_approval_gated_dispatch` protects current inline refresh CI and permit explicit dispatch-run selection |
| #138 zero open-window share count | Existing `test_page.py::test_preview_counts_open_objection_windows` |
| #155 lost runner output; #251 incomplete detail resume | Existing `test_scan_checkpoint.py` checkpoint/retry/fail-stop/resume tests |
| #170 stale PR; #187 invalid jq; #277 Mavat stale PR | `test_publish_wait_executes_clean_conflict_timeout_paths`: extracted real shell, mocked gh, nine workflow/state cases. CLEAN succeeds, DIRTY fails, BLOCKED times out after45checks. |
| #186 index drift | Existing `test_site_index.py::test_committed_index_matches_repo_folder_state` |
| #227 stale mirror lease | `test_refresh_mirror_fetches_lease_ref_before_force_push` |
| #244 inert mobile AI chip | `test_site_browser.py::test_mobile_ai_header_hidden_review_links_preserved` |
| #258 inaccessible popup after boundary fit | Explicit popup-closed assertion added to existing keyboard boundary-loading browser test |
| #256/#260/#264/#265/#269/#273 | Existing evidence in table above |
| #283 random citywide interior clicks | Existing `test_map_browser.py::test_map_excludes_style_hidden_row_and_keeps_boundary_click` and outside-polygon test |
| #285 oversized checkpoint/fresh detail cache | Existing large-stdin and freshness tests noted above |

New test cases:17 (nine shell state/workflow cases, seven other historical
checks, one mobile browser check), plus one stronger existing browser test.
No production code or visual design changed. Source-site outages, runner
cancellation signals and VPN-provider behavior cannot be faithfully reproduced
by offline regression tests; the #83 distinction above is intentional.
