"""Phase 7 – Commercial Analytics Service.

All aggregations are performed in PostgreSQL via SQLAlchemy expressions.
No bulk Python loops over full table scans.

Analytics covered:
  7.1  RFQ Funnel
  7.2  Quotation Win / Loss
  7.3  Revenue
  7.4  Rate Competitiveness
  7.5  Rate Utilisation Heatmap
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, and_, case, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.commercial import (
    Customer,
    Quotation,
    QuotationOption,
    Rate,
    RateVersion,
    RFQ,
)
from app.db.models.domain import RevenueLine, Shipment
from app.db.models.financial_integrity import MarketRate
from app.db.models.identity import Branch, UserBranchRole
from app.db.models.reference import Carrier, Location


def _parse_uuid(val: Any) -> uuid.UUID | None:
    if not val:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError):
        return None


class CommercialAnalyticsService:
    """Database-side aggregation for all Phase 7 analytics endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # 7.1  RFQ Funnel
    # ------------------------------------------------------------------

    # RFQ status lifecycle as defined in the existing RFQ model default
    RFQ_FUNNEL_STAGES = [
        "DRAFT",
        "SUBMITTED",
        "PRICING_IN_PROGRESS",
        "QUOTED",
        "WON",
        "LOST",
        "CANCELLED",
    ]

    async def rfq_funnel(
        self,
        *,
        tenant_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        customer_id: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Return RFQ counts, conversion rates, and average aging per stage.

        Filtering supports: date range (created_at), customer, mode.
        Branch filtering is not supported because RFQ has no branch_id column.
        Trade-lane filtering is not supported at the funnel level (use heatmap
        for lane-specific coverage instead).
        """
        stmt = select(
            RFQ.status,
            func.count(RFQ.id).label("count"),
            func.avg(
                func.extract(
                    "epoch",
                    func.now() - RFQ.created_at,
                )
                / 86400  # seconds → days
            ).label("avg_age_days"),
        ).where(RFQ.tenant_id == tenant_id)

        if date_from:
            stmt = stmt.where(RFQ.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            stmt = stmt.where(RFQ.created_at <= datetime.combine(date_to, datetime.max.time()))
        c_uuid = _parse_uuid(customer_id)
        if c_uuid:
            stmt = stmt.where(RFQ.customer_id == c_uuid)
        if mode:
            stmt = stmt.where(RFQ.mode == mode.upper())

        stmt = stmt.group_by(RFQ.status)
        rows = (await self.session.execute(stmt)).all()

        # Build stage map
        stage_map: dict[str, dict[str, Any]] = {
            s: {"status": s, "count": 0, "avg_age_days": None}
            for s in self.RFQ_FUNNEL_STAGES
        }
        total = 0
        for row in rows:
            status = row.status
            if status not in stage_map:
                stage_map[status] = {"status": status, "count": 0, "avg_age_days": None}
            stage_map[status]["count"] = int(row.count)
            stage_map[status]["avg_age_days"] = (
                round(float(row.avg_age_days), 1) if row.avg_age_days else None
            )
            total += int(row.count)

        # Conversion rates: count at each stage / total submitted
        submitted = stage_map.get("SUBMITTED", {}).get("count", 0) or 1  # avoid /0
        stages = list(stage_map.values())
        for s in stages:
            s["conversion_rate_pct"] = (
                round(s["count"] / submitted * 100, 1) if submitted else None
            )

        return {
            "total_rfqs": total,
            "filters_applied": {
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "customer_id": customer_id,
                "mode": mode,
            },
            "stages": stages,
        }

    # ------------------------------------------------------------------
    # 7.2  Quotation Win / Loss
    # ------------------------------------------------------------------

    # Existing quotation statuses that represent a win or a loss
    WIN_STATUSES = {"ACCEPTED", "WON"}
    LOSS_STATUSES = {"LOST", "DECLINED", "EXPIRED"}

    async def quotation_win_loss(
        self,
        *,
        tenant_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        customer_id: str | None = None,
        carrier_id: str | None = None,
        origin_location_id: str | None = None,
        destination_location_id: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate win/loss by customer, lane, and carrier from existing
        Quotation, RFQ, RateVersion, Rate, and Carrier tables.

        Revenue figures come from QuotationOption.total_sell.
        """
        effective_carrier_id = func.coalesce(Rate.carrier_id, RFQ.preferred_carrier_id)
        stmt = (
            select(
                Quotation.status,
                Quotation.customer_id if hasattr(Quotation, "customer_id") else RFQ.customer_id,
                RFQ.customer_id.label("rfq_customer_id"),
                RFQ.mode,
                RFQ.origin_location_id,
                RFQ.destination_location_id,
                effective_carrier_id.label("carrier_id"),
                Carrier.name.label("carrier_name"),
                func.count(Quotation.id).label("count"),
                func.sum(QuotationOption.total_sell).label("total_sell"),
                func.avg(QuotationOption.total_sell).label("avg_sell"),
            )
            .join(RFQ, Quotation.rfq_id == RFQ.id)
            .outerjoin(QuotationOption, QuotationOption.quotation_id == Quotation.id)
            .outerjoin(RateVersion, QuotationOption.primary_rate_version_id == RateVersion.id)
            .outerjoin(Rate, RateVersion.rate_id == Rate.id)
            .outerjoin(Carrier, Carrier.id == effective_carrier_id)
            .where(Quotation.tenant_id == tenant_id)
        )

        if date_from:
            stmt = stmt.where(
                Quotation.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to:
            stmt = stmt.where(
                Quotation.created_at <= datetime.combine(date_to, datetime.max.time())
            )
        c_uuid = _parse_uuid(customer_id)
        if c_uuid:
            stmt = stmt.where(RFQ.customer_id == c_uuid)
        car_uuid = _parse_uuid(carrier_id)
        if car_uuid:
            stmt = stmt.where(effective_carrier_id == car_uuid)

        o_uuid = _parse_uuid(origin_location_id)
        d_uuid = _parse_uuid(destination_location_id)
        if o_uuid:
            stmt = stmt.where(RFQ.origin_location_id == o_uuid)
        if d_uuid:
            stmt = stmt.where(RFQ.destination_location_id == d_uuid)

        stmt = stmt.group_by(
            Quotation.status,
            RFQ.customer_id,
            RFQ.mode,
            RFQ.origin_location_id,
            RFQ.destination_location_id,
            effective_carrier_id,
            Carrier.name,
        )

        rows = (await self.session.execute(stmt)).all()

        # Aggregate into summary
        wins = losses = other = 0
        win_value = loss_value = 0.0
        by_customer: dict[str, dict] = {}
        by_lane: dict[str, dict] = {}
        by_mode: dict[str, dict] = {}
        by_carrier: dict[str, dict] = {}

        for row in rows:
            status = row.status
            count = int(row.count or 0)
            sell = float(row.total_sell or 0.0)
            cust = str(row.rfq_customer_id) if row.rfq_customer_id else "unknown"
            o_id = str(row.origin_location_id) if row.origin_location_id else "?"
            d_id = str(row.destination_location_id) if row.destination_location_id else "?"
            lane_key = f"{o_id}→{d_id}"
            mode_key = row.mode or "UNKNOWN"

            is_win = status in self.WIN_STATUSES
            is_loss = status in self.LOSS_STATUSES

            if is_win:
                wins += count
                win_value += sell
            elif is_loss:
                losses += count
                loss_value += sell
            else:
                other += count

            # By customer
            if cust not in by_customer:
                by_customer[cust] = {"customer_id": cust, "wins": 0, "losses": 0, "total": 0, "win_value": 0.0}
            by_customer[cust]["wins" if is_win else "losses" if is_loss else "total"] += count
            by_customer[cust]["total"] += count
            if is_win:
                by_customer[cust]["win_value"] += sell

            # By lane
            if lane_key not in by_lane:
                by_lane[lane_key] = {
                    "lane": lane_key,
                    "origin_location_id": o_id,
                    "destination_location_id": d_id,
                    "wins": 0, "losses": 0, "total": 0, "win_value": 0.0,
                }
            by_lane[lane_key]["wins" if is_win else "losses" if is_loss else "total"] += count
            by_lane[lane_key]["total"] += count
            if is_win:
                by_lane[lane_key]["win_value"] += sell

            # By mode
            if mode_key not in by_mode:
                by_mode[mode_key] = {"mode": mode_key, "wins": 0, "losses": 0, "total": 0}
            by_mode[mode_key]["wins" if is_win else "losses" if is_loss else "total"] += count
            by_mode[mode_key]["total"] += count

            # By carrier
            car_id_str = str(row.carrier_id) if row.carrier_id else "unassigned"
            car_name_str = row.carrier_name or ("Unknown Carrier" if row.carrier_id else "Unassigned Carrier")
            if car_id_str not in by_carrier:
                by_carrier[car_id_str] = {
                    "carrier_id": car_id_str,
                    "carrier_name": car_name_str,
                    "wins": 0,
                    "losses": 0,
                    "total": 0,
                    "win_value": 0.0,
                    "win_rate_pct": 0.0,
                }
            by_carrier[car_id_str]["wins" if is_win else "losses" if is_loss else "total"] += count
            by_carrier[car_id_str]["total"] += count
            if is_win:
                by_carrier[car_id_str]["win_value"] += sell

        total = wins + losses + other
        win_rate = round(wins / total * 100, 1) if total else 0.0

        # Add win_rate percentages
        for v in by_customer.values():
            t = v["total"] or 1
            v["win_rate_pct"] = round(v["wins"] / t * 100, 1)
        for v in by_lane.values():
            t = v["total"] or 1
            v["win_rate_pct"] = round(v["wins"] / t * 100, 1)
        for v in by_carrier.values():
            t = v["total"] or 1
            v["win_rate_pct"] = round(v["wins"] / t * 100, 1)
            v["win_value"] = round(v["win_value"], 2)

        return {
            "summary": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "other": other,
                "win_rate_pct": win_rate,
                "win_value": round(win_value, 2),
                "loss_value": round(loss_value, 2),
            },
            "by_customer": list(by_customer.values()),
            "by_lane": list(by_lane.values()),
            "by_mode": list(by_mode.values()),
            "by_carrier": list(by_carrier.values()),
        }

    # ------------------------------------------------------------------
    # 7.3  Revenue Analytics
    # ------------------------------------------------------------------

    async def revenue_analytics(
        self,
        *,
        tenant_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
        customer_id: str | None = None,
        mode: str | None = None,
        origin_location_id: str | None = None,
        destination_location_id: str | None = None,
        branch_id: str | None = None,
    ) -> dict[str, Any]:
        """Revenue sourced from QuotationOption.total_sell for ACCEPTED/WON
        quotations.

        Branch is derived via the assigned user / creator through UserBranchRole -> Branch.
        """
        effective_user_id = func.coalesce(RFQ.assigned_to, Quotation.created_by, RFQ.created_by)
        stmt = (
            select(
                RFQ.customer_id,
                RFQ.mode,
                RFQ.origin_location_id,
                RFQ.destination_location_id,
                Branch.id.label("branch_id"),
                Branch.name.label("branch_name"),
                Branch.code.label("branch_code"),
                func.count(Quotation.id).label("quote_count"),
                func.sum(QuotationOption.total_sell).label("total_revenue"),
                func.avg(QuotationOption.total_sell).label("avg_revenue"),
                func.min(QuotationOption.total_sell).label("min_revenue"),
                func.max(QuotationOption.total_sell).label("max_revenue"),
            )
            .join(RFQ, Quotation.rfq_id == RFQ.id)
            .outerjoin(QuotationOption, QuotationOption.quotation_id == Quotation.id)
            .outerjoin(UserBranchRole, UserBranchRole.user_id == effective_user_id)
            .outerjoin(Branch, Branch.id == UserBranchRole.branch_id)
            .where(
                Quotation.tenant_id == tenant_id,
                Quotation.status.in_(list(self.WIN_STATUSES)),
            )
        )

        if date_from:
            stmt = stmt.where(
                Quotation.created_at >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to:
            stmt = stmt.where(
                Quotation.created_at <= datetime.combine(date_to, datetime.max.time())
            )
        c_uuid = _parse_uuid(customer_id)
        if c_uuid:
            stmt = stmt.where(RFQ.customer_id == c_uuid)
        if mode:
            stmt = stmt.where(RFQ.mode == mode.upper())
        o_uuid = _parse_uuid(origin_location_id)
        if o_uuid:
            stmt = stmt.where(RFQ.origin_location_id == o_uuid)
        d_uuid = _parse_uuid(destination_location_id)
        if d_uuid:
            stmt = stmt.where(RFQ.destination_location_id == d_uuid)
        b_uuid = _parse_uuid(branch_id)
        if b_uuid:
            stmt = stmt.where(Branch.id == b_uuid)

        stmt = stmt.group_by(
            RFQ.customer_id,
            RFQ.mode,
            RFQ.origin_location_id,
            RFQ.destination_location_id,
            Branch.id,
            Branch.name,
            Branch.code,
        )

        rows = (await self.session.execute(stmt)).all()

        grand_total = 0.0
        by_customer: dict[str, dict] = {}
        by_mode: dict[str, dict] = {}
        by_lane: dict[str, dict] = {}
        by_branch: dict[str, dict] = {}
        entries = []

        for row in rows:
            cust = str(row.customer_id) if row.customer_id else "unknown"
            mode_key = row.mode or "UNKNOWN"
            o_id = str(row.origin_location_id) if row.origin_location_id else None
            d_id = str(row.destination_location_id) if row.destination_location_id else None
            lane_key = f"{o_id}→{d_id}" if o_id and d_id else "unknown"
            br_id_str = str(row.branch_id) if row.branch_id else "unassigned"
            br_name_str = row.branch_name or ("Unassigned Branch" if not row.branch_id else "Branch")
            br_code_str = row.branch_code or "N/A"
            rev = float(row.total_revenue or 0.0)
            grand_total += rev

            entries.append(
                {
                    "customer_id": cust,
                    "mode": mode_key,
                    "origin_location_id": o_id,
                    "destination_location_id": d_id,
                    "branch_id": br_id_str,
                    "branch_name": br_name_str,
                    "quote_count": int(row.quote_count or 0),
                    "total_revenue": round(rev, 2),
                    "avg_revenue": round(float(row.avg_revenue or 0.0), 2),
                    "min_revenue": round(float(row.min_revenue or 0.0), 2),
                    "max_revenue": round(float(row.max_revenue or 0.0), 2),
                }
            )
            by_customer.setdefault(cust, {"customer_id": cust, "total_revenue": 0.0})
            by_customer[cust]["total_revenue"] += rev
            by_mode.setdefault(mode_key, {"mode": mode_key, "total_revenue": 0.0})
            by_mode[mode_key]["total_revenue"] += rev
            by_lane.setdefault(lane_key, {"lane": lane_key, "total_revenue": 0.0})
            by_lane[lane_key]["total_revenue"] += rev
            by_branch.setdefault(
                br_id_str,
                {
                    "branch_id": br_id_str,
                    "branch_name": br_name_str,
                    "branch_code": br_code_str,
                    "total_revenue": 0.0,
                    "quote_count": 0,
                },
            )
            by_branch[br_id_str]["total_revenue"] += rev
            by_branch[br_id_str]["quote_count"] += int(row.quote_count or 0)

        limitations = [
            "Revenue source: QuotationOption.total_sell for ACCEPTED/WON quotations.",
            "Branch dimension: Derived via RFQ assigned_to / created_by user associated with Branch via UserBranchRole. Quotations without assigned branch users appear under 'unassigned'. Direct branch assignment on RFQ/Quotation would require adding an explicit branch_id column.",
            "Recognised revenue: RevenueLine table (domain.py) exists but is populated only after shipment creation; QuotationOption is used as the commercial pipeline revenue source.",
        ]

        return {
            "grand_total_revenue": round(grand_total, 2),
            "entry_count": len(entries),
            "by_customer": [
                {**v, "total_revenue": round(v["total_revenue"], 2)}
                for v in by_customer.values()
            ],
            "by_mode": [
                {**v, "total_revenue": round(v["total_revenue"], 2)}
                for v in by_mode.values()
            ],
            "by_lane": [
                {**v, "total_revenue": round(v["total_revenue"], 2)}
                for v in by_lane.values()
            ],
            "by_branch": [
                {**v, "total_revenue": round(v["total_revenue"], 2)}
                for v in by_branch.values()
            ],
            "entries": entries,
            "limitations": limitations,
        }

    # ------------------------------------------------------------------
    # 7.4  Rate Competitiveness Analysis
    # ------------------------------------------------------------------

    async def rate_competitiveness(
        self,
        *,
        tenant_id: uuid.UUID,
        as_of_date: date | None = None,
        mode: str | None = None,
        top_n: int = 20,
    ) -> dict[str, Any]:
        """Compare contracted rates against market averages for the top lanes.

        Market data must be pre-loaded into the market_rates table.
        If no market data exists, lanes are still returned with
        market_amount=null and competitiveness="NO_MARKET_DATA".
        """
        today = as_of_date or date.today()

        # Active contracted rates
        rate_q = (
            select(Rate)
            .where(
                Rate.tenant_id == tenant_id,
                Rate.effective_date <= today,
                Rate.expiry_date >= today,
                Rate.status.in_(["APPROVED", "ACTIVE"]),
                Rate.origin_location_id.isnot(None),
                Rate.destination_location_id.isnot(None),
            )
        )
        if mode:
            rate_q = rate_q.where(Rate.rate_type.ilike(f"%{mode}%"))
        rate_q = rate_q.limit(top_n)

        rates = (await self.session.execute(rate_q)).scalars().all()

        results = []
        for rate in rates:
            # Best contracted rate line amount from latest APPROVED version
            from app.db.models.commercial import RateVersion, RateLine
            ver_q = (
                select(RateVersion)
                .where(
                    RateVersion.rate_id == rate.id,
                    RateVersion.approval_status == "APPROVED",
                )
                .order_by(RateVersion.version_number.desc())
                .limit(1)
            )
            version = (await self.session.execute(ver_q)).scalar_one_or_none()
            contracted_amount = None
            if version:
                line_q = select(RateLine).where(RateLine.rate_version_id == version.id).limit(1)
                line = (await self.session.execute(line_q)).scalar_one_or_none()
                if line:
                    contracted_amount = float(line.amount)

            # Market benchmark
            mr_q = (
                select(MarketRate)
                .where(
                    MarketRate.tenant_id == tenant_id,
                    MarketRate.origin_location_id == rate.origin_location_id,
                    MarketRate.destination_location_id == rate.destination_location_id,
                    MarketRate.rate_type == rate.rate_type,
                    MarketRate.effective_date <= today,
                    or_(
                        MarketRate.expiry_date.is_(None),
                        MarketRate.expiry_date >= today,
                    ),
                )
                .order_by(MarketRate.effective_date.desc())
                .limit(1)
            )
            mr = (await self.session.execute(mr_q)).scalar_one_or_none()
            market_amount = float(mr.amount) if mr else None

            variance = None
            variance_pct = None
            competitiveness = "NO_MARKET_DATA"

            if contracted_amount is not None and market_amount is not None:
                variance = round(contracted_amount - market_amount, 4)
                variance_pct = (
                    round(variance / market_amount * 100, 2)
                    if market_amount != 0
                    else None
                )
                if abs(variance) <= 0.01 * market_amount:
                    competitiveness = "COMPETITIVE"
                elif contracted_amount < market_amount:
                    competitiveness = "BELOW_MARKET"
                else:
                    competitiveness = "ABOVE_MARKET"

            results.append(
                {
                    "rate_id": str(rate.id),
                    "rate_number": rate.rate_number,
                    "rate_type": rate.rate_type,
                    "origin_location_id": str(rate.origin_location_id),
                    "destination_location_id": str(rate.destination_location_id),
                    "currency_code": rate.currency_code,
                    "contracted_amount": contracted_amount,
                    "market_amount": market_amount,
                    "market_source": mr.source if mr else None,
                    "variance": variance,
                    "variance_pct": variance_pct,
                    "competitiveness": competitiveness,
                    "effective_date": str(rate.effective_date),
                    "expiry_date": str(rate.expiry_date),
                }
            )

        market_data_note = (
            "Market rate data must be provided via POST /api/v1/financial/market-rates. "
            "Lanes with no market data show competitiveness='NO_MARKET_DATA'."
            if not any(r["market_amount"] is not None for r in results)
            else None
        )

        return {
            "as_of_date": str(today),
            "total_lanes": len(results),
            "lanes": results,
            "market_data_note": market_data_note,
        }

    # ------------------------------------------------------------------
    # 7.5  Rate Utilisation Heatmap
    # ------------------------------------------------------------------

    async def rate_heatmap(
        self,
        *,
        tenant_id: uuid.UUID,
        as_of_date: date | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Return per-lane active-rate counts suitable for a heatmap.

        A rate is "active" when:
          - status IN ('APPROVED','ACTIVE')
          - effective_date <= today
          - expiry_date >= today

        Expired rates are excluded.
        """
        today = as_of_date or date.today()

        stmt = (
            select(
                Rate.origin_location_id,
                Rate.destination_location_id,
                Rate.rate_type,
                Rate.mode if hasattr(Rate, "mode") else Rate.rate_type,
                func.count(Rate.id).label("active_rate_count"),
            )
            .where(
                Rate.tenant_id == tenant_id,
                Rate.origin_location_id.isnot(None),
                Rate.destination_location_id.isnot(None),
                Rate.effective_date <= today,
                Rate.expiry_date >= today,
                Rate.status.in_(["APPROVED", "ACTIVE"]),
            )
        )

        if mode:
            stmt = stmt.where(Rate.rate_type.ilike(f"%{mode}%"))

        stmt = stmt.group_by(
            Rate.origin_location_id,
            Rate.destination_location_id,
            Rate.rate_type,
        )

        rows = (await self.session.execute(stmt)).all()

        heatmap_cells = []
        for row in rows:
            count = int(row.active_rate_count)
            heatmap_cells.append(
                {
                    "origin_location_id": str(row.origin_location_id),
                    "destination_location_id": str(row.destination_location_id),
                    "rate_type": row.rate_type,
                    "active_rate_count": count,
                    "coverage_status": "COVERED" if count > 0 else "UNCOVERED",
                }
            )

        total_covered = len(heatmap_cells)
        total_active_rates = sum(c["active_rate_count"] for c in heatmap_cells)

        return {
            "as_of_date": str(today),
            "total_lanes_covered": total_covered,
            "total_active_rates": total_active_rates,
            "cells": heatmap_cells,
            "note": (
                "Only lanes with at least one active rate appear here. "
                "Lanes with no coverage do not appear because the system "
                "has no exhaustive lane catalogue to compare against. "
                "Use the rate review endpoint to identify soon-to-expire lanes."
            ),
        }
