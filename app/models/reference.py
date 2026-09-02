from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.utils.text import normalized_key

if TYPE_CHECKING:
    from app.models.item import Item, ItemAcquisition
    from app.models.recipe import (
        Recipe,
        RecipeEquipmentRequirement,
        RecipeSkillRequirement,
        RecipeSkillReward,
    )


class CraftStation(Base):
    __tablename__ = "craft_station"
    __table_args__ = (
        UniqueConstraint("name", name="uq_craft_station_name"),
        Index("ux_craft_station_name_key", "name_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    recipes: Mapped[list["Recipe"]] = relationship(back_populates="craft_station")


class ItemGroup(Base):
    __tablename__ = "item_group"
    __table_args__ = (
        UniqueConstraint("name", name="uq_item_group_name"),
        Index("ux_item_group_name_key", "name_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    subgroups: Mapped[list["ItemSubgroup"]] = relationship(
        back_populates="group",
        order_by="ItemSubgroup.sort_order, ItemSubgroup.name",
    )
    items: Mapped[list["Item"]] = relationship(back_populates="group")


class ItemSubgroup(Base):
    __tablename__ = "item_subgroup"
    __table_args__ = (
        UniqueConstraint("group_id", "name", name="uq_item_subgroup_group_name"),
        Index("ix_item_subgroup_group_id", "group_id"),
        Index("ux_item_subgroup_group_name_key", "group_id", "name_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("item_group.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped[ItemGroup] = relationship(back_populates="subgroups")
    items: Mapped[list["Item"]] = relationship(back_populates="subgroup")


class Skill(Base):
    __tablename__ = "skill"
    __table_args__ = (
        UniqueConstraint("name", name="uq_skill_name"),
        Index("ux_skill_name_key", "name_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    requirements: Mapped[list["RecipeSkillRequirement"]] = relationship(back_populates="skill")
    rewards: Mapped[list["RecipeSkillReward"]] = relationship(back_populates="skill")


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("name", name="uq_equipment_name"),
        Index("ux_equipment_name_key", "name_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    requirements: Mapped[list["RecipeEquipmentRequirement"]] = relationship(
        back_populates="equipment"
    )


class AcquisitionMethod(Base):
    __tablename__ = "acquisition_method"
    __table_args__ = (
        UniqueConstraint("code", name="uq_acquisition_method_code"),
        UniqueConstraint("name", name="uq_acquisition_method_name"),
        Index("ux_acquisition_method_name_key", "name_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32, collation="NOCASE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    item_links: Mapped[list["ItemAcquisition"]] = relationship(back_populates="method")


def _populate_name_key(_mapper: object, _connection: object, target: object) -> None:
    target.name_key = normalized_key(target.name)  # type: ignore[attr-defined]


for _model in (CraftStation, ItemGroup, ItemSubgroup, Skill, Equipment, AcquisitionMethod):
    event.listen(_model, "before_insert", _populate_name_key)
    event.listen(_model, "before_update", _populate_name_key)
