from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models import (
    CraftStation,
    Equipment,
    Item,
    ItemGroup,
    ItemSubgroup,
    Recipe,
    RecipeEquipmentRequirement,
    RecipeSkillRequirement,
    RecipeSkillReward,
    Skill,
)


ReferenceModel = TypeVar("ReferenceModel", bound=Base)


class ReferenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_stations(self) -> list[CraftStation]:
        return list(self.session.scalars(select(CraftStation).order_by(CraftStation.sort_order, CraftStation.name)))

    def list_groups(self) -> list[ItemGroup]:
        return list(self.session.scalars(select(ItemGroup).order_by(ItemGroup.sort_order, ItemGroup.name)))

    def list_subgroups(self, group_id: int | None = None) -> list[ItemSubgroup]:
        statement: Select[tuple[ItemSubgroup]] = select(ItemSubgroup)
        if group_id is not None:
            statement = statement.where(ItemSubgroup.group_id == group_id)
        statement = statement.order_by(ItemSubgroup.sort_order, ItemSubgroup.name)
        return list(self.session.scalars(statement))

    def list_skills(self) -> list[Skill]:
        return list(self.session.scalars(select(Skill).order_by(Skill.name)))

    def list_equipment(self) -> list[Equipment]:
        return list(self.session.scalars(select(Equipment).order_by(Equipment.name)))

    def get_required(self, model: type[ReferenceModel], entity_id: int) -> ReferenceModel | None:
        return self.session.get(model, entity_id)

    def add(self, entity: ReferenceModel) -> ReferenceModel:
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: Base) -> None:
        self.session.delete(entity)
        self.session.flush()

    def count_station_dependencies(self, entity_id: int) -> int:
        return self._count(Recipe, Recipe.craft_station_id == entity_id)

    def count_group_dependencies(self, entity_id: int) -> tuple[int, int]:
        return (
            self._count(ItemSubgroup, ItemSubgroup.group_id == entity_id),
            self._count(Item, Item.group_id == entity_id),
        )

    def count_subgroup_dependencies(self, entity_id: int) -> int:
        return self._count(Item, Item.subgroup_id == entity_id)

    def count_skill_dependencies(self, entity_id: int) -> tuple[int, int]:
        return (
            self._count(RecipeSkillRequirement, RecipeSkillRequirement.skill_id == entity_id),
            self._count(RecipeSkillReward, RecipeSkillReward.skill_id == entity_id),
        )

    def count_equipment_dependencies(self, entity_id: int) -> int:
        return self._count(
            RecipeEquipmentRequirement,
            RecipeEquipmentRequirement.equipment_id == entity_id,
        )

    def _count(self, model: type[Base], criterion: Any) -> int:
        return int(self.session.scalar(select(func.count()).select_from(model).where(criterion)) or 0)

