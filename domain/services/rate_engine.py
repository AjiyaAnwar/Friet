"""
Commercial Rate & Tariff Engine (Team 2).

Implements 4-tier rate resolution, priority cascade, weight break matching,
container type matching, surcharge auto-attachment, multi-currency conversion,
and multi-carrier comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from domain.entities import (
    Rate, RateVersion, RateLine, RateSurcharge, RateCategory, RateStatus,
    QuotationLine, ChargeCategory
)
from domain.interfaces import RateRepositoryPort, ExchangeRatePort


@dataclass
class CarrierRateComparisonItem:
    carrier_id: str
    service_name: str
    rate_category: str
    base_freight_cost: float
    surcharges_cost: float
    total_landed_cost: float
    proposed_sell_price: float
    gross_margin: float
    margin_pct: float
    currency: str
    rate_version_id: str
    rate: Rate
    version: RateVersion
    resolved_lines: list[RateLine]
    attached_surcharges: list[RateSurcharge]


class RateEngine:
    def __init__(
        self,
        rate_repo: RateRepositoryPort,
        fx_service: ExchangeRatePort | None = None,
    ) -> None:
        self.rate_repo = rate_repo
        self.fx_service = fx_service

    def resolve_rate_for_lane(
        self,
        customer_id: str,
        origin_id: str,
        destination_id: str,
        effective_date: date,
        weight_kg: float | None = None,
        volume_cbm: float | None = None,
        container_type: str | None = None,
        commodity_id: str | None = None,
        carrier_id: str | None = None,
    ) -> tuple[Rate | None, RateVersion | None, list[RateLine], list[RateSurcharge], str]:
        """
        Applies the 7-tier priority cascade to find the best rate and extracts matching
        rate lines and surcharges.
        """
        available = self.rate_repo.find_rates(
            origin_id=origin_id,
            destination_id=destination_id,
            effective_date=effective_date,
            commodity_id=commodity_id,
        )

        if carrier_id:
            available = [r for r in available if r.carrier_vendor_id == carrier_id]

        categories = [
            RateCategory.CONTRACT_NAC,
            RateCategory.SPOT,
            RateCategory.LANE_NAC,
            RateCategory.PROMOTIONAL,
            RateCategory.FAK,
            RateCategory.AGENT,
        ]

        for cat in categories:
            candidates = [r for r in available if r.rate_category == cat]
            if cat in (RateCategory.CONTRACT_NAC, RateCategory.SPOT):
                candidates = [r for r in candidates if r.customer_id == customer_id]

            if not candidates:
                continue

            # Pick best rate in this category
            best_rate = candidates[0]
            version = best_rate.current_version
            if not version:
                continue

            # Match applicable rate lines
            matched_lines: list[RateLine] = []
            for line in version.lines:
                if weight_kg is not None and line.weight_break_from is not None:
                    wb_to = line.weight_break_to or float("inf")
                    if line.weight_break_from <= weight_kg < wb_to:
                        matched_lines.append(line)
                elif container_type and line.container_type_code:
                    if line.container_type_code == container_type:
                        matched_lines.append(line)
                else:
                    matched_lines.append(line)

            # Match applicable surcharges
            matched_surcharges: list[RateSurcharge] = [
                s for s in version.surcharges
                if s.applicable_from <= effective_date <= s.applicable_to
            ]

            return (
                best_rate,
                version,
                matched_lines,
                matched_surcharges,
                f"Selected {cat.value} rate {best_rate.rate_number}",
            )

        return None, None, [], [], "No valid rate found in any category for this lane"

    def calculate_freight_charge_lines(
        self,
        version: RateVersion,
        matched_lines: list[RateLine],
        surcharges: list[RateSurcharge],
        markup_pct: float = 15.0,
        rate_currency: str = "USD",
        target_currency: str = "USD",
        effective_date: date | None = None,
        weight_kg: float = 1.0,
        volume_cbm: float = 1.0,
        container_qty: int = 1,
    ) -> list[QuotationLine]:
        """
        Converts resolved rate lines and surcharges into itemized QuotationLines with cost and sell prices.
        Applies currency conversion if rate_currency differs from target_currency.
        """
        if effective_date is None:
            effective_date = date.today()

        charge_lines: list[QuotationLine] = []

        # Base freight lines
        for line in matched_lines:
            if line.rate_basis == "PER_KG":
                cost = line.amount * weight_kg
            elif line.rate_basis == "PER_CBM":
                cost = line.amount * volume_cbm
            elif line.rate_basis == "PER_CONTAINER":
                cost = line.amount * container_qty
            else:
                cost = line.amount

            # Convert FX if needed
            if self.fx_service and rate_currency != target_currency:
                cost = self.fx_service.convert(cost, rate_currency, target_currency, effective_date)

            sell = round(cost * (1 + markup_pct / 100), 2)
            charge_lines.append(
                QuotationLine(
                    charge_code=line.charge_code,
                    category=ChargeCategory.FREIGHT,
                    cost_amount=round(cost, 2),
                    sell_amount=sell,
                    description=f"Base Freight ({line.charge_code})",
                    rate_version_id=version.id,
                )
            )

        # Surcharges
        for sur in surcharges:
            if sur.basis == "PER_TEU" or sur.basis == "PER_CONTAINER":
                cost = sur.amount * container_qty
            elif sur.basis == "PER_KG":
                cost = sur.amount * weight_kg
            elif sur.basis == "PERCENTAGE":
                # Percentage of total base freight in target currency
                base_cost = sum(cl.cost_amount for cl in charge_lines if cl.category == ChargeCategory.FREIGHT)
                cost = base_cost * (sur.amount / 100)
            else:
                cost = sur.amount

            # Convert FX if not percentage
            if sur.basis != "PERCENTAGE" and self.fx_service and rate_currency != target_currency:
                cost = self.fx_service.convert(cost, rate_currency, target_currency, effective_date)

            sell = round(cost * (1 + markup_pct / 100), 2)
            charge_lines.append(
                QuotationLine(
                    charge_code=sur.charge_code,
                    category=ChargeCategory.SURCHARGE,
                    cost_amount=round(cost, 2),
                    sell_amount=sell,
                    description=f"Surcharge ({sur.charge_code})",
                    rate_version_id=version.id,
                )
            )

        return charge_lines

    def compare_all_carriers_on_lane(
        self,
        customer_id: str,
        origin_id: str,
        destination_id: str,
        effective_date: date,
        weight_kg: float = 1.0,
        volume_cbm: float = 1.0,
        container_type: str | None = None,
        container_qty: int = 1,
        markup_pct: float = 15.0,
        target_currency: str = "USD",
    ) -> list[CarrierRateComparisonItem]:
        """
        Finds all active rates across all carriers on a trade lane and computes side-by-side
        landed costs, margins, and comparative summaries (SRS Section 5.7).
        """
        available = self.rate_repo.find_rates(
            origin_id=origin_id,
            destination_id=destination_id,
            effective_date=effective_date,
        )

        comparison_items: list[CarrierRateComparisonItem] = []

        # Group by carrier
        carriers = {r.carrier_vendor_id for r in available}
        for carrier_id in carriers:
            rate, version, lines, surcharges, reason = self.resolve_rate_for_lane(
                customer_id=customer_id,
                origin_id=origin_id,
                destination_id=destination_id,
                effective_date=effective_date,
                weight_kg=weight_kg,
                volume_cbm=volume_cbm,
                container_type=container_type,
                carrier_id=carrier_id,
            )
            if not rate or not version:
                continue

            charge_lines = self.calculate_freight_charge_lines(
                version=version,
                matched_lines=lines,
                surcharges=surcharges,
                markup_pct=markup_pct,
                rate_currency=rate.currency_code,
                target_currency=target_currency,
                effective_date=effective_date,
                weight_kg=weight_kg,
                volume_cbm=volume_cbm,
                container_qty=container_qty,
            )

            freight_cost = sum(cl.cost_amount for cl in charge_lines if cl.category == ChargeCategory.FREIGHT)
            surcharge_cost = sum(cl.cost_amount for cl in charge_lines if cl.category == ChargeCategory.SURCHARGE)
            total_cost = round(freight_cost + surcharge_cost, 2)
            total_sell = round(sum(cl.sell_amount for cl in charge_lines), 2)
            margin = round(total_sell - total_cost, 2)
            margin_pct = round((margin / total_sell) * 100, 2) if total_sell > 0 else 0.0

            comparison_items.append(
                CarrierRateComparisonItem(
                    carrier_id=carrier_id,
                    service_name=rate.service_name,
                    rate_category=rate.rate_category.value,
                    base_freight_cost=freight_cost,
                    surcharges_cost=surcharge_cost,
                    total_landed_cost=total_cost,
                    proposed_sell_price=total_sell,
                    gross_margin=margin,
                    margin_pct=margin_pct,
                    currency=target_currency,
                    rate_version_id=version.id,
                    rate=rate,
                    version=version,
                    resolved_lines=lines,
                    attached_surcharges=surcharges,
                )
            )

        return sorted(comparison_items, key=lambda x: x.total_landed_cost)
