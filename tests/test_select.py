from shapely.geometry import Point, Polygon

from ginot import select


def test_select_and_verify_real_landmarks():
    # fabricate polygons at the real landmark coordinates
    t = select._TO_2039
    xs, ys = zip(*[t.transform(*select.REQUIRED_LANDMARKS[k]) for k in
                   ["Rehavia", "Talbiya", "Komemiyut", "GermanColony", "GreekColony", "Nayot"]])
    a = Polygon([(min(xs)-50, min(ys)-50), (max(xs)+50, min(ys)-50),
                 (max(xs)+50, max(ys)+50), (min(xs)-50, max(ys)+50)])
    polys = [a]
    # narrow strips from each southern landmark back into A (like real road-following polys)
    anchor = t.transform(*select.REQUIRED_LANDMARKS["GreekColony"])
    for k in ["KatamonOld", "GivatHordim", "Gonenim"]:
        x, y = t.transform(*select.REQUIRED_LANDMARKS[k])
        x0, x1 = sorted([x-30, anchor[0]+30]); y0, y1 = sorted([y-30, anchor[1]+30])
        polys.append(Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
    union, idx = select.select_council(polys)
    assert len(idx) >= 3  # greedy may merge coverage
    for k, ll in select.REQUIRED_LANDMARKS.items():
        assert union.contains(Point(*t.transform(*ll))), k
    for k, ll in select.FORBIDDEN_LANDMARKS.items():
        assert not union.contains(Point(*t.transform(*ll))), k


def test_verify_flags_missing():
    tiny = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    v = select.verify(tiny)
    assert not v["ok"]
    assert v["required_inside"] == []
