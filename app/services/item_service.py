from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AcquisitionMethod,
    Item,
    ItemAcquisition,
    ItemGroup,
    ItemPrice,
    ItemSubgroup,
    ItemUseEffect,
)
from app.repositories.item_repository import ItemRepository
from app.services.access import AccessController
from app.services.errors import DependencyError, NotFoundError, ValidationError
from app.services.image_service import ImageService
from app.utils.text import normalized_key


@dataclass(frozen=True, slots=True)
class UseEffectInput:
    effect_type: str
    value: Decimal
    max_uses: int


@dataclass(frozen=True, slots=True)
class ItemInput:
    name: str
    group_id: int
    subgroup_id: int | None = None
    rank: str | None = None
    item_class: str | None = None
    notes: str | None = None
    is_active: bool = True
    is_consumable: bool = False
    effects: tuple[UseEffectInput, ...] = field(default_factory=tuple)
    acquisition_codes: frozenset[str] = field(default_factory=frozenset)
    prices: dict[str, Decimal] = field(default_factory=dict)


class ItemService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        access: AccessController,
        images: ImageService,
    ) -> None:
        self.session_factory = session_factory
        self.access = access
        self.images = images

    def get_item(self, item_id: int) -> Item:
        with self.session_factory() as session:
            item = ItemRepository(session).get(item_id)
            if item is None:
                raise NotFoundError("Предмет не найден.")
            return item

    def create_item(self, data: ItemInput, image_source: Path | None = None) -> Item:
        self.access.require_admin()
        clean = self._validate(data)
        new_image = self.images.import_item_image(image_source) if image_source else None
        try:
            with self.session_factory.begin() as session:
                effects, acquisitions, prices = self._owned_rows(session, clean)
                item = Item(
                    name=clean.name,
                    group_id=clean.group_id,
                    subgroup_id=clean.subgroup_id,
                    rank=clean.rank,
                    item_class=clean.item_class,
                    notes=clean.notes,
                    is_active=clean.is_active,
                    is_consumable=clean.is_consumable,
                    image_path=new_image,
                    use_effects=effects,
                    acquisitions=acquisitions,
                    prices=prices,
                )
                item_id = ItemRepository(session).add(item).id
            return self.get_item(item_id)
        except Exception:
            self.images.delete(new_image)
            raise

    def update_item(
        self,
        item_id: int,
        data: ItemInput,
        *,
        image_source: Path | None = None,
        remove_image: bool = False,
    ) -> Item:
        self.access.require_admin()
        if image_source is not None and remove_image:
            raise ValidationError("Нельзя одновременно заменить и удалить изображение.")
        clean = self._validate(data)
        new_image = self.images.import_item_image(image_source) if image_source else None
        old_image: str | None = None
        remove_old_after_commit = False
        try:
            with self.session_factory.begin() as session:
                repository = ItemRepository(session)
                item = repository.get(item_id)
                if item is None:
                    raise NotFoundError("Предмет не найден.")
                old_image = item.image_path
                if new_image is not None:
                    item.image_path = new_image
                    remove_old_after_commit = True
                elif remove_image:
                    item.image_path = None
                    remove_old_after_commit = True
                item.name = clean.name
                item.group_id = clean.group_id
                item.subgroup_id = clean.subgroup_id
                item.rank = clean.rank
                item.item_class = clean.item_class
                item.notes = clean.notes
                item.is_active = clean.is_active
                item.is_consumable = clean.is_consumable
                effects, acquisitions, prices = self._owned_rows(session, clean)
                repository.replace_owned_rows(item, effects, acquisitions, prices)
            if remove_old_after_commit and old_image:
                self._delete_image_if_unused(old_image)
            return self.get_item(item_id)
        except Exception:
            self.images.delete(new_image)
            raise

    def duplicate_item(self, item_id: int) -> Item:
        self.access.require_admin()
        original = self.get_item(item_id)
        duplicate_image = self.images.duplicate_item_image(original.image_path) if original.image_path else None
        data = ItemInput(
            name=f"Копия — {original.name}",
            group_id=original.group_id,
            subgroup_id=original.subgroup_id,
            rank=original.rank,
            item_class=original.item_class,
            notes=original.notes,
            is_active=original.is_active,
            is_consumable=original.is_consumable,
            effects=tuple(
                UseEffectInput(effect.effect_type, effect.value, effect.max_uses)
                for effect in original.use_effects
            ),
            acquisition_codes=frozenset(link.method.code for link in original.acquisitions),
            prices={},
        )
        try:
            with self.session_factory.begin() as session:
                effects, acquisitions, prices = self._owned_rows(session, data)
                duplicate = Item(
                    name=data.name,
                    group_id=data.group_id,
                    subgroup_id=data.subgroup_id,
                    rank=data.rank,
                    item_class=data.item_class,
                    notes=data.notes,
                    is_active=data.is_active,
                    is_consumable=data.is_consumable,
                    image_path=duplicate_image,
                    use_effects=effects,
                    acquisitions=acquisitions,
                    prices=prices,
                )
                duplicate_id = ItemRepository(session).add(duplicate).id
            return self.get_item(duplicate_id)
        except Exception:
            self.images.delete(duplicate_image)
            raise

    def delete_item(self, item_id: int) -> None:
        self.access.require_admin()
        old_image: str | None = None
        with self.session_factory.begin() as session:
            repository = ItemRepository(session)
            item = repository.get(item_id)
            if item is None:
                raise NotFoundError("Предмет не найден.")
            uses = repository.ingredient_use_count(item_id)
            recipes = repository.recipe_count(item_id)
            if uses:
                raise DependencyError(
                    f'Невозможно удалить предмет «{item.name}»: он используется в {uses} рецептах.'
                )
            if recipes:
                raise DependencyError(
                    f'Невозможно удалить предмет «{item.name}»: для него создано рецептов: {recipes}.'
                )
            old_image = item.image_path
            session.delete(item)
        if old_image:
            self._delete_image_if_unused(old_image)

    def _owned_rows(
        self,
        session: Session,
        data: ItemInput,
    ) -> tuple[list[ItemUseEffect], list[ItemAcquisition], list[ItemPrice]]:
        methods = {
            method.code: method
            for method in session.scalars(
                select(AcquisitionMethod).where(AcquisitionMethod.code.in_(data.acquisition_codes))
            )
        }
        if set(methods) != set(data.acquisition_codes):
            raise ValidationError("Один из способов получения не существует.")
        effects = [
            ItemUseEffect(
                effect_type=effect.effect_type.strip(),
                value=effect.value,
                max_uses=effect.max_uses,
            )
            for effect in data.effects
        ]
        acquisitions = [ItemAcquisition(method_id=methods[code].id) for code in sorted(methods)]
        prices = [
            ItemPrice(price_type=price_type, price=value)
            for price_type, value in sorted(data.prices.items())
        ]
        return effects, acquisitions, prices

    def _validate(self, data: ItemInput) -> ItemInput:
        name = data.name.strip()
        if not name:
            raise ValidationError("Название предмета обязательно.")
        with self.session_factory() as session:
            group = session.get(ItemGroup, data.group_id)
            if group is None:
                raise ValidationError("Выбранная группа не существует.")
            if data.subgroup_id is not None:
                subgroup = session.get(ItemSubgroup, data.subgroup_id)
                if subgroup is None or subgroup.group_id != data.group_id:
                    raise ValidationError("Подгруппа не принадлежит выбранной группе.")

        effects = tuple(data.effects)
        if data.is_consumable and not effects:
            raise ValidationError("Для используемого предмета укажите эффект.")
        if not data.is_consumable and effects:
            raise ValidationError("Эффекты можно задать только используемому предмету.")
        effect_keys: set[str] = set()
        for effect in effects:
            key = normalized_key(effect.effect_type)
            if not key:
                raise ValidationError("Тип эффекта обязателен.")
            if key in effect_keys:
                raise ValidationError("Один тип эффекта указан несколько раз.")
            effect_keys.add(key)
            if effect.max_uses <= 0:
                raise ValidationError("Количество использований должно быть больше нуля.")
            self._decimal(effect.value, "Значение эффекта")

        codes = frozenset(code.strip().upper() for code in data.acquisition_codes if code.strip())
        clean_prices: dict[str, Decimal] = {}
        for price_type, value in data.prices.items():
            code = price_type.strip().upper()
            if not code:
                raise ValidationError("Тип цены обязателен.")
            decimal_value = self._decimal(value, "Цена")
            if decimal_value < 0:
                raise ValidationError("Цена не может быть отрицательной.")
            clean_prices[code] = decimal_value
        for standard in ("TRADER", "AUCTION"):
            if standard in clean_prices and standard not in codes:
                raise ValidationError("Цена задана для отключённого способа получения.")

        return ItemInput(
            name=name,
            group_id=data.group_id,
            subgroup_id=data.subgroup_id,
            rank=self._optional(data.rank),
            item_class=self._optional(data.item_class),
            notes=self._optional(data.notes),
            is_active=data.is_active,
            is_consumable=data.is_consumable,
            effects=effects,
            acquisition_codes=codes,
            prices=clean_prices,
        )

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

    def _delete_image_if_unused(self, image_path: str) -> None:
        with self.session_factory() as session:
            if ItemRepository(session).image_reference_count(image_path) == 0:
                self.images.delete(image_path)
