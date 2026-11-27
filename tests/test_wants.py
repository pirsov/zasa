"""Заказ спрашивает город, адрес и телефон и не открывает сайт раньше."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.wants import Wants


def _wants(tmp_path: Path) -> Wants:
    runner = AsyncMock()
    runner.execute = AsyncMock(return_value=(0, "", ""))
    pages = AsyncMock()
    pages.open_and_clear = AsyncMock(return_value="Убрал: «Крутите колесо».")
    pages.reach_order = AsyncMock(
        return_value="В корзине Пепперони. Кнопку «Оформить заказ» не нажимал."
    )
    return Wants(runner, root=tmp_path / "home", pages=pages)


@pytest.mark.asyncio
async def test_pizza_asks_for_the_city_before_any_site(tmp_path: Path) -> None:
    wants = _wants(tmp_path)
    answer = await wants.fulfill("я хочу пиццу")
    assert answer == "Заказываю пиццу. В каком городе доставить? Сам я город не знаю."
    wants.pages.open_and_clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_order_collects_address_and_phone_then_opens(tmp_path: Path) -> None:
    wants = _wants(tmp_path)
    await wants.fulfill("я хочу пиццу")
    assert await wants.fulfill("Москва") == (
        "Заказываю пиццу. Город: Москва. Какой адрес доставки? Сам я адрес не знаю."
    )
    assert await wants.fulfill("улица Ленина, 1") == (
        "Заказываю пиццу. Город: Москва. Адрес: улица Ленина, 1. "
        "Какой номер телефона указать? Сам я телефон не знаю."
    )
    done = await wants.fulfill("+7 999 123-45-67")
    assert done is not None
    assert "Город: Москва" in done
    assert "Адрес: улица Ленина, 1" in done
    assert "Телефон: +7 999 123-45-67" in done
    assert "https://papajohns.ru/moscow" in done
    wants.pages.reach_order.assert_awaited_once()
    assert wants.pages.reach_order.await_args.args[:3] == (
        "https://papajohns.ru/moscow",
        "Пепперони",
        "улица Ленина, 1",
    )
    assert "не нажимал" in done
    assert not (tmp_path / "home" / "order.json").exists()


@pytest.mark.asyncio
async def test_other_city_does_not_use_moscow(tmp_path: Path) -> None:
    wants = _wants(tmp_path)
    await wants.fulfill("хочу суши")
    await wants.fulfill("Казань")
    await wants.fulfill("улица Баумана, 10")
    done = await wants.fulfill("89991234567")
    assert done is not None
    assert "Казань" in done
    assert "papajohns.ru/moscow" not in done
    opened = wants.pages.open_and_clear.await_args.args[0]
    assert "yandex.ru/search" in opened
    assert "papajohns" not in opened


@pytest.mark.asyncio
async def test_bad_phone_is_asked_again(tmp_path: Path) -> None:
    wants = _wants(tmp_path)
    await wants.fulfill("я хочу пиццу")
    await wants.fulfill("Москва")
    await wants.fulfill("улица Ленина, 1")
    again = await wants.fulfill("не скажу")
    assert again is not None
    assert "телефон" in again
    wants.pages.open_and_clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_known_details_are_reused(tmp_path: Path) -> None:
    wants = _wants(tmp_path)
    await wants.fulfill("я хочу пиццу")
    await wants.fulfill("Москва")
    await wants.fulfill("улица Ленина, 1")
    await wants.fulfill("+7 999 123-45-67")
    wants.pages.reach_order.reset_mock()
    again = await wants.fulfill("я хочу пиццу")
    assert again is not None
    assert "Город: Москва" in again
    assert "https://papajohns.ru/moscow" in again
    wants.pages.reach_order.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_and_stray_word_are_not_orders(tmp_path: Path) -> None:
    wants = _wants(tmp_path)
    assert await wants.fulfill("хочу список покупок: молоко") is None
    assert await wants.fulfill("Москва") is None


@pytest.mark.asyncio
async def test_orchestrator_asks_instead_of_planning(tmp_path: Path) -> None:
    from tests.test_orchestrator import _orchestrator

    orchestrator = _orchestrator(tmp_path)
    orchestrator.wants = _wants(tmp_path)
    await orchestrator.run("я хочу пиццу")
    orchestrator.planner.create_plan.assert_not_awaited()
    orchestrator.wants.pages.open_and_clear.assert_not_awaited()
