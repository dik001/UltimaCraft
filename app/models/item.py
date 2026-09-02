from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, utc_now
from app.utils.text import normalized_key

if TYPE_CHECKING:
    from app.models.recipe import Recipe, RecipeIngredient
    from app.models.reference import AcquisitionMethod, ItemGroup, ItemSubgroup


class Item(TimestampMixin, Base):
    __tablename__ = "item"
    __table_args__ = (
        Index("ix_item_name_nocase", "name"),
        Index("ix_item_name_key", "name_key"),
        Index("ix_item_group_id", "group_id"),
        Index("ix_item_subgroup_id", "subgroup_id"),
        Index("ix_item_rank", "rank"),
        Index("ix_item_item_class", "item_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(240, collation="NOCASE"), nullable=False)
    name_key: Mapped[str] = mapped_column(String(300), nullable=False)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("item_group.id", ondelete="RESTRICT"), nullable=False
    )
    subgroup_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_subgroup.id", ondelete="RESTRICT")
    )
    rank: Mapped[str | None] = mapped_column(String(100))
    item_class: Mapped[str | None] = mapped_column(String(160))
    image_path: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_consumable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    group: Mapped["ItemGroup"] = relationship(back_populates="items")
    subgroup: Mapped["ItemSubgroup | None"] = relationship(back_populates="items")
    use_effects: Mapped[list["ItemUseEffect"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    recipes: Mapped[list["Recipe"]] = relationship(back_populates="result_item")
    ingredient_uses: Mapped[list["RecipeIngredient"]] = relationship(back_populates="item")
    acquisitions: Mapped[list["ItemAcquisition"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    prices: Mapped[list["ItemPrice"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class ItemUseEffect(Base):
    __tablename__ = "item_use_effect"
    __table_args__ = (
        CheckConstraint("max_uses > 0", name="max_uses_positive"),
        Index("ix_item_use_effect_item_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), nullable=False
    )
    effect_type: Mapped[str] = mapped_column(String(100, collation="NOCASE"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)

    item: Mapped[Item] = relationship(back_populates="use_effects")


class ItemAcquisition(Base):
    __tablename__ = "item_acquisition"
    __table_args__ = (
        UniqueConstraint("item_id", "method_id", name="uq_item_acquisition_item_method"),
        Index("ix_item_acquisition_item_id", "item_id"),
        Index("ix_item_acquisition_method_id", "method_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), nullable=False
    )
    method_id: Mapped[int] = mapped_column(
        ForeignKey("acquisition_method.id", ondelete="RESTRICT"), nullable=False
    )
    details: Mapped[str | None] = mapped_column(String(300))

    item: Mapped[Item] = relationship(back_populates="acquisitions")
    method: Mapped["AcquisitionMethod"] = relationship(back_populates="item_links")


class ItemPrice(Base):
    __tablename__ = "item_price"
    __table_args__ = (
        UniqueConstraint("item_id", "price_type", name="uq_item_price_item_type"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
        Index("ix_item_price_item_id", "item_id"),
        Index("ix_item_price_price_type", "price_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item.id", ondelete="CASCADE"), nullable=False
    )
    price_type: Mapped[str] = mapped_column(String(32, collation="NOCASE"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)

    item: Mapped[Item] = relationship(back_populates="prices")


def _populate_item_name_key(_mapper: object, _connection: object, target: Item) -> None:
    target.name_key = normalized_key(target.name)


event.listen(Item, "before_insert", _populate_item_name_key)
event.listen(Item, "before_update", _populate_item_name_key)
