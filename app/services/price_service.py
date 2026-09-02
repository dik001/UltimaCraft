from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.models import AcquisitionMethod, Item, ItemAcquisition, ItemPrice
from app.services.errors import NotFoundError, ValidationError


class PriceService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def update_auction_price(self, item_id: int, value: Decimal) -> ItemPrice:
        try:
            price_value = Decimal(value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Введите корректную цену аукциона.") from exc
        if price_value < 0:
            raise ValidationError("Цена аукциона не может быть отрицательной.")
        with self.session_factory.begin() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Предмет не найден.")
            auction_enabled = session.scalar(
                select(ItemAcquisition.id)
                .join(AcquisitionMethod, ItemAcquisition.method_id == AcquisitionMethod.id)
                .where(
                    ItemAcquisition.item_id == item_id,
                    AcquisitionMethod.code == "AUCTION",
                )
            )
            if auction_enabled is None:
                raise ValidationError("Для предмета не включён способ получения «Аукцион».")
            price = session.scalar(
                select(ItemPrice).where(
                    ItemPrice.item_id == item_id,
                    ItemPrice.price_type == "AUCTION",
                )
            )
            if price is None:
                price = ItemPrice(
                    item_id=item_id,
                    price_type="AUCTION",
                    price=price_value,
                    updated_at=utc_now(),
                )
                session.add(price)
            else:
                price.price = price_value
                price.updated_at = utc_now()
            session.flush()
            return price

