import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from dataclasses import dataclass
from ports import InMemoryRepository, ImmutableRepository


@dataclass
class Widget:
    id: str
    name: str
    category: str = "A"


def test_add_and_get():
    repo = InMemoryRepository[Widget]()
    repo.add(Widget(id="1", name="Bolt"))
    assert repo.get("1").name == "Bolt"


def test_get_missing_returns_none():
    repo = InMemoryRepository[Widget]()
    assert repo.get("missing") is None


def test_add_duplicate_id_raises():
    repo = InMemoryRepository[Widget]()
    repo.add(Widget(id="1", name="Bolt"))
    with pytest.raises(ValueError):
        repo.add(Widget(id="1", name="Nut"))


def test_list_with_filter():
    repo = InMemoryRepository[Widget]()
    repo.add(Widget(id="1", name="Bolt", category="A"))
    repo.add(Widget(id="2", name="Nut", category="B"))
    results = repo.list(category="A")
    assert len(results) == 1
    assert results[0].name == "Bolt"


def test_update_existing():
    repo = InMemoryRepository[Widget]()
    repo.add(Widget(id="1", name="Bolt"))
    repo.update(Widget(id="1", name="Bolt v2"))
    assert repo.get("1").name == "Bolt v2"


def test_update_missing_raises():
    repo = InMemoryRepository[Widget]()
    with pytest.raises(ValueError):
        repo.update(Widget(id="99", name="Ghost"))


def test_delete():
    repo = InMemoryRepository[Widget]()
    repo.add(Widget(id="1", name="Bolt"))
    assert repo.delete("1") is True
    assert repo.get("1") is None
    assert repo.delete("1") is False


def test_immutable_repository_blocks_update():
    repo = ImmutableRepository[Widget]()
    repo.add(Widget(id="1", name="Bolt"))
    with pytest.raises(ValueError):
        repo.update(Widget(id="1", name="Changed"))