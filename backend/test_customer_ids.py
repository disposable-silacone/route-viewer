from __future__ import annotations

from app.db.customers import normalize_customer_id
from app.db.segment_ids import make_activity_id, make_region_id, make_region_name


def test_normalize_customer_id():
    assert normalize_customer_id("Amanda") == "amanda"
    assert normalize_customer_id("  amanda-early  ") == "amanda-early"


def test_normalize_customer_id_rejects_empty():
    try:
        normalize_customer_id("   ")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_make_region_id_stable_at_2dp():
    a = make_region_id(40.590879, -75.515792)
    b = make_region_id(40.594, -75.519)
    assert a == b


def test_make_region_name():
    assert make_region_name(40.59, -75.52) == "40.59°N, 75.52°W"


def test_make_activity_id_scoped_to_customer():
    h = "abc123" * 6 + "abcd"
    a = make_activity_id("amanda", h)
    b = make_activity_id("bob", h)
    assert a != b
    assert a == make_activity_id("amanda", h)
    assert len(a) == 36
