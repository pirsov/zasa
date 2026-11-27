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
