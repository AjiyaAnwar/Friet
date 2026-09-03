import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.modules.commercial.ports import InMemoryRepository
from app.modules.commercial.master_data.models import Location, Incoterm
from app.modules.commercial.master_data.services import MasterDataLookupService, LocationSearchService


def test_lookup_by_code_success():
    repo = InMemoryRepository[Incoterm](id_attr="code")
    repo.add(Incoterm(code="FOB", name="Free On Board"))
    service = MasterDataLookupService(repo)
    assert service.get_by_code("FOB").name == "Free On Board"


def test_lookup_by_code_missing_raises():
    repo = InMemoryRepository[Incoterm](id_attr="code")
    service = MasterDataLookupService(repo)
    with pytest.raises(LookupError):
        service.get_by_code("XXX")


def test_location_search_by_city():
    repo = InMemoryRepository[Location]()
    repo.add(Location(id="1", un_locode="PKKAR", iata_code="KHI", name="Jinnah International",
                       country_id="PK", city="Karachi", type="AIRPORT", timezone="Asia/Karachi"))
    repo.add(Location(id="2", un_locode="AEJEA", iata_code=None, name="Jebel Ali",
                       country_id="AE", city="Dubai", type="SEA_PORT", timezone="Asia/Dubai"))

    service = LocationSearchService(repo)
    results = service.search("karachi")
    assert len(results) == 1
    assert results[0].city == "Karachi"


def test_location_search_filters_by_type():
    repo = InMemoryRepository[Location]()
    repo.add(Location(id="1", un_locode="PKKAR", iata_code="KHI", name="Jinnah International",
                       country_id="PK", city="Karachi", type="AIRPORT", timezone="Asia/Karachi"))
    repo.add(Location(id="2", un_locode="PKQCT", iata_code=None, name="Karachi Port",
                       country_id="PK", city="Karachi", type="SEA_PORT", timezone="Asia/Karachi"))

    service = LocationSearchService(repo)
    results = service.search("karachi", location_type="AIRPORT")
    assert len(results) == 1
    assert results[0].type == "AIRPORT"


def test_location_search_excludes_inactive():
    repo = InMemoryRepository[Location]()
    repo.add(Location(id="1", un_locode="PKKAR", iata_code="KHI", name="Jinnah International",
                       country_id="PK", city="Karachi", type="AIRPORT", timezone="Asia/Karachi",
                       is_active=False))
    service = LocationSearchService(repo)
    assert service.search("karachi") == []


def test_empty_query_returns_all_active():
    repo = InMemoryRepository[Location]()
    repo.add(Location(id="1", un_locode="PKKAR", iata_code="KHI", name="A",
                       country_id="PK", city="Karachi", type="AIRPORT", timezone="Asia/Karachi"))
    service = LocationSearchService(repo)
    assert len(service.search("")) == 1