from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, ItemGroup, ItemSubgroup, Recipe
from app.repositories.item_repository import ItemRepository
from app.repositories.recipe_repository import RecipeRepository
from app.services.errors import NotFoundError, ValidationError
from app.services.item_service import ItemInput, ItemService
from app.services.recipe_service import IngredientInput, RecipeInput, RecipeService


@dataclass(frozen=True, slots=True)
class RecipeDraft:
    recipe_id: int | None
    data: RecipeInput


@dataclass(frozen=True, slots=True)
class PendingItemDraft:
    """A minimal Item created atomically for a newly typed ingredient."""

    temporary_id: int
    data: ItemInput


@dataclass(frozen=True, slots=True)
class PendingGroupDraft:
    """An ItemGroup created atomically with quick ingredient Items."""

    temporary_id: int
    name: str


@dataclass(frozen=True, slots=True)
class PendingSubgroupDraft:
    """An ItemSubgroup whose group may also be pending in the same save."""

    temporary_id: int
    group_id: int
    name: str


@dataclass(frozen=True, slots=True)
class AggregateResult:
    item: Item
    recipes: list[Recipe]


class BuilderService:
    """Atomically saves the item form and every recipe shown in it."""

    def __init__(self, items: ItemService, recipes: RecipeService) -> None:
        self.items = items
        self.recipes = recipes
        self.session_factory = items.session_factory
        self.access = items.access
        self.images = items.images

    def save(
        self,
        item_id: int | None,
        item_data: ItemInput,
        recipe_drafts: tuple[RecipeDraft, ...],
        *,
        image_source: Path | None = None,
        remove_image: bool = False,
        pending_groups: tuple[PendingGroupDraft, ...] = (),
        pending_subgroups: tuple[PendingSubgroupDraft, ...] = (),
        pending_items: tuple[PendingItemDraft, ...] = (),
    ) -> AggregateResult:
        self.access.require_admin()
        if image_source is not None and remove_image:
            raise ValidationError("Нельзя одновременно заменить и удалить изображение.")
        clean_item = self.items._validate(item_data)
        clean_pending = tuple(
            PendingItemDraft(
                pending.temporary_id,
                replace(pending.data, name=self._required_name(pending.data.name, "ресурса")),
            )
            for pending in pending_items
        )
        clean_groups = tuple(
            PendingGroupDraft(
                pending.temporary_id,
                self._required_name(pending.name, "группы"),
            )
            for pending in pending_groups
        )
        clean_subgroups = tuple(
            PendingSubgroupDraft(
                pending.temporary_id,
                pending.group_id,
                self._required_name(pending.name, "подгруппы"),
            )
            for pending in pending_subgroups
        )
        self._validate_temporary_ids(clean_groups, "группа")
        self._validate_temporary_ids(clean_subgroups, "подгруппа")
        self._validate_temporary_ids(clean_pending, "ресурс")
        existing_ids = [draft.recipe_id for draft in recipe_drafts if draft.recipe_id is not None]
        if len(existing_ids) != len(set(existing_ids)):
            raise ValidationError("Один рецепт присутствует в форме несколько раз.")

        new_image = self.images.import_item_image(image_source) if image_source else None
        old_image: str | None = None
        delete_old = False
        try:
            with self.session_factory.begin() as session:
                item_repository = ItemRepository(session)
                recipe_repository = RecipeRepository(session)
                if item_id is None:
                    item = Item(name=clean_item.name, group_id=clean_item.group_id)
                    item_repository.add(item)
                    item_id = item.id
                else:
                    item = item_repository.get(item_id)
                    if item is None:
                        raise NotFoundError("Предмет не найден.")
                old_image = item.image_path
                if new_image is not None:
                    item.image_path = new_image
                    delete_old = True
                elif remove_image:
                    item.image_path = None
                    delete_old = True
                item.name = clean_item.name
                item.group_id = clean_item.group_id
                item.subgroup_id = clean_item.subgroup_id
                item.rank = clean_item.rank
                item.item_class = clean_item.item_class
                item.notes = clean_item.notes
                item.is_active = clean_item.is_active
                item.is_consumable = clean_item.is_consumable
                effects, acquisitions, prices = self.items._owned_rows(session, clean_item)
                item_repository.replace_owned_rows(item, effects, acquisitions, prices)

                resolved_group_ids: dict[int, int] = {}
                for pending in clean_groups:
                    group = ItemGroup(name=pending.name, sort_order=0)
                    session.add(group)
                    session.flush()
                    resolved_group_ids[pending.temporary_id] = group.id

                resolved_subgroup_ids: dict[int, int] = {}
                for pending in clean_subgroups:
                    group_id = self._resolve_reference_id(
                        session,
                        ItemGroup,
                        pending.group_id,
                        resolved_group_ids,
                        "группы новой подгруппы",
                    )
                    subgroup = ItemSubgroup(
                        name=pending.name,
                        group_id=group_id,
                        sort_order=0,
                    )
                    session.add(subgroup)
                    session.flush()
                    resolved_subgroup_ids[pending.temporary_id] = subgroup.id

                resolved_pending_ids: dict[int, int] = {}
                for pending in clean_pending:
                    group_id = self._resolve_reference_id(
                        session,
                        ItemGroup,
                        pending.data.group_id,
                        resolved_group_ids,
                        "группы нового ресурса",
                    )
                    subgroup_id: int | None = None
                    if pending.data.subgroup_id is not None:
                        subgroup_id = self._resolve_reference_id(
                            session,
                            ItemSubgroup,
                            pending.data.subgroup_id,
                            resolved_subgroup_ids,
                            "подгруппы нового ресурса",
                        )
                        subgroup = session.get(ItemSubgroup, subgroup_id)
                        if subgroup is None or subgroup.group_id != group_id:
                            raise ValidationError(
                                "Подгруппа нового ресурса не принадлежит выбранной группе."
                            )
                    pending_item = Item(
                        name=pending.data.name,
                        group_id=group_id,
                        subgroup_id=subgroup_id,
                        rank=pending.data.rank,
                        item_class=pending.data.item_class,
                        notes=pending.data.notes,
                        is_active=pending.data.is_active,
                        is_consumable=False,
                    )
                    session.add(pending_item)
                    session.flush()
                    resolved_pending_ids[pending.temporary_id] = pending_item.id

                resolved_drafts = tuple(
                    RecipeDraft(
                        draft.recipe_id,
                        self.recipes.validate_draft(
                            self._resolve_pending_ingredients(draft.data, resolved_pending_ids),
                            result_item_id=item_id,
                            session=session,
                        ),
                    )
                    for draft in recipe_drafts
                )

                existing = {
                    recipe.id: recipe
                    for recipe in session.scalars(
                        select(Recipe).where(Recipe.result_item_id == item_id)
                    )
                }
                unknown = set(existing_ids) - set(existing)
                if unknown:
                    raise ValidationError("Один из изменяемых рецептов не принадлежит предмету.")
                retained: set[int] = set()
                for draft in resolved_drafts:
                    data = draft.data
                    if draft.recipe_id is None:
                        recipe = Recipe(result_item_id=item_id)
                        session.add(recipe)
                    else:
                        recipe = existing[draft.recipe_id]
                        retained.add(draft.recipe_id)
                    recipe.craft_station_id = data.craft_station_id
                    recipe.output_quantity = data.output_quantity
                    recipe.energy_cost = data.energy_cost
                    recipe.notes = data.notes
                    recipe.is_active = data.is_active
                    ingredients, requirements, rewards, equipment = self.recipes._owned_rows(data)
                    if draft.recipe_id is None:
                        recipe.ingredients = ingredients
                        recipe.skill_requirements = requirements
                        recipe.skill_rewards = rewards
                        recipe.equipment_requirements = equipment
                    else:
                        recipe_repository.replace_owned_rows(
                            recipe,
                            ingredients=ingredients,
                            requirements=requirements,
                            rewards=rewards,
                            equipment=equipment,
                        )
                for recipe_id, recipe in existing.items():
                    if recipe_id not in retained:
                        session.delete(recipe)
            if delete_old and old_image:
                self.items._delete_image_if_unused(old_image)
            return AggregateResult(
                item=self.items.get_item(item_id),
                recipes=self.recipes.list_for_item(item_id),
            )
        except Exception:
            self.images.delete(new_image)
            raise

    @staticmethod
    def _validate_temporary_ids(rows: tuple[object, ...], label: str) -> None:
        temporary_ids = [int(getattr(row, "temporary_id")) for row in rows]
        if any(temporary_id >= 0 for temporary_id in temporary_ids):
            raise ValidationError(f"Временные ID ({label}) должны быть отрицательными.")
        if len(temporary_ids) != len(set(temporary_ids)):
            raise ValidationError(f"Одна временная сущность ({label}) передана несколько раз.")

    @staticmethod
    def _resolve_reference_id(
        session: Session,
        model: type,
        reference_id: int,
        resolved_ids: dict[int, int],
        label: str,
    ) -> int:
        resolved_id = resolved_ids.get(reference_id) if reference_id < 0 else reference_id
        if resolved_id is None or resolved_id <= 0 or session.get(model, resolved_id) is None:
            raise ValidationError(f"Не найдено описание {label}.")
        return resolved_id

    @staticmethod
    def _required_name(value: str, label: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValidationError(f"Название {label} обязательно.")
        return clean

    @staticmethod
    def _resolve_pending_ingredients(
        data: RecipeInput,
        resolved_ids: dict[int, int],
    ) -> RecipeInput:
        ingredients: list[IngredientInput] = []
        for line in data.ingredients:
            item_id = line.item_id
            if item_id < 0:
                item_id = resolved_ids.get(item_id, 0)
                if item_id <= 0:
                    raise ValidationError("Не найдено описание нового ресурса рецепта.")
            ingredients.append(IngredientInput(item_id, line.quantity))
        return replace(data, ingredients=tuple(ingredients))
