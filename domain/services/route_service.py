"""
Route Discovery & Comparison Service (Commercial Domain).

Implements route path finding across legs and 6-dimensional comparison (SRS Section 3.4, Table 16).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from domain.entities import Route, RouteLeg
from domain.interfaces import RouteRepositoryPort


@dataclass
class CommercialRouteEvaluation:
    route: Route
    total_landed_cost: float
    proposed_sell_price: float
    carrier_reliability_score: float = 90.0
    congestion_index: float = 10.0
    on_time_pct_trailing_12mo: float = 95.0
    has_peak_season_flag: bool = False
    has_embargo_risk: bool = False

    @property
    def total_transit_hours(self) -> float:
        return self.route.total_transit_hours

    @property
    def transshipment_count(self) -> int:
        return self.route.transshipment_count

    @property
    def gross_margin(self) -> float:
        return round(self.proposed_sell_price - self.total_landed_cost, 2)

    @property
    def margin_pct(self) -> float:
        if self.proposed_sell_price == 0:
            return 0.0
        return round((self.gross_margin / self.proposed_sell_price) * 100, 2)

    @property
    def risk_score(self) -> float:
        # Lower score = lower risk
        base_risk = (
            self.transshipment_count * 10.0
            + (100.0 - self.carrier_reliability_score) * 0.5
            + self.congestion_index * 0.3
        )
        if self.has_peak_season_flag:
            base_risk += 15.0
        if self.has_embargo_risk:
            base_risk += 50.0
        return round(base_risk, 2)


@dataclass
class RouteComparisonResult:
    cheapest: CommercialRouteEvaluation | None
    fastest: CommercialRouteEvaluation | None
    lowest_risk: CommercialRouteEvaluation | None
    best_margin: CommercialRouteEvaluation | None
    most_reliable: CommercialRouteEvaluation | None
    customer_preferred: CommercialRouteEvaluation | None
    all_ranked_by_risk: list[CommercialRouteEvaluation] = field(default_factory=list)


class RouteService:
    def __init__(self, route_repo: RouteRepositoryPort) -> None:
        self.route_repo = route_repo

    def discover_routes(
        self,
        origin_id: str,
        destination_id: str,
        mode: str,
        available_legs: list[RouteLeg] | None = None,
    ) -> list[Route]:
        """
        Discovers direct routes and 2-hop transshipment routes between origin and destination.
        """
        existing = self.route_repo.find_routes(origin_id, destination_id, mode)
        if existing:
            return existing

        discovered: list[Route] = []

        if available_legs:
            # 1. Direct legs
            for leg in available_legs:
                if leg.from_location_id == origin_id and leg.to_location_id == destination_id:
                    discovered.append(
                        Route(
                            origin_location_id=origin_id,
                            destination_location_id=destination_id,
                            mode=mode,
                            legs=[leg],
                        )
                    )

            # 2. 2-hop transshipment combinations
            for leg1 in available_legs:
                if leg1.from_location_id == origin_id and leg1.to_location_id != destination_id:
                    for leg2 in available_legs:
                        if leg2.from_location_id == leg1.to_location_id and leg2.to_location_id == destination_id:
                            leg1_copy = RouteLeg(
                                from_location_id=leg1.from_location_id,
                                to_location_id=leg1.to_location_id,
                                carrier_id=leg1.carrier_id,
                                sequence=1,
                                transit_time_hours=leg1.transit_time_hours,
                                is_transshipment=False,
                            )
                            leg2_copy = RouteLeg(
                                from_location_id=leg2.from_location_id,
                                to_location_id=leg2.to_location_id,
                                carrier_id=leg2.carrier_id,
                                sequence=2,
                                transit_time_hours=leg2.transit_time_hours,
                                is_transshipment=True,
                            )
                            discovered.append(
                                Route(
                                    origin_location_id=origin_id,
                                    destination_location_id=destination_id,
                                    mode=mode,
                                    legs=[leg1_copy, leg2_copy],
                                )
                            )

        return discovered

    def compare_evaluated_routes(
        self,
        evaluations: list[CommercialRouteEvaluation],
        preferred_carrier_id: str | None = None,
    ) -> RouteComparisonResult:
        if not evaluations:
            return RouteComparisonResult(
                cheapest=None, fastest=None, lowest_risk=None,
                best_margin=None, most_reliable=None, customer_preferred=None,
            )

        cheapest = min(evaluations, key=lambda e: e.total_landed_cost)
        fastest = min(evaluations, key=lambda e: e.total_transit_hours)
        ranked_by_risk = sorted(evaluations, key=lambda e: e.risk_score)
        lowest_risk = ranked_by_risk[0]
        best_margin = max(evaluations, key=lambda e: e.gross_margin)
        most_reliable = max(evaluations, key=lambda e: e.on_time_pct_trailing_12mo)

        customer_preferred = None
        if preferred_carrier_id:
            matches = [e for e in evaluations if preferred_carrier_id in e.route.carriers_used]
            if matches:
                customer_preferred = min(matches, key=lambda e: e.total_landed_cost)

        return RouteComparisonResult(
            cheapest=cheapest,
            fastest=fastest,
            lowest_risk=lowest_risk,
            best_margin=best_margin,
            most_reliable=most_reliable,
            customer_preferred=customer_preferred,
            all_ranked_by_risk=ranked_by_risk,
        )
