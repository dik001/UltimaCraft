from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CraftStation,
    Equipment,
    Item,
    Recipe,
    RecipeEquipmentRequirement,
    RecipeIngredient,
    RecipeSkillRequirement,
    RecipeSkillReward,
    Skill,
)
from app.repositories.recipe_repository import RecipeRepository
from app.services.access import AccessController
from app.services.errors import NotFoundError, ValidationError


@dataclass(frozen=True, slots=True)
class IngredientInput:
    item_id: int
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class SkillRequirementInput:
    skill_id: int
    required_level: Decimal


@dataclass(frozen=True, slots=True)
class SkillRewardInput:
    skill_id: int
    experience_amount: Decimal


@dataclass(frozen=True, slots=True)
class EquipmentRequirementInput:
    equipment_id: int
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class RecipeInput:
    craft_station_id: int
    output_quantity: Decimal
    energy_cost: Decimal = Decimal("0")
    notes: str | None = None
    is_active: bool = True
    ingredients: tuple[IngredientInput, ...] = field(default_factory=tuple)
    skill_requirements: tuple[SkillRequirementInput, ...] = field(default_factory=tuple)
    skill_rewards: tuple[SkillRewardInput, ...] = field(default_factory=tuple)
    equipment_requirements: tuple[EquipmentRequirementInput, ...] = field(default_factory=tuple)


