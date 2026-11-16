"""Browser coverage: search. Shared fixtures stay in test_site_browser."""

import functools
import json
import threading

import pytest
from test_site_browser import _Quiet, _ThreadingServer, plan_ids, recorded_page

pytest_plugins = ["test_site_browser"]


# Section: Search


def _permit(tik, status, sug="היתר", addr="הרצל 5"):
    return {
        "tik_num": tik,
        "mahut": "x",
        "sugbakasha": sug,
        "status": status,
        "status_date": "2026-10-01",
        "gush": 30007,
        "helka": 12,
        "address": addr,
        "publication_start": "",
        "publication_end_planned": "",
    }


@pytest.mark.evidence
def test_legend_options_and_counts_follow_the_live_fragment(browser, tmp_path, request):
    """Regression (#414): the weekly shell and the feed-updated fragment drift
    apart between Tuesdays (legend said (1) while 8 rows carried the status on
    the live site, 2026-10-24). Legend chips, filter options and the closed
    count must derive from the loaded fragment, not the stale shell."""
    from ginot import page as _page

    shell_permits = [_permit("2020/0001.00", "בבדיקה")]
    live_permits = shell_permits + [
        _permit("2026/0439.00", "תחילת פרסום הבקשה להקלה", addr="הפלמח 41 קטמון הישנה"),
        _permit("2026/0439.01", "תחילת פרסום הבקשה להקלה", addr="הפלמח 43 קטמון הישנה"),
        _permit("1990/0002.00", "הבקשה נסגרה"),
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(
        json.dumps({"requests": shell_permits}, ensure_ascii=False), encoding="utf-8"
    )
    plan = {
        "pl_number": "1",
        "pl_name": "תכנית 1",
        "station_desc": "הפקדה",
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }
    _page.render_site([plan], [], str(tmp_path), permits_path=str(pf))
    # feed publish re-renders ONLY the fragment from newer data (#412 flow)
    _page._permits_section(live_permits, rows_file=str(tmp_path / "permits.html"))

    handler = functools.partial(_Quiet, directory=str(tmp_path))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with recorded_page(browser, request) as (pg, _errs):
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            # #441: the full list loads on demand; these tests need all rows.
            pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
            pg.wait_for_function(
                "window.__permitsLoaded === true || window.__permitsFailed === true"
            )
            assert pg.evaluate("window.__permitsLoaded") is True
            new_status = "תחילת פרסום הבקשה להקלה"
            # dropdown gains the status that only exists in the live fragment
            options = pg.locator("#pfstatus option").all_text_contents()
            assert new_status in options
            # legend chip counts come from the fragment rows, not the shell;
            # chips are status GROUPS since #521 (raw statuses fill the select)
            chips = pg.locator("#permits .legend .chip").all_text_contents()
            assert "פרסום / הודעות להתנגדות (2)" in chips
            assert "לא מסווג (1)" in chips
            assert "סגור/אחר (1)" in chips
            # closed count label follows the fragment
            label = pg.locator("#pfilters label", has_text="הצג בקשות שהסתיימו")
            assert "(1)" in label.inner_text()
            # selecting the new status filters to exactly its rows
            pg.select_option("#pfstatus", new_status)
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 2


@pytest.mark.evidence
def test_search_matches_hebrew_punctuation_variants(browser, tmp_path, request):
    """Regression (#413): the user's exact spelling הפלמ״ח (geresh) returned 0
    on the live site 2026-10-24 while the municipal address spells הפלמח
    without geresh. Geresh, gershayim, apostrophes, quotes and maqaf/hyphen
    normalize away on both the query and the indexed row text."""
    from ginot import page as _page

    permits = [
        _permit("2026/0439.00", "תחילת פרסום הבקשה להקלה", addr="הפלמח 41 קטמון הישנה"),
        _permit("2020/0001.00", "בבדיקה", addr="הרצל 5"),
        # #468 row-side folding: pointed letters, a typographic quote, NBSP and
        # an RLM in the stored address must fold like the query does.
        _permit(
            "2020/0002.00",
            "בבדיקה",
            addr="\u200fהַמֶּלֶךְ\u00a0ג\u2018ורג\u2018  60",
        ),
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(
        json.dumps({"requests": permits}, ensure_ascii=False), encoding="utf-8"
    )
    plan = {
        "pl_number": "1",
        "pl_name": "תכנית 1",
        "station_desc": "הפקדה",
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }
    _page.render_site([plan], [], str(tmp_path), permits_path=str(pf))
    handler = functools.partial(_Quiet, directory=str(tmp_path))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with recorded_page(browser, request) as (pg, _errs):
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            # #441: the full list loads on demand; these tests need all rows.
            pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
            pg.wait_for_function(
                "window.__permitsLoaded === true || window.__permitsFailed === true"
            )
            assert pg.evaluate("window.__permitsLoaded") is True
            # #468: typographic quotes, primes, niqqud, NBSP and doubled
            # spaces fold the same way as the #413 ASCII/Hebrew variants.
            for variant in [
                "הפלמ״ח",
                'הפלמ"ח',
                "הפלמ'ח",
                "הפלמח",
                "הפלמח 41",
                "הפלמ\u201cח",
                "הפלמ\u201dח",
                "הפלמ\u2033ח",
                "הפלמ\u2019ח",
                "\u05d4\u05b7\u05e4\u05bc\u05b8\u05dc\u05de\u05d7",  # pointed
                "הפלמח\u00a041",
                "הפלמח   41",
                "\u200fהפלמח 41",
            ]:
                pg.fill("#pfq", "")
                pg.fill("#pfq", variant)
                pg.dispatch_event("#pfq", "input")
                visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
                texts = visible.all_text_contents()
                assert len(texts) == 1 and "2026/0439.00" in texts[0], (
                    f"{variant!r} should find exactly the הפלמח 41 row, got {texts}"
                )
            for variant in ["המלך גורג 60", "המלך ג'ורג' 60", "ג׳ורג׳"]:
                pg.fill("#pfq", "")
                pg.fill("#pfq", variant)
                pg.dispatch_event("#pfq", "input")
                visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
                texts = visible.all_text_contents()
                assert len(texts) == 1 and "2020/0002.00" in texts[0], (
                    f"{variant!r} should find exactly the pointed-address row, got {texts}"
                )


def _plan_row(num, name, status="הפקדה"):
    return {
        "pl_number": num,
        "pl_name": name,
        "station_desc": status,
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": f"https://mavat.iplan.gov.il/{num}",
    }


def test_plan_search_folds_spelling_variants_without_aliases(
    browser, tmp_path, request
):
    """Regression (#468): the owner could not find plan 101-0617134 by a
    spelling variant. The plans table must fold geresh/quote/prime variants,
    niqqud, dashes and whitespace runs identically on query and row text,
    keep literal plan-number matching, and add NO aliases: the plan feed
    carries no street field, so the colloquial "קינג גורג" stays a miss.
    Synthetic rows; the official name shape is decorated with row-side
    Unicode variants to cover query AND index normalization (#678)."""
    from ginot import page as _page

    plans = [
        _plan_row(
            "101-0617134", "מלון\u00a0המלכים\u200f\u2013 הַמֶּלֶך\u00a0ג\u2018ורג\u2018  60"
        ),
        _plan_row("101-0000001", "גולדה מאיר 3"),
        _plan_row("101-0000002", "הרצל 5"),
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(json.dumps({"requests": []}, ensure_ascii=False), encoding="utf-8")
    _page.render_site(plans, [], str(tmp_path), permits_path=str(pf))
    handler = functools.partial(_Quiet, directory=str(tmp_path))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with recorded_page(browser, request) as (pg, errors):
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            pg.wait_for_function(
                "window.__rowsLoaded === true || window.__rowsFailed === true"
            )
            assert pg.evaluate("window.__rowsLoaded") is True
            pg.check("#fappr")

            def ids(query):
                pg.fill("#fq", query)
                pg.dispatch_event("#fq", "input")
                return sorted(plan_ids(pg))

            everything = ids("")
            assert len(everything) == 3
            george = ["101-0617134"]
            for variant in [
                "ג'ורג'",
                "ג׳ורג׳",
                "ג\u2019ורג\u2019",
                "ג\u2018ורג\u2018",
                "ג\u2032ורג\u2032",
                "גורג",
                "המלך ג׳ורג׳ 60",
                "המלך  ג'ורג'  60",
                "המלך\u00a0גורג",
                "המלכים - המלך",
                "המלכים \u2013 המלך",
                "\u05d4\u05b7\u05de\u05bc\u05b6\u05dc\u05b6\u05da\u05b0 גורג",
                "\u200fמלון המלכים",
                # literal plan-number matching is preserved
                "101-0617134",
                "1010617134",
                "0617134",
                "101\u20110617134",
            ]:
                assert ids(variant) == george, (
                    f"{variant!r} should find only 101-0617134"
                )
            # no aliases: no committed source spells the plan this way
            assert ids("קינג גורג") == []
            # no false-positive broadening
            assert ids("הרצל") == ["101-0000002"]
            assert ids("גולדה") == ["101-0000001"]
            assert ids("צ") == ["101-0000002"]  # one letter: only rows containing it
            assert ids("ט") == []
            assert ids("'") == everything  # punctuation-only behaves like empty
            assert ids("   ") == everything
            assert errors == [], f"JavaScript errors on the page: {errors}"
