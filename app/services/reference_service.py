from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CraftStation, Equipment, ItemGroup, ItemSubgroup, Skill
from app.repositories.reference_repository import ReferenceRepository
from app.services.access import AccessController
from app.services.errors import DependencyError, NotFoundError, ValidationError
from app.utils.text import normalized_key


@dataclass(frozen=True, slots=True)
class StationInput:
    name: str
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class GroupInput:
    name: str
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class SubgroupInput:
    group_id: int
    name: str
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class SkillInput:
    name: str
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class EquipmentInput:
    name: str
    description: str | None = None
    image_path: str | None = None
    is_active: bool = True


class ReferenceService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        access: AccessController,
    ) -> None:
        self.session_factory = session_factory
        self.access = access

    def list_stations(self) -> list[CraftStation]:
        with self.session_factory() as session:
            return ReferenceRepository(session).list_stations()

    def list_groups(self) -> list[ItemGroup]:
        with self.session_factory() as session:
            return ReferenceRepository(session).list_groups()

    def list_subgroups(self, group_id: int | None = None) -> list[ItemSubgroup]:
        with self.session_factory() as session:
            rows = ReferenceRepository(session).list_subgroups(group_id)
            for row in rows:
                _ = row.group.name
            return rows

    def list_skills(self) -> list[Skill]:
        with self.session_factory() as session:
            return ReferenceRepository(session).list_skills()

    def list_equipment(self) -> list[Equipment]:
        with self.session_factory() as session:
            return ReferenceRepository(session).list_equipment()

    def create_station(self, data: StationInput) -> CraftStation:
        self.access.require_admin()
        clean_name = self._name(data.name)
        return self._create(
            CraftStation(
                name=clean_name,
                name_key=normalized_key(clean_name),
                description=self._optional(data.description),
                sort_order=data.sort_order,
                is_active=data.is_active,
            ),
            "Стол с таким названием уже существует.",
        )

    def update_station(self, entity_id: int, data: StationInput) -> CraftStation:
        return self._update(
            CraftStation,
            entity_id,
            {
                "name": self._name(data.name),
                "name_key": normalized_key(self._name(data.name)),
                "description": self._optional(data.description),
                "sort_order": data.sort_order,
                "is_active": data.is_active,
            },
            "Стол с таким названием уже существует.",
        )

    def create_group(self, data: GroupInput) -> ItemGroup:
        self.access.require_admin()
        return self._create(
            ItemGroup(
                name=self._name(data.name),
                name_key=normalized_key(self._name(data.name)),
                sort_order=data.sort_order,
            ),
            "Группа с таким названием уже существует.",
        )

    def update_group(self, entity_id: int, data: GroupInput) -> ItemGroup:
        return self._update(
            ItemGroup,
            entity_id,
            {
                "name": self._name(data.name),
                "name_key": normalized_key(self._name(data.name)),
                "sort_order": data.sort_order,
            },
            "Группа с таким названием уже существует.",
        )

    def create_subgroup(self, data: SubgroupInput) -> ItemSubgroup:
        self.access.require_admin()
        self._ensure_group(data.group_id)
        return self._create(
            ItemSubgroup(
                group_id=data.group_id,
                name=self._name(data.name),
                name_key=normalized_key(self._name(data.name)),
                sort_order=data.sort_order,
            ),
            "Такая подгруппа уже существует в выбранной группе.",
        )

    def update_subgroup(self, entity_id: int, data: SubgroupInput) -> ItemSubgroup:
        self._ensure_group(data.group_id)
        return self._update(
            ItemSubgroup,
            entity_id,
            {
                "group_id": data.group_id,
                "name": self._name(data.name),
                "name_key": normalized_key(self._name(data.name)),
                "sort_order": data.sort_order,
            },
            "Такая подгруппа уже существует в выбранной группе.",
        )

    def create_skill(self, data: SkillInput) -> Skill:
        self.access.require_admin()
        return self._create(
            Skill(
                name=self._name(data.name),
                name_key=normalized_key(self._name(data.name)),
                description=self._optional(data.description),
                is_active=data.is_active,
            ),
            "Навык с таким названием уже существует.",
        )

    def update_skill(self, entity_id: int, data: SkillInput) -> Skill:
        return self._update(
            Skill,
            entity_id,
            {
                "name": self._name(data.name),
                "name_key": normalized_key(self._name(data.name)),
                "description": self._optional(data.description),
                "is_active": data.is_active,
            },
            "Навык с таким названием уже существует.",
        )

    def create_equipment(self, data: EquipmentInput) -> Equipment:
        self.access.require_admin()
        return self._create(
            Equipment(
                name=self._name(data.name),
                name_key=normalized_key(self._name(data.name)),
                description=self._optional(data.description),
                image_path=self._optional(data.image_path),
                is_active=data.is_active,
            ),
            "Оборудование с таким названием уже существует.",
        )

    def update_equipment(self, entity_id: int, data: EquipmentInput) -> Equipment:
        return self._update(
            Equipment,
            entity_id,
            {
                "name": self._name(data.name),
                "name_key": normalized_key(self._name(data.name)),
                "description": self._optional(data.description),
                "image_path": self._optional(data.image_path),
                "is_active": data.is_active,
            },
            "Оборудование с таким названием уже существует.",
        )

    def delete_station(self, entity_id: int) -> None:
        self._delete_with_check(
            CraftStation,
            entity_id,
            lambda repo: self._single_dependency(
                repo.count_station_dependencies(entity_id), "рецептах"
            ),
        )

    def delete_group(self, entity_id: int) -> None:
        def dependencies(repo: ReferenceRepository) -> str | None:
            subgroups, items = repo.count_group_dependencies(entity_id)
            parts = []
            if subgroups:
                parts.append(f"подгруппы: {subgroups}")
            if items:
                parts.append(f"предметы: {items}")
            return ", ".join(parts) or None

        self._delete_with_check(ItemGroup, entity_id, dependencies)

    def delete_subgroup(self, entity_id: int) -> None:
        self._delete_with_check(
            ItemSubgroup,
            entity_id,
            lambda repo: self._single_dependency(repo.count_subgroup_dependencies(entity_id), "предметах"),
        )

    def delete_skill(self, entity_id: int) -> None:
        def dependencies(repo: ReferenceRepository) -> str | None:
            requirements, rewards = repo.count_skill_dependencies(entity_id)
            parts = []
            if requirements:
                parts.append(f"требования рецептов: {requirements}")
            if rewards:
                parts.append(f"награды рецептов: {rewards}")
            return ", ".join(parts) or None

        self._delete_with_check(Skill, entity_id, dependencies)

    def delete_equipment(self, entity_id: int) -> None:
        self._delete_with_check(
            Equipment,
            entity_id,
            lambda repo: self._single_dependency(
                repo.count_equipment_dependencies(entity_id), "рецептах"
            ),
        )

    def _create(self, entity: object, duplicate_message: str):
        try:
            with self.session_factory.begin() as session:
                return ReferenceRepository(session).add(entity)  # type: ignore[arg-type]
        except IntegrityError as exc:
            raise ValidationError(duplicate_message) from exc

    def _update(
        self,
        model: type,
        entity_id: int,
        values: dict[str, object],
        duplicate_message: str,
    ):
        self.access.require_admin()
        try:
            with self.session_factory.begin() as session:
                entity = ReferenceRepository(session).get_required(model, entity_id)
                if entity is None:
                    raise NotFoundError("Запись справочника не найдена.")
                for key, value in values.items():
                    setattr(entity, key, value)
                session.flush()
                return entity
        except IntegrityError as exc:
            raise ValidationError(duplicate_message) from exc

    def _delete_with_check(self, model: type, entity_id: int, checker: Callable) -> None:
        self.access.require_admin()
        with self.session_factory.begin() as session:
            repository = ReferenceRepository(session)
            entity = repository.get_required(model, entity_id)
            if entity is None:
                raise NotFoundError("Запись справочника не найдена.")
            dependencies = checker(repository)
            if dependencies:
                raise DependencyError(
                    f'Невозможно удалить «{entity.name}»: запись используется ({dependencies}).'
                )
            repository.delete(entity)

    def _ensure_group(self, group_id: int) -> None:
        with self.session_factory() as session:
            if session.get(ItemGroup, group_id) is None:
                raise ValidationError("Выбранная группа не существует.")

    @staticmethod
    def _name(value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValidationError("Название обязательно.")
        return clean

    @staticmethod
    def _optional(value: str | None) -> str | None:
        clean = value.strip() if value else ""
        return clean or None

    @staticmethod
    def _single_dependency(count: int, label: str) -> str | None:
        return f"{label}: {count}" if count else None