class RecipeService:
    def __init__(self, session_factory: Callable[[], Session], access: AccessController) -> None:
        self.session_factory = session_factory
        self.access = access

    def get_recipe(self, recipe_id: int) -> Recipe:
        with self.session_factory() as session:
            recipe = RecipeRepository(session).get(recipe_id)
            if recipe is None:
                raise NotFoundError("Рецепт не найден.")
            self._load_row_references(recipe)
            return recipe

    def list_for_item(self, item_id: int) -> list[Recipe]:
        with self.session_factory() as session:
            recipes = RecipeRepository(session).list_for_item(item_id)
            for recipe in recipes:
                self._load_row_references(recipe)
            return recipes

    def create_recipe(self, result_item_id: int, data: RecipeInput) -> Recipe:
        self.access.require_admin()
        clean = self._validate(result_item_id, data)
        with self.session_factory.begin() as session:
            if session.get(Item, result_item_id) is None:
                raise ValidationError("Предмет-результат не существует.")
            ingredients, requirements, rewards, equipment = self._owned_rows(clean)
            recipe = Recipe(
                result_item_id=result_item_id,
                craft_station_id=clean.craft_station_id,
                output_quantity=clean.output_quantity,
                energy_cost=clean.energy_cost,
                notes=clean.notes,
                is_active=clean.is_active,
                ingredients=ingredients,
                skill_requirements=requirements,
                skill_rewards=rewards,
                equipment_requirements=equipment,
            )
            recipe_id = RecipeRepository(session).add(recipe).id
        return self.get_recipe(recipe_id)

    def update_recipe(self, recipe_id: int, data: RecipeInput) -> Recipe:
        self.access.require_admin()
        with self.session_factory() as session:
            existing = session.get(Recipe, recipe_id)
            if existing is None:
                raise NotFoundError("Рецепт не найден.")
            result_item_id = existing.result_item_id
        clean = self._validate(result_item_id, data)
        with self.session_factory.begin() as session:
            repository = RecipeRepository(session)
            recipe = repository.get(recipe_id)
            if recipe is None:
                raise NotFoundError("Рецепт не найден.")
            recipe.craft_station_id = clean.craft_station_id
            recipe.output_quantity = clean.output_quantity
            recipe.energy_cost = clean.energy_cost
            recipe.notes = clean.notes
            recipe.is_active = clean.is_active
            ingredients, requirements, rewards, equipment = self._owned_rows(clean)
            repository.replace_owned_rows(
                recipe,
                ingredients=ingredients,
                requirements=requirements,
                rewards=rewards,
                equipment=equipment,
            )
        return self.get_recipe(recipe_id)

    def delete_recipe(self, recipe_id: int) -> None:
        self.access.require_admin()
        with self.session_factory.begin() as session:
            recipe = RecipeRepository(session).get(recipe_id)
            if recipe is None:
                raise NotFoundError("Рецепт не найден.")
            session.delete(recipe)

    def validate_draft(
        self,
        data: RecipeInput,
        *,
        result_item_id: int | None = None,
        session: Session | None = None,
    ) -> RecipeInput:
        return self._validate(result_item_id, data, session=session)

    def _validate(
        self,
        result_item_id: int | None,
        data: RecipeInput,
        *,
        session: Session | None = None,
    ) -> RecipeInput:
        output = self._decimal(data.output_quantity, "Количество результата")
        energy = self._decimal(data.energy_cost, "Затраты энергии")
        if output <= 0:
            raise ValidationError("Количество результата должно быть больше нуля.")
        if energy < 0:
            raise ValidationError("Затраты энергии не могут быть отрицательными.")

        ingredient_ids = self._unique_ids(
            (line.item_id for line in data.ingredients),
            "Один ингредиент нельзя добавить несколько раз.",
        )
        requirement_ids = self._unique_ids(
            (line.skill_id for line in data.skill_requirements),
            "Один навык нельзя несколько раз добавить в требования.",
        )
        reward_ids = self._unique_ids(
            (line.skill_id for line in data.skill_rewards),
            "Один навык нельзя несколько раз добавить в награды.",
        )
        equipment_ids = self._unique_ids(
            (line.equipment_id for line in data.equipment_requirements),
            "Один тип оборудования нельзя добавить несколько раз.",
        )

        for line in data.ingredients:
            if self._decimal(line.quantity, "Количество ингредиента") <= 0:
                raise ValidationError("Количество ингредиента должно быть больше нуля.")
        for line in data.skill_requirements:
            if self._decimal(line.required_level, "Уровень навыка") < 0:
                raise ValidationError("Уровень навыка не может быть отрицательным.")
        for line in data.skill_rewards:
            if self._decimal(line.experience_amount, "Опыт навыка") < 0:
                raise ValidationError("Опыт навыка не может быть отрицательным.")
        for line in data.equipment_requirements:
            if self._decimal(line.quantity, "Количество оборудования") <= 0:
                raise ValidationError("Количество оборудования должно быть больше нуля.")

        if session is None:
            with self.session_factory() as validation_session:
                self._validate_references(
                    validation_session,
                    result_item_id,
                    data.craft_station_id,
                    ingredient_ids,
                    requirement_ids | reward_ids,
                    equipment_ids,
                )
        else:
            self._validate_references(
                session,
                result_item_id,
                data.craft_station_id,
                ingredient_ids,
                requirement_ids | reward_ids,
                equipment_ids,
            )

        return RecipeInput(
            craft_station_id=data.craft_station_id,
            output_quantity=output,
            energy_cost=energy,
            notes=self._optional(data.notes),
            is_active=data.is_active,
            ingredients=tuple(
                IngredientInput(line.item_id, self._decimal(line.quantity, "Количество ингредиента"))
                for line in data.ingredients
            ),
            skill_requirements=tuple(
                SkillRequirementInput(
                    line.skill_id,
                    self._decimal(line.required_level, "Уровень навыка"),
                )
                for line in data.skill_requirements
            ),
            skill_rewards=tuple(
                SkillRewardInput(
                    line.skill_id,
                    self._decimal(line.experience_amount, "Опыт навыка"),
                )
                for line in data.skill_rewards
            ),
            equipment_requirements=tuple(
                EquipmentRequirementInput(
                    line.equipment_id,
                    self._decimal(line.quantity, "Количество оборудования"),
                )
                for line in data.equipment_requirements
            ),
        )

    @classmethod
    def _validate_references(
        cls,
        session: Session,
        result_item_id: int | None,
        station_id: int,
        ingredient_ids: set[int],
        skill_ids: set[int],
        equipment_ids: set[int],
    ) -> None:
        if result_item_id is not None and session.get(Item, result_item_id) is None:
            raise ValidationError("Предмет-результат не существует.")
        if session.get(CraftStation, station_id) is None:
            raise ValidationError("Выбранный стол не существует.")
        cls._ensure_ids(session, Item, ingredient_ids, "Один из ингредиентов не существует.")
        cls._ensure_ids(session, Skill, skill_ids, "Один из навыков не существует.")
        cls._ensure_ids(
            session,
            Equipment,
            equipment_ids,
            "Один из типов оборудования не существует.",
        )

    @staticmethod
    def _owned_rows(data: RecipeInput):
        return (
            [
                RecipeIngredient(item_id=line.item_id, quantity=line.quantity)
                for line in data.ingredients
            ],
            [
                RecipeSkillRequirement(skill_id=line.skill_id, required_level=line.required_level)
                for line in data.skill_requirements
            ],
            [
                RecipeSkillReward(skill_id=line.skill_id, experience_amount=line.experience_amount)
                for line in data.skill_rewards
            ],
            [
                RecipeEquipmentRequirement(
                    equipment_id=line.equipment_id,
                    quantity=line.quantity,
                )
                for line in data.equipment_requirements
            ],
        )

    @staticmethod
    def _load_row_references(recipe: Recipe) -> None:
        _ = recipe.result_item.name
        _ = recipe.craft_station.name
        for line in recipe.ingredients:
            _ = line.item.name
        for line in recipe.skill_requirements:
            _ = line.skill.name
        for line in recipe.skill_rewards:
            _ = line.skill.name
        for line in recipe.equipment_requirements:
            _ = line.equipment.name

    @staticmethod
    def _unique_ids(values, message: str) -> set[int]:
        materialized = list(values)
        if len(materialized) != len(set(materialized)):
            raise ValidationError(message)
        return set(materialized)

    @staticmethod
    def _ensure_ids(session: Session, model: type, expected: set[int], message: str) -> None:
        if not expected:
            return
        actual = set(session.scalars(select(model.id).where(model.id.in_(expected))))
        if actual != expected:
            raise ValidationError(message)

    @staticmethod
    def _decimal(value: Decimal, label: str) -> Decimal:
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError(f"{label}: введите корректное число.") from exc

    @staticmethod
    def _optional(value: str | None) -> str | None:
        clean = value.strip() if value else ""
        return clean or None
