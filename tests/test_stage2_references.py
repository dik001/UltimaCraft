from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.database.session import Database
from app.models import (
    CraftStation,
    Equipment,
    Item,
    ItemGroup,
    Recipe,
    RecipeEquipmentRequirement,
    RecipeSkillRequirement,
    Skill,
)
from app.services.access import AccessController, AppMode
from app.services.errors import AccessDeniedError, DependencyError, ValidationError
from app.services.reference_service import (
    EquipmentInput,
    GroupInput,
    ReferenceService,
    SkillInput,
    StationInput,
    SubgroupInput,
)


@pytest.fixture
def service(database: Database) -> ReferenceService:
    return ReferenceService(database.session_factory, AccessController(AppMode.ADMIN))


def test_crud_all_reference_types(service: ReferenceService) -> None:
    station = service.create_station(StationInput("Верстак", "Основной стол", 10, True))
    group = service.create_group(GroupInput("Боеприпасы", 20))
    subgroup = service.create_subgroup(SubgroupInput(group.id, "9 мм", 30))
    skill = service.create_skill(SkillInput("Оружейное дело", "Сборка", True))
    equipment = service.create_equipment(EquipmentInput("Набор инструментов", "Комплект"))

    service.update_station(station.id, StationInput("Улучшенный верстак", None, 11, False))
    service.update_group(group.id, GroupInput("Патроны", 21))
    service.update_subgroup(subgroup.id, SubgroupInput(group.id, "9×19 мм", 31))
    service.update_skill(skill.id, SkillInput("Оружейник", None, False))
    service.update_equipment(equipment.id, EquipmentInput("Инструменты", None, None, False))

    assert service.list_stations()[0].name == "Улучшенный верстак"
    assert service.list_groups()[0].name == "Патроны"
    assert service.list_subgroups()[0].group.name == "Патроны"
    assert service.list_skills()[0].name == "Оружейник"
    assert service.list_equipment()[0].name == "Инструменты"

    service.delete_subgroup(subgroup.id)
    service.delete_equipment(equipment.id)
    service.delete_skill(skill.id)
    service.delete_station(station.id)
    service.delete_group(group.id)
    assert service.list_groups() == []


def test_validation_duplicate_and_viewer_guard(database: Database, service: ReferenceService) -> None:
    service.create_group(GroupInput("Материалы"))
    with pytest.raises(ValidationError, match="уже существует"):
        service.create_group(GroupInput("материалы"))
    with pytest.raises(ValidationError, match="Название обязательно"):
        service.create_skill(SkillInput("   "))

    viewer_service = ReferenceService(database.session_factory, AccessController(AppMode.VIEWER))
    with pytest.raises(AccessDeniedError):
        viewer_service.create_station(StationInput("Плита"))


def test_deletion_is_blocked_by_recipe_dependencies(
    database: Database,
    service: ReferenceService,
) -> None:
    station = service.create_station(StationInput("Лаборатория"))
    group = service.create_group(GroupInput("Химия"))
    subgroup = service.create_subgroup(SubgroupInput(group.id, "Реактивы"))
    skill = service.create_skill(SkillInput("Химик"))
    equipment = service.create_equipment(EquipmentInput("Колба"))

    with database.session_factory.begin() as session:
        item = Item(name="Состав", group_id=group.id, subgroup_id=subgroup.id)
        recipe = Recipe(
            result_item=item,
            craft_station_id=station.id,
            output_quantity=Decimal("1"),
            energy_cost=Decimal("0"),
            skill_requirements=[
                RecipeSkillRequirement(skill_id=skill.id, required_level=Decimal("2"))
            ],
            equipment_requirements=[
                RecipeEquipmentRequirement(equipment_id=equipment.id, quantity=Decimal("1"))
            ],
        )
        session.add(recipe)

    for operation in (
        lambda: service.delete_station(station.id),
        lambda: service.delete_group(group.id),
        lambda: service.delete_subgroup(subgroup.id),
        lambda: service.delete_skill(skill.id),
        lambda: service.delete_equipment(equipment.id),
    ):
        with pytest.raises(DependencyError, match="Невозможно удалить"):
            operation()

    with database.session_factory() as session:
        assert session.scalar(select(CraftStation).where(CraftStation.id == station.id)) is not None
        assert session.scalar(select(ItemGroup).where(ItemGroup.id == group.id)) is not None
        assert session.scalar(select(Skill).where(Skill.id == skill.id)) is not None
        assert session.scalar(select(Equipment).where(Equipment.id == equipment.id)) is not None

