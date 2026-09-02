from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.database.session import Database
from app.paths import AppPaths
from app.services.access import AccessController, AppMode
from app.services.errors import AccessDeniedError, ValidationError
from app.services.image_service import ImageService
from app.services.item_service import ItemInput, ItemService
from app.services.price_service import PriceService
from app.services.reference_service import GroupInput, ReferenceService
from app.services.settings_service import DEFAULT_ADMIN_PASSWORD, SettingsService


def test_password_hash_and_change(tmp_path: Path) -> None:
    settings = SettingsService(tmp_path / "data" / "settings.json")
    assert settings.was_created
    assert settings.verify_admin_password(DEFAULT_ADMIN_PASSWORD)
    assert not settings.verify_admin_password("wrong")
    raw = settings.path.read_text(encoding="utf-8")
    assert f': "{DEFAULT_ADMIN_PASSWORD}"' not in raw
    settings.change_admin_password(DEFAULT_ADMIN_PASSWORD, "новый-пароль")
    assert settings.verify_admin_password("новый-пароль")
    assert not settings.verify_admin_password(DEFAULT_ADMIN_PASSWORD)


def test_viewer_can_only_update_auction_price(database: Database, tmp_path: Path) -> None:
    access = AccessController(AppMode.ADMIN)
    references = ReferenceService(database.session_factory, access)
    items = ItemService(
        database.session_factory,
        access,
        ImageService(AppPaths.from_root(tmp_path / "workspace")),
    )
    group = references.create_group(GroupInput("Товары"))
    item = items.create_item(
        ItemInput(
            "Рыночный предмет",
            group.id,
            acquisition_codes=frozenset({"AUCTION", "TRADER"}),
            prices={"AUCTION": Decimal("18900"), "TRADER": Decimal("1000")},
        )
    )
    access.mode = AppMode.VIEWER
    with pytest.raises(AccessDeniedError):
        items.update_item(item.id, ItemInput("Взлом", group.id))

    prices = PriceService(database.session_factory)
    before = next(price.updated_at for price in item.prices if price.price_type == "AUCTION")
    prices.update_auction_price(item.id, Decimal("17500.5"))
    reloaded = items.get_item(item.id)
    values = {price.price_type: price for price in reloaded.prices}
    assert values["AUCTION"].price == Decimal("17500.5000")
    assert values["AUCTION"].updated_at >= before
    assert values["TRADER"].price == Decimal("1000.0000")

    no_auction = access
    access.mode = AppMode.ADMIN
    second = items.create_item(ItemInput("Без аукциона", group.id))
    access.mode = AppMode.VIEWER
    with pytest.raises(ValidationError, match="не включён"):
        prices.update_auction_price(second.id, Decimal("1"))
