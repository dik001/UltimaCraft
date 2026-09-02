from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Recipe


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, recipe_id: int) -> Recipe | None:
        return self.session.scalar(
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.result_item),
                selectinload(Recipe.craft_station),
                selectinload(Recipe.ingredients),
                selectinload(Recipe.skill_requirements),
                selectinload(Recipe.skill_rewards),
                selectinload(Recipe.equipment_requirements),
            )
        )

    def list_for_item(self, item_id: int) -> list[Recipe]:
        return list(
            self.session.scalars(
                select(Recipe)
                .where(Recipe.result_item_id == item_id)
                .order_by(Recipe.id)
                .options(
                    selectinload(Recipe.craft_station),
                    selectinload(Recipe.ingredients),
                    selectinload(Recipe.skill_requirements),
                    selectinload(Recipe.skill_rewards),
                    selectinload(Recipe.equipment_requirements),
                )
            )
        )

    def add(self, recipe: Recipe) -> Recipe:
        self.session.add(recipe)
        self.session.flush()
        return recipe

    def replace_owned_rows(
        self,
        recipe: Recipe,
        *,
        ingredients: list,
        requirements: list,
        rewards: list,
        equipment: list,
    ) -> None:
        recipe.ingredients.clear()
        recipe.skill_requirements.clear()
        recipe.skill_rewards.clear()
        recipe.equipment_requirements.clear()
        self.session.flush()
        recipe.ingredients.extend(ingredients)
        recipe.skill_requirements.extend(requirements)
        recipe.skill_rewards.extend(rewards)
        recipe.equipment_requirements.extend(equipment)
        self.session.flush()

