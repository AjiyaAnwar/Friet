import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.modules.commercial.calculations.route_comparison import Route, RouteLeg, compare_routes


def make_route(**overrides):
    defaults = dict(
        route_id="RT1", origin="PKKAR", destination="AEJEA",
        legs=[RouteLeg("PKKAR", "AEJEA", "Maersk", transit_time_hours=48)],
        total_landed_cost=1000, proposed_sell_price=1200,
        carrier_reliability_score=90, congestion_index=10,
        on_time_pct_trailing_12mo=95,
    )
    defaults.update(overrides)
    return Route(**defaults)


def test_route_derived_properties():
    route = make_route(
        legs=[
            RouteLeg("PKKAR", "AEDXB", "Emirates", 20),
            RouteLeg("AEDXB", "AEJEA", "Emirates", 10),
        ]
    )
    assert route.total_transit_hours == 30
    assert route.transshipment_count == 1
    assert route.carriers_used == {"Emirates"}
    assert route.gross_margin == route.proposed_sell_price - route.total_landed_cost


def test_cheapest_route_is_selected():
    routes = [
        make_route(route_id="EXPENSIVE", total_landed_cost=2000),
        make_route(route_id="CHEAP", total_landed_cost=800),
    ]
    result = compare_routes(routes)
    assert result.cheapest.route_id == "CHEAP"


def test_fastest_route_is_selected():
    routes = [
        make_route(route_id="SLOW", legs=[RouteLeg("A", "B", "X", 100)]),
        make_route(route_id="FAST", legs=[RouteLeg("A", "B", "X", 20)]),
    ]
    result = compare_routes(routes)
    assert result.fastest.route_id == "FAST"


def test_lowest_risk_favors_direct_high_reliability_route():
    routes = [
        make_route(
            route_id="DIRECT_RELIABLE",
            legs=[RouteLeg("A", "B", "X", 30)],
            carrier_reliability_score=98, congestion_index=5,
        ),
        make_route(
            route_id="TRANSSHIP_RISKY",
            legs=[RouteLeg("A", "T", "X", 15), RouteLeg("T", "B", "Y", 15)],
            carrier_reliability_score=60, congestion_index=70,
        ),
    ]
    result = compare_routes(routes)
    assert result.lowest_risk.route_id == "DIRECT_RELIABLE"


def test_best_margin_route_is_selected():
    routes = [
        make_route(route_id="LOW_MARGIN", total_landed_cost=1000, proposed_sell_price=1050),
        make_route(route_id="HIGH_MARGIN", total_landed_cost=1000, proposed_sell_price=1500),
    ]
    result = compare_routes(routes)
    assert result.best_margin.route_id == "HIGH_MARGIN"


def test_most_reliable_route_is_selected():
    routes = [
        make_route(route_id="LESS_RELIABLE", on_time_pct_trailing_12mo=80),
        make_route(route_id="MORE_RELIABLE", on_time_pct_trailing_12mo=99),
    ]
    result = compare_routes(routes)
    assert result.most_reliable.route_id == "MORE_RELIABLE"


def test_customer_preferred_carrier_match():
    routes = [
        make_route(route_id="OTHER_CARRIER", legs=[RouteLeg("A", "B", "MSC", 30)]),
        make_route(route_id="PREFERRED", legs=[RouteLeg("A", "B", "Maersk", 40)]),
    ]
    result = compare_routes(routes, preferred_carrier="Maersk")
    assert result.customer_preferred.route_id == "PREFERRED"


def test_customer_preferred_none_when_no_match():
    routes = [make_route(route_id="R1", legs=[RouteLeg("A", "B", "MSC", 30)])]
    result = compare_routes(routes, preferred_carrier="Maersk")
    assert result.customer_preferred is None


def test_empty_routes_returns_all_none():
    result = compare_routes([])
    assert result.cheapest is None
    assert result.fastest is None
    assert result.lowest_risk is None