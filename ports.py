"""
Repository Ports (interfaces) - Ports & Adapters pattern.

WHY THIS FILE EXISTS:
Team 1 owns the real Postgres database. We don't have it yet, and we
shouldn't wait for it. So every piece of Phase 2 business logic below
talks to a *Repository* - an abstract interface - never to a database
directly.

Today, that Repository is backed by a plain Python dict (InMemoryRepository).
Later, someone implements a PostgresRepository with the exact same methods
(get/list/add/update/delete) and plugs it in. Zero business logic changes.

This is intentionally ONE generic implementation reused for every entity
(Country, Rate, Customer, etc.) rather than 30 near-identical classes -
they all need the same four operations, so one generic class does the job.
"""

from typing import Protocol, TypeVar, Generic, Any, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Repository(Protocol[T]):
    def get(self, entity_id: str) -> T | None: ...
    def list(self, **filters: Any) -> list[T]: ...
    def add(self, entity: T) -> T: ...
    def update(self, entity: T) -> T: ...
    def delete(self, entity_id: str) -> bool: ...


class InMemoryRepository(Generic[T]):
    """
    In-memory adapter implementing the Repository port.
    Good for unit tests today, and for running the whole service layer
    standalone before Team 1's DB exists.
    """

    def __init__(self, id_attr: str = "id"):
        self._store: dict[str, T] = {}
        self._id_attr = id_attr

    def get(self, entity_id: str) -> T | None:
        return self._store.get(entity_id)

    def list(self, **filters: Any) -> list[T]:
        items = list(self._store.values())
        for key, value in filters.items():
            items = [i for i in items if getattr(i, key, None) == value]
        return items

    def add(self, entity: T) -> T:
        entity_id = getattr(entity, self._id_attr)
        if entity_id in self._store:
            raise ValueError(f"Entity with id '{entity_id}' already exists")
        self._store[entity_id] = entity
        return entity

    def update(self, entity: T) -> T:
        entity_id = getattr(entity, self._id_attr)
        if entity_id not in self._store:
            raise ValueError(f"Entity with id '{entity_id}' not found")
        self._store[entity_id] = entity
        return entity

    def delete(self, entity_id: str) -> bool:
        return self._store.pop(entity_id, None) is not None

    def count(self) -> int:
        return len(self._store)


class ImmutableRepository(InMemoryRepository[T]):
    """
    Same as InMemoryRepository, but blocks update() entirely.

    Used for RATE_VERSION: per SRS, a rate version is never edited once
    created - any change must be a brand new version. This class makes
    that rule impossible to accidentally violate in code, rather than
    relying on developers remembering not to call update().
    """

    def update(self, entity: T) -> T:
        raise ValueError(
            "This entity is immutable once created - create a new version instead "
            "of updating an existing one."
        )