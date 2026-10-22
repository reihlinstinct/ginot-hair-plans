"""Functional map coverage with actual Chromium DOM events.

Fixtures build the real site, serve its generated HTML and assert no JS errors.
Only external map data/tiles are mocked. No test relies on internal map state.
"""
import pytest
from test_site_browser import plan_ids

pytest_plugins = ["test_site_browser"]

def test_map_lazy_filter_legend_and_live_boundary(page):
    points = [{"pl_number": f"200-{i}", "pl_name": f"Synthetic {i}",
               "station_desc": "הפקדה להתנגדויות", "representative_point": [35.213+i*.0001, 31.768]}
              for i in range(1, 23)]
    page.route("**/plan-points.json", lambda route: route.fulfill(
        json={"generated": "2026-10-22", "points": points}))
    page.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
    requests = []

    def boundary(route):
        import re
        from urllib.parse import parse_qs, urlparse
        query = parse_qs(urlparse(route.request.url).query)
        numbers = re.findall(r"'([0-9]+-[0-9]+)'", query["where"][0])
        requests.append(numbers)
        route.fulfill(json={"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"pl_number": n}, "geometry": {
                "type": "Polygon", "coordinates": [[[35.212, 31.767], [35.214, 31.767],
                [35.214, 31.769], [35.212, 31.769], [35.212, 31.767]]]}} for n in numbers]})
    page.route("https://ags.iplan.gov.il/**", boundary)
    assert not requests
    page.locator("#plan-map-panel summary").click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    assert set(requests[0]) == set(plan_ids(page))
    assert len(requests[0]) == 20
    assert page.locator(".leaflet-marker-icon").count() == 0
    assert page.locator(".leaflet-overlay-pane path").count() == 20
    assert page.locator("#map-legend").is_hidden()
    page.locator("#map-legend-toggle").click()
    assert "נקודה" in page.locator("#map-legend").inner_text()
    page.locator("#map-legend-toggle").click()
    page.click("#more")
    assert "26 שורות גלויות" in page.locator("#map-status").inner_text()
    assert page.locator(".leaflet-marker-icon").count() == 22
    assert page.locator(".leaflet-overlay-pane path").count() == 0
    page.locator("#fq").fill("200-1")
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('גבולות') && !document.querySelector('#map-status').textContent.includes('טוען')")
    assert page.locator(".leaflet-overlay-pane path").count() == 11
    assert page.locator("#map-boundaries").is_checked()
    page.uncheck("#map-boundaries")
    assert page.locator(".leaflet-overlay-pane path").count() == 0
    assert page.locator(".leaflet-marker-icon").count() == 11
    page.locator(".leaflet-marker-icon").first.click()
    page.get_by_role("button", name="טען גבול תכנית", exact=True).click()
    page.wait_for_function("document.querySelectorAll('.leaflet-overlay-pane path').length===1")
    assert not page.locator("#map-boundaries").is_checked()
    page.check("#map-boundaries")
    assert page.locator(".leaflet-overlay-pane path").count() == 11
    page.locator("#fq").fill("does-not-exist")
    assert page.locator(".leaflet-marker-icon").count() == 0
    assert page.locator(".leaflet-overlay-pane path").count() == 0
    assert "אין תכניות" in page.locator("#map-status").inner_text()


def test_map_failed_geometry_keeps_small_accessible_points(page):
    page.fill("#fq", "200-22")
    page.route("**/plan-points.json", lambda route: route.fulfill(json={"generated": "2026-10-22",
        "points": [{"pl_number": "200-22", "pl_name": "Fallback plan", "station_desc": "הפקדה",
                    "representative_point": [35.213, 31.768]}]}))
    page.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
    page.route("https://ags.iplan.gov.il/**", lambda route: route.fulfill(status=503, body="unavailable"))
    page.locator("#plan-map-panel summary").click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('לא נטענו')")
    point = page.locator(".leaflet-marker-icon")
    assert point.count() == 1
    assert "200-22" in point.get_attribute("title")
    assert point.inner_text() == ""
    point.click()
    assert "Fallback plan" in page.locator(".leaflet-popup").inner_text()


def test_map_overlap_prefers_smallest_and_excludes_holes_and_hidden_rows(page):
    # All three plans are among the initial visible twenty. Paint the largest
    # last, reproducing the reported SVG-order bug.
    numbers = ['200-20', '200-21', '200-22']
    page.route('**/plan-points.json', lambda r: r.fulfill(json={'generated': 'test', 'points': [
        {'pl_number': n, 'pl_name': n, 'station_desc': 'הפקדה',
         'representative_point': [35.213, 31.768]} for n in numbers]}))
    page.route('https://tile.openstreetmap.org/**', lambda r: r.abort())

    def square(d):
        return [[35.213-d, 31.768-d], [35.213+d, 31.768-d],
                [35.213+d, 31.768+d], [35.213-d, 31.768+d], [35.213-d, 31.768-d]]
    features = [
        {'type': 'Feature', 'properties': {'pl_number': numbers[0]},
         'geometry': {'type': 'Polygon', 'coordinates': [square(.001)]}},
        {'type': 'Feature', 'properties': {'pl_number': numbers[1]},
         'geometry': {'type': 'MultiPolygon', 'coordinates': [[square(.01), square(.002)]]}},
        {'type': 'Feature', 'properties': {'pl_number': numbers[2]},
         'geometry': {'type': 'Polygon', 'coordinates': [square(.1)]}}]
    page.route('https://ags.iplan.gov.il/**', lambda r: r.fulfill(
        json={'type': 'FeatureCollection', 'features': features}))
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('3 גבולות')")
    box = page.locator('#plan-map')
    box.click(position={'x': box.bounding_box()['width']/2, 'y': box.bounding_box()['height']/2})
    popup = page.locator('.leaflet-popup-content')
    assert 'תכנית 200-20' in popup.inner_text()
    assert popup.locator('strong').first.inner_text() == 'תכנית 200-20'
    assert '200-22' not in popup.inner_text()
    assert '200-21' not in popup.inner_text()  # click was in its hole
    assert page.locator('.leaflet-overlay-pane .leaflet-interactive').count() == 0
    page.fill('#fq', '200-22')
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('1 גבולות')")
    box.click(position={'x': box.bounding_box()['width']/2+50, 'y': box.bounding_box()['height']/2+50})
    page.locator('.leaflet-popup').wait_for(state='detached')
    page.fill('#fq', 'absent')
    box.click(position={'x': box.bounding_box()['width']/2, 'y': box.bounding_box()['height']/2})
    page.locator('.leaflet-popup').wait_for(state='detached')


@pytest.fixture
def map_network(page):
    numbers = [f'200-{i}' for i in range(1, 23)] + [f'300-{i}' for i in range(1, 5)]
    requests = []
    page.route('**/plan-points.json', lambda r: r.fulfill(json={'generated': 'test', 'points': [
        {'pl_number': n, 'pl_name': n, 'station_desc': 'בדיקה' if n.startswith('300-') else 'הפקדה',
         'representative_point': [35.213, 31.768]} for n in numbers]}))
    page.route('https://tile.openstreetmap.org/**', lambda r: r.abort())

    def respond(route):
        import re
        from urllib.parse import parse_qs, urlparse
        nums = re.findall(r"'([0-9]+-[0-9]+)'", parse_qs(urlparse(route.request.url).query)['where'][0])
        requests.append(nums)
        route.fulfill(json={'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'pl_number': n}, 'geometry': {'type': 'Polygon',
             'coordinates': [[[35.212, 31.767], [35.214, 31.767], [35.214, 31.769],
                              [35.212, 31.769], [35.212, 31.767]]]}} for n in nums]})
    page.route('https://ags.iplan.gov.il/**', respond)
    return requests


def test_map_sort_status_reset_and_no_numbered_markers(page, map_network):
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    assert set(map_network[0]) == set(plan_ids(page))
    page.uncheck('#map-boundaries')
    assert page.locator('.leaflet-marker-icon').count() == 20
    assert page.locator('.leaflet-marker-icon').all_inner_texts() == [''] * 20
    page.locator('th button[data-sort="num"]').click()
    page.wait_for_function("document.querySelectorAll('.leaflet-marker-icon').length===20")
    titles = page.locator('.leaflet-marker-icon').evaluate_all('els=>els.map(e=>e.title)')
    assert {t.split()[1] for t in titles} == set(plan_ids(page))
    page.locator('.plan-legend .chip', has_text='בדיקה תכנונית').click()
    assert page.locator('.leaflet-marker-icon').count() == 4
    assert set(plan_ids(page)) == {'300-1', '300-2', '300-3', '300-4'}
    page.check('#map-boundaries')
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('4 גבולות')")
    page.click('#freset')
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    assert page.locator('.leaflet-overlay-pane path').count() == 20


def test_map_off_prevents_auto_fetch_and_keyboard_loads_single_plan(page, map_network):
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    page.uncheck('#map-boundaries')
    map_network.clear()
    page.fill('#fq', '300-4')
    page.wait_for_selector('.leaflet-marker-icon')
    assert not map_network
    marker = page.locator('.leaflet-marker-icon').first
    marker.focus()
    marker.press('Enter')
    page.locator('.leaflet-popup-content').wait_for(state='visible')
    page.get_by_role('button', name='טען גבול תכנית', exact=True).click()
    page.wait_for_function("document.querySelectorAll('.leaflet-overlay-pane path').length===1")
    assert len(map_network) == 1 and len(map_network[0]) == 1
    page.locator(".leaflet-popup").wait_for(state="detached")  # #258: close before fitting bounds
    assert not page.locator('#map-boundaries').is_checked()


