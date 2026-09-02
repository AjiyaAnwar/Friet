import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from datetime import datetime
from itertools import count

from ports import ImmutableRepository
from rate_engine.models import RateLine
from rate_engine.versioning import RateVersioningService


def make_service():
    counter = count(1)
    id_gen = lambda: f"id-{next(counter)}"
    return RateVersioningService(
        rate_version_repo=ImmutableRepository(),
        rate_line_repo=ImmutableRepository(),
        id_generator=id_gen,
    ), id_gen


def sample_line(rate_version_id="placeholder"):
    return RateLine(
        id="placeholder", rate_version_id=rate_version_id, charge_code="OFR",
        rate_basis="PER_KG", weight_break_from=0, weight_break_to=45,
        container_type_code=None, amount=5.5,
    )


def test_first_version_starts_at_1():
    service, _ = make_service()
    version = service.create_new_version("RATE-1", "user-1", "initial rate load", [sample_line()])
    assert version.version_number == 1
    assert version.approval_status == "DRAFT"


def test_second_version_increments():
    service, _ = make_service()
    service.create_new_version("RATE-1", "user-1", "v1", [sample_line()])
    v2 = service.create_new_version("RATE-1", "user-1", "rate correction", [sample_line()])
    assert v2.version_number == 2


def test_versions_for_different_rates_are_independent():
    service, _ = make_service()
    v1_rate_a = service.create_new_version("RATE-A", "user-1", "v1", [sample_line()])
    v1_rate_b = service.create_new_version("RATE-B", "user-1", "v1", [sample_line()])
    assert v1_rate_a.version_number == 1
    assert v1_rate_b.version_number == 1


def test_lines_are_correctly_associated_with_new_version():
    service, _ = make_service()
    version = service.create_new_version("RATE-1", "user-1", "v1", [sample_line(), sample_line()])
    lines = service.get_lines_for_version(version.id)
    assert len(lines) == 2
    assert all(l.rate_version_id == version.id for l in lines)


def test_cannot_update_existing_version_directly():
    service, _ = make_service()
    version = service.create_new_version("RATE-1", "user-1", "v1", [sample_line()])
    with pytest.raises(ValueError):
        service._version_repo.update(version)


def test_cannot_update_existing_line_directly():
    service, _ = make_service()
    version = service.create_new_version("RATE-1", "user-1", "v1", [sample_line()])
    lines = service.get_lines_for_version(version.id)
    with pytest.raises(ValueError):
        service._line_repo.update(lines[0])


def test_get_latest_version_returns_highest_number():
    service, _ = make_service()
    service.create_new_version("RATE-1", "user-1", "v1", [sample_line()])
    service.create_new_version("RATE-1", "user-1", "v2", [sample_line()])
    v3 = service.create_new_version("RATE-1", "user-1", "v3", [sample_line()])
    latest = service.get_latest_version("RATE-1")
    assert latest.id == v3.id
    assert latest.version_number == 3


def test_get_latest_version_none_when_no_versions_exist():
    service, _ = make_service()
    assert service.get_latest_version("NONEXISTENT") is None


def test_compare_versions_returns_both():
    service, _ = make_service()
    service.create_new_version("RATE-1", "user-1", "v1", [sample_line()])
    service.create_new_version("RATE-1", "user-1", "v2 - price increase", [sample_line()])
    comparison = service.compare_versions("RATE-1", 1, 2)
    assert comparison["version_a"].version_number == 1
    assert comparison["version_b"].version_number == 2
    assert comparison["version_b"].reason == "v2 - price increase"


def test_compare_versions_invalid_number_raises():
    service, _ = make_service()
    service.create_new_version("RATE-1", "user-1", "v1", [sample_line()])
    with pytest.raises(ValueError):
        service.compare_versions("RATE-1", 1, 99)