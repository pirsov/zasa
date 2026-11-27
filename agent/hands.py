"""Инструменты агента. Каждый вызов — одно действие, не сценарий."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.browser import _HAS_OVERLAY, _clear

_CHROME = "/usr/bin/google-chrome"


class HandsError(RuntimeError):
    """Инструмент вызван без нужных аргументов или страница не открыта."""


class Hands:
    """Руки агента: спросить, запомнить, открыть, нажать, ввести, прочитать."""

    def __init__(self, root: str | Path = "home", executable: str = _CHROME) -> None:
        self.root = Path(root)
        self.executable = executable
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> str:
        args = arguments or {}
        if tool == "ask":
            return _required(args, "text")
        if tool == "remember":
            return self._remember(_required(args, "text"))
        if tool == "open_page":
            return await self._open(_required(args, "url"))
        if tool == "click":
            return await self._click(_required(args, "text"))
        if tool == "type_text":
            return await self._type(_required(args, "field"), _required(args, "value"))
        if tool == "read_page":
            return await self._read()
        raise HandsError(f"Неизвестный инструмент: {tool}")

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._page = None
        self._playwright = None

    def _remember(self, text: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "notes.md"
        previous = path.read_text(encoding="utf-8") if path.is_file() else ""
        path.write_text(previous + text + "\n", encoding="utf-8")
        return f"Запомнил: {text}"

    async def _page_ready(self) -> Any:
        if self._page is not None:
            return self._page
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            executable_path=self.executable,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._page = await self._browser.new_page(viewport={"width": 1400, "height": 1100})
        return self._page

    async def _open(self, url: str) -> str:
        page = await self._page_ready()
        try:
            await page.goto(url, wait_until="commit", timeout=45000)
        except Exception:
            await page.goto(url, wait_until="commit", timeout=45000)
        try:
            await page.wait_for_function(_HAS_OVERLAY, timeout=2000)
        except Exception:
            pass
        removed = await _clear(page)
        text = await self._read()
        cleared = f" Убрал: «{'», «'.join(removed)}»." if removed else ""
        return f"Открыл {url}.{cleared} {text}"

    async def _click(self, text: str) -> str:
        page = await self._need_page()
        button = page.locator("button, a, [role='button']").filter(has_text=text)
        if await button.count():
            await button.first.click()
        else:
            await page.get_by_text(text).first.click()
        await page.wait_for_timeout(300)
        return f"Нажал «{text}»."

    async def _type(self, field: str, value: str) -> str:
        page = await self._need_page()
        target = page.locator(
            f"input[name='{field}'], input[placeholder='{field}'], textarea[name='{field}']"
        )
        if await target.count() == 0:
            target = page.get_by_label(field)
        await target.first.fill(value)
        return f"Ввёл в «{field}»."

    async def _read(self) -> str:
        page = await self._need_page()
        text = await page.evaluate(
            """() => {
                const bits = [document.body.innerText || ""];
                for (const el of document.querySelectorAll("input, textarea")) {
                    if (el.value) bits.push(el.value);
                }
                return bits.join(" ").replace(/\\s+/g, " ").trim();
            }"""
        )
        snippet = str(text)[:500]
        return f"На странице: {snippet}" if snippet else "Страница пустая."

    async def _need_page(self) -> Any:
        if self._page is None:
            raise HandsError("Страница ещё не открыта.")
        return self._page


def _required(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HandsError(f"Нужен аргумент {key}.")
    return value.strip()