def test_map_outside_polygon_does_not_open_details(page, map_network):
    page.fill('#fq', '200-22')
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('1 גבולות')")
    canvas = page.locator('#plan-map')
    canvas.click(position={'x': canvas.bounding_box()['width']-5, 'y': 5})
    assert page.locator('.leaflet-popup').count() == 0
    canvas.click(position={'x': canvas.bounding_box()['width']/2, 'y': canvas.bounding_box()['height']/2})
    page.locator('.leaflet-popup-content strong').wait_for()
    assert page.locator('.leaflet-popup-content strong').inner_text() == 'תכנית 200-22'


def test_map_requests_survive_quick_filter_changes_without_stale_layers(page, map_network):
    page.locator('#plan-map-panel summary').click()
    page.fill('#fq', '300-4')
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('1 גבולות')")
    assert page.locator('.leaflet-overlay-pane path').count() == 1
    assert plan_ids(page) == ['300-4']
    page.fill('#fq', 'absent')
    assert page.locator('.leaflet-overlay-pane path').count() == 0
    assert page.locator('.leaflet-marker-icon').count() == 0


def test_permit_status_chip_isolated_from_map_and_closed_hidden(page, map_network):
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    before = plan_ids(page)
    assert page.locator('#permits-table tbody tr[data-active="0"]:visible').count() == 0
    page.locator('#permits .legend .chip', has_text='הבקשה נסגרה').click()
    assert page.locator('#permits-table tbody tr:visible').count() == 1
    assert plan_ids(page) == before
    assert page.locator('.leaflet-overlay-pane path').count() == 20
    page.click('#pfreset')
    assert page.locator('#permits-table tbody tr[data-active="0"]:visible').count() == 0


def test_popup_layer_above_controls_and_overlap_summary_compact(page, map_network):
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    canvas = page.locator('#plan-map')
    box = canvas.bounding_box()
    canvas.click(position={'x': box['width']/2, 'y': box['height']/2})
    page.locator('.leaflet-popup-content').wait_for()
    z = page.locator('.leaflet-popup-pane').evaluate('e=>+getComputedStyle(e).zIndex')
    assert z > 800
    assert page.locator('.leaflet-control-zoom').is_hidden()
    assert page.locator('.leaflet-popup-content summary').first.evaluate(
        'e=>parseFloat(getComputedStyle(e).fontSize)') == 14


@pytest.mark.parametrize('width', [390, 1280])
def test_popup_close_restores_zoom_and_keeps_nested_text_readable(page, map_network, width):
    page.set_viewport_size({'width': width, 'height': 900})
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('20 גבולות')")
    canvas = page.locator('#plan-map')
    box = canvas.bounding_box()
    canvas.click(position={'x': box['width']/2, 'y': box['height']/2})
    popup = page.locator('.leaflet-popup')
    popup.wait_for()
    assert page.locator('.leaflet-control-zoom').is_hidden()
    heading = popup.locator('summary').first
    assert heading.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)') == 14
    assert heading.bounding_box()['height'] >= 44
    assert popup.bounding_box()['width'] <= width
    popup.locator('.leaflet-popup-close-button').click()
    popup.wait_for(state='detached')
    assert page.locator('.leaflet-control-zoom').is_visible()


def test_map_excludes_style_hidden_row_and_keeps_boundary_click(page, map_network):
    page.fill('#fq', '200-22')
    page.locator('#plan-map-panel summary').click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('1 גבולות')")
    canvas = page.locator('#plan-map')
    canvas.scroll_into_view_if_needed()
    canvas.screenshot(path='/tmp/map-boundary-stable.png')
    # SVG path pixels give an actual edge to click, not a mocked map event.
    point = page.locator('.leaflet-overlay-pane path').evaluate('''e=>{
      var p=e.getPointAtLength(e.getTotalLength()/2).matrixTransform(e.getScreenCTM());
      return {x:p.x,y:p.y};}''')
    page.mouse.click(point['x'], point['y'])
    page.locator('.leaflet-popup-content strong').wait_for()
    assert page.locator('.leaflet-popup-content strong').inner_text() == 'תכנית 200-22'
    page.locator('.leaflet-popup-close-button').click()
    page.locator('.leaflet-popup').wait_for(state='detached')
    # Simulate an alternate table presentation hiding a row without its class.
    page.locator('#plans tbody tr[data-num="200-22"]').evaluate("e=>e.style.display='none'")
    box = canvas.bounding_box()
    canvas.click(position={'x': box['width']/2, 'y': box['height']/2})
    assert page.locator('.leaflet-popup').count() == 0
