"""
Route Management Engine - Comparison logic.

    - Cheapest: total landed cost
    - Fastest: total transit time
    - Lowest-risk: fewest transshipments, highest reliability, lowest congestion
    - Best margin: highest gross margin at proposed selling price
    - Customer preferred: matches customer's stated carrier/routing preference
    - Most reliable: on-time arrival % over trailing 12 months
"""

from dataclasses import dataclass, field


@dataclass
class RouteLeg:
    from_location: str
    to_location: str
    carrier: str
    transit_time_hours: float
    is_transshipment_point: bool = False


@dataclass
class Route:
    route_id: str
    origin: str
    destination: str
    legs: list[RouteLeg]
    total_landed_cost: float
    proposed_sell_price: float
    carrier_reliability_score: float
    congestion_index: float
    on_time_pct_trailing_12mo: float

    @property
    def total_transit_hours(self) -> float:
        return sum(leg.transit_time_hours for leg in self.legs)

    @property
    def transshipment_count(self) -> int:
        return max(len(self.legs) - 1, 0)

    @property
    def carriers_used(self) -> set[str]:
        return {leg.carrier for leg in self.legs}

    @property
    def gross_margin(self) -> float:
        return self.proposed_sell_price - self.total_landed_cost

    @property
    def risk_score(self) -> float:
        return (
            self.transshipment_count * 10
            + (100 - self.carrier_reliability_score) * 0.5
            + self.congestion_index * 0.3
        )


@dataclass
class RouteComparisonResult:
    cheapest: Route | None
    fastest: Route | None
    lowest_risk: Route | None
    best_margin: Route | None
    most_reliable: Route | None
    customer_preferred: Route | None
    all_routes_ranked_by_risk: list[Route] = field(default_factory=list)


def compare_routes(
    routes: list[Route],
    preferred_carrier: str | None = None,
) -> RouteComparisonResult:
    if not routes:
        return RouteComparisonResult(
            cheapest=None, fastest=None, lowest_risk=None,
            best_margin=None, most_reliable=None, customer_preferred=None,
        )

    cheapest = min(routes, key=lambda r: r.total_landed_cost)
    fastest = min(routes, key=lambda r: r.total_transit_hours)
    ranked_by_risk = sorted(routes, key=lambda r: r.risk_score)
    lowest_risk = ranked_by_risk[0]
    best_margin = max(routes, key=lambda r: r.gross_margin)
    most_reliable = max(routes, key=lambda r: r.on_time_pct_trailing_12mo)

    customer_preferred = None
    if preferred_carrier:
        matches = [r for r in routes if preferred_carrier in r.carriers_used]
        if matches:
            customer_preferred = min(matches, key=lambda r: r.total_landed_cost)

    return RouteComparisonResult(
        cheapest=cheapest,
        fastest=fastest,
        lowest_risk=lowest_risk,
        best_margin=best_margin,
        most_reliable=most_reliable,
        customer_preferred=customer_preferred,
        all_routes_ranked_by_risk=ranked_by_risk,
    )