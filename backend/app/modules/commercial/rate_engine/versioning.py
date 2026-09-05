"""
Rate Versioning Service.

Per SRS: "Every modification creates a new version record (previous
version immutable)." We enforce this structurally: RATE_VERSION and
RATE_LINE are stored in an ImmutableRepository (see ports.py), so calling
.update() on an existing version raises an error by design - the only
way to change a rate's pricing is to create a brand new version.

Rate approval STATE TRANSITIONS (DRAFT -> PENDING_APPROVAL -> APPROVED
-> ...) are explicitly a Team 1 dependency (via their state machine
engine) and are NOT implemented here.
"""

from dataclasses import replace
from datetime import datetime, timezone

from app.modules.commercial.ports import ImmutableRepository, InMemoryRepository
from app.modules.commercial.rate_engine.models import RateVersion, RateLine


class RateVersioningService:
    def __init__(
        self,
        rate_version_repo: ImmutableRepository,
        rate_line_repo: ImmutableRepository,
        id_generator,
    ):
        self._version_repo = rate_version_repo
        self._line_repo = rate_line_repo
        self._new_id = id_generator

    def create_new_version(
        self,
        rate_id: str,
        modified_by: str,
        reason: str,
        lines: list[RateLine],
        modified_date: datetime | None = None,
    ) -> RateVersion:
        existing_versions = self._version_repo.list(rate_id=rate_id)
        next_version_number = (
            max((v.version_number for v in existing_versions), default=0) + 1
        )

        version = RateVersion(
            id=self._new_id(),
            rate_id=rate_id,
            version_number=next_version_number,
            modified_by=modified_by,
            modified_date=modified_date or datetime.now(timezone.utc),
            reason=reason,
            approval_status="DRAFT",
        )
        self._version_repo.add(version)

        for line in lines:
            stamped_line = replace(line, id=self._new_id(), rate_version_id=version.id)
            self._line_repo.add(stamped_line)

        return version

    def get_latest_version(self, rate_id: str) -> RateVersion | None:
        versions = self._version_repo.list(rate_id=rate_id)
        if not versions:
            return None
        return max(versions, key=lambda v: v.version_number)

    def get_lines_for_version(self, rate_version_id: str) -> list[RateLine]:
        return self._line_repo.list(rate_version_id=rate_version_id)

    def compare_versions(self, rate_id: str, version_a: int, version_b: int) -> dict:
        versions = {v.version_number: v for v in self._version_repo.list(rate_id=rate_id)}
        if version_a not in versions or version_b not in versions:
            raise ValueError("One or both version numbers do not exist for this rate")

        return {
            "version_a": versions[version_a],
            "version_b": versions[version_b],
            "lines_a": self.get_lines_for_version(versions[version_a].id),
            "lines_b": self.get_lines_for_version(versions[version_b].id),
        }
