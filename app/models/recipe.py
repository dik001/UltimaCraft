from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.reference import CraftStation, Equipment, Skill


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipe"
    __table_args__ = (
        CheckConstraint("output_quantity > 0", name="output_quantity_positive"),
        CheckConstraint("energy_cost >= 0", name="energy_cost_nonnegative"),
        Index("ix_recipe_result_item_id", "result_item_id"),
        Index("ix_recipe_craft_station_id", "craft_station_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    result_item_id: Mapped[int] = mapped_column(
        ForeignKey("item.id", ondelete="RESTRICT"), nullable=False
    )
    craft_station_id: Mapped[int] = mapped_column(
        ForeignKey("craft_station.id", ondelete="RESTRICT"), nullable=False
    )
    output_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    energy_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    result_item: Mapped["Item"] = relationship(back_populates="recipes")
    craft_station: Mapped["CraftStation"] = relationship(back_populates="recipes")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    skill_requirements: Mapped[list["RecipeSkillRequirement"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    skill_rewards: Mapped[list["RecipeSkillReward"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    equipment_requirements: Mapped[list["RecipeEquipmentRequirement"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredient"
    __table_args__ = (
        UniqueConstraint("recipe_id", "item_id", name="uq_recipe_ingredient_recipe_item"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_recipe_ingredient_recipe_id", "recipe_id"),
        Index("ix_recipe_ingredient_item_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    item: Mapped["Item"] = relationship(back_populates="ingredient_uses")


class RecipeSkillRequirement(Base):
    __tablename__ = "recipe_skill_requirement"
    __table_args__ = (
        UniqueConstraint("recipe_id", "skill_id", name="uq_recipe_skill_requirement_recipe_skill"),
        CheckConstraint("required_level >= 0", name="required_level_nonnegative"),
        Index("ix_recipe_skill_requirement_recipe_id", "recipe_id"),
        Index("ix_recipe_skill_requirement_skill_id", "skill_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id", ondelete="RESTRICT"), nullable=False)
    required_level: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="skill_requirements")
    skill: Mapped["Skill"] = relationship(back_populates="requirements")


class RecipeSkillReward(Base):
    __tablename__ = "recipe_skill_reward"
    __table_args__ = (
        UniqueConstraint("recipe_id", "skill_id", name="uq_recipe_skill_reward_recipe_skill"),
        CheckConstraint("experience_amount >= 0", name="experience_amount_nonnegative"),
        Index("ix_recipe_skill_reward_recipe_id", "recipe_id"),
        Index("ix_recipe_skill_reward_skill_id", "skill_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id", ondelete="RESTRICT"), nullable=False)
    experience_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="skill_rewards")
    skill: Mapped["Skill"] = relationship(back_populates="rewards")


class RecipeEquipmentRequirement(Base):
    __tablename__ = "recipe_equipment_requirement"
    __table_args__ = (
        UniqueConstraint(
            "recipe_id", "equipment_id", name="uq_recipe_equipment_requirement_recipe_equipment"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_recipe_equipment_requirement_recipe_id", "recipe_id"),
        Index("ix_recipe_equipment_requirement_equipment_id", "equipment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="equipment_requirements")
    equipment: Mapped["Equipment"] = relationship(back_populates="requirements")

