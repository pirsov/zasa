"""Окна, которые закрывают страницу, снимаются крестиком или прячутся."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.browser import PageCleaner

_PAGE = """<!doctype html>
<html>
  <body>
    <h1 id="menu">Меню</h1>
    <div id="wheel" style="position:fixed;inset:0;background:#402;z-index:5">
      <p>Крутите колесо. Первый подарок</p>
      <button id="close" style="width:36px;height:36px"
        onclick="document.getElementById('wheel').remove()"></button>
      <button style="width:120px;height:52px">Войти</button>
    </div>
    <div id="city" style="position:fixed;inset:0;background:#222;z-index:4">
      <p>Вы точно тут?</p>
    </div>
  </body>
</html>
"""


@pytest.mark.asyncio
async def test_clears_a_popup_and_a_banner_without_a_cross(tmp_path: Path) -> None:
    page = tmp_path / "menu.html"
    page.write_text(_PAGE, encoding="utf-8")
    shot = tmp_path / "after.png"
    report = await PageCleaner().open_and_clear(page.as_uri(), screenshot=shot)
    assert "Крутите колесо" in report
    assert "Вы точно тут?" in report
    assert shot.is_file()
    assert shot.stat().st_size > 1000


_MENU = """<!doctype html>
<html><body>
  <div>
    <span>Пепперони</span>
    <button>В корзину</button>
  </div>
  <a href="order.html">Оформить</a>
</body></html>
"""

_ORDER = """<!doctype html>
<html><body>
  <div>Пепперони</div>
  <div>620 ₽</div>
  <input name="address_in_line" placeholder="Адрес">
  <ul id="hints" hidden></ul>
  <button id="pay" onclick="document.body.dataset.paid='1'">Оформить заказ</button>
  <script>
    const field = document.querySelector("input");
    const hints = document.getElementById("hints");
    field.addEventListener("input", () => {
      hints.hidden = false;
      hints.innerHTML = "<li>Москва, Тверская улица, 1</li>";
    });
    hints.addEventListener("click", (event) => {
      if (event.target.tagName === "LI") field.value = event.target.innerText;
    });
  </script>
</body></html>
"""


@pytest.mark.asyncio
async def test_reaches_checkout_without_paying(tmp_path: Path) -> None:
    (tmp_path / "menu.html").write_text(_MENU, encoding="utf-8")
    (tmp_path / "order.html").write_text(_ORDER, encoding="utf-8")
    report = await PageCleaner().reach_order(
        (tmp_path / "menu.html").as_uri(),
        "Пепперони",
        "Тверская улица 1",
    )
    assert "Пепперони" in report
    assert "Тверская" in report
    assert "не нажимал" in report
    paid = await PageCleaner().reach_order(
        (tmp_path / "menu.html").as_uri(),
        "Пепперони",
        "Тверская улица 1",
        confirm=True,
    )
    assert "нажал" in paid


_MINIMUM = """<!doctype html>
<html><body>
  <div>
    <span>Пепперони</span>
    <button>В корзину</button>
  </div>
  <a href="order.html">Оформить</a>
</body></html>
"""

_SHORT = """<!doctype html>
<html><body>
  <div>
    <span>Пепперони</span>
    <button id="minus"></button>
    <button id="plus" onclick="unlock()"></button>
  </div>
  <input name="address_in_line" placeholder="Адрес">
  <ul id="hints" hidden></ul>
  <button id="pay" disabled>Доставка от 770 ₽</button>
  <script>
    const field = document.querySelector("input");
    const hints = document.getElementById("hints");
    field.addEventListener("input", () => {
      hints.hidden = false;
      hints.innerHTML = "<li>Москва, Тверская улица, 1</li>";
    });
    hints.addEventListener("click", (event) => {
      if (event.target.tagName === "LI") field.value = event.target.innerText;
    });
    function unlock() {
      const pay = document.getElementById("pay");
      pay.disabled = false;
      pay.textContent = "Оформить заказ";
    }
    document.getElementById("pay").addEventListener("click", () => {
      document.body.dataset.paid = "1";
    });
  </script>
</body></html>
"""


@pytest.mark.asyncio
async def test_confirm_adds_until_the_minimum_and_then_presses(tmp_path: Path) -> None:
    (tmp_path / "menu.html").write_text(_MINIMUM, encoding="utf-8")
    (tmp_path / "order.html").write_text(_SHORT, encoding="utf-8")
    report = await PageCleaner().reach_order(
        (tmp_path / "menu.html").as_uri(),
        "Пепперони",
        "Тверская улица 1",
        confirm=True,
    )
    assert "Добавил ещё 1" in report
    assert "нажал" in report
