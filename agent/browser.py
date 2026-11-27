"""Открывает страницу и убирает окна, которые закрывают её."""

from __future__ import annotations

import re
from pathlib import Path

from playwright.async_api import async_playwright

_CHROME = "/usr/bin/google-chrome"
_MAX_PASSES = 16
_HAS_OVERLAY = """
() => [...document.querySelectorAll("body *")].some((el) => {
  const style = getComputedStyle(el);
  if (style.position !== "fixed" && style.position !== "absolute") return false;
  const box = el.getBoundingClientRect();
  return box.width * box.height > window.innerWidth * window.innerHeight * 0.35;
})
"""

# Один проход: закрыть верхнее мешающее окно. Заголовок или пустая строка.
_DISMISS_ONE = """
() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const text = (el) =>
    (el.innerText || el.getAttribute("aria-label") || "")
      .replace(/\\s+/g, " ")
      .trim();
  const visible = (el) => {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (Number(style.opacity) === 0) return false;
    const box = el.getBoundingClientRect();
    return box.width > 8 && box.height > 8;
  };
  const overlays = [...document.querySelectorAll("body *")].filter((el) => {
    if (!visible(el)) return false;
    const style = getComputedStyle(el);
    const dialog = el.getAttribute("role") === "dialog" || el.getAttribute("aria-modal") === "true";
    if (style.position !== "fixed" && style.position !== "absolute" && !dialog) return false;
    const box = el.getBoundingClientRect();
    return box.width * box.height > vw * vh * 0.35 && box.width > vw * 0.5 && box.height > vh * 0.35;
  }).sort((a, b) => (Number(getComputedStyle(a).zIndex) || 0) - (Number(getComputedStyle(b).zIndex) || 0));
  const overlay = overlays[overlays.length - 1];
  if (!overlay) return "";
  const title = text(overlay).slice(0, 80);
  const buttons = [...overlay.querySelectorAll("button, [role='button']")].filter(visible);
  const labeled = buttons.find((button) => /закрыть|close|dismiss/i.test(text(button)));
  const corner = buttons
    .filter((button) => {
      const label = (button.innerText || "").trim();
      const box = button.getBoundingClientRect();
      return label.length <= 1 && box.width <= 48 && box.height <= 48 && box.y < vh * 0.35;
    })
    .sort((a, b) => a.getBoundingClientRect().y - b.getBoundingClientRect().y);
  const close = labeled || corner[0];
  if (!close) return { title: title || "окно", x: 0, y: 0 };
  const box = close.getBoundingClientRect();
  return { title: title || "окно", x: box.x + box.width / 2, y: box.y + box.height / 2 };
}
"""

_HIDE_TOP = """
() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const overlays = [...document.querySelectorAll("body *")].filter((el) => {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (style.position !== "fixed" && style.position !== "absolute") return false;
    const box = el.getBoundingClientRect();
    return box.width * box.height > vw * vh * 0.35;
  });
  const overlay = overlays[overlays.length - 1];
  if (overlay) overlay.style.setProperty("display", "none", "important");
}
"""


class PageCleaner:
    """Открывает адрес в Chrome и закрывает перекрывающие окна."""

    def __init__(self, executable: str = _CHROME) -> None:
        self.executable = executable

    async def open_and_clear(self, url: str, screenshot: str | Path | None = None) -> str:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=self.executable,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                page = await browser.new_page(viewport={"width": 1400, "height": 1000})
                await page.goto(url, wait_until="commit", timeout=45000)
                try:
                    await page.wait_for_function(_HAS_OVERLAY, timeout=5000)
                except Exception:
                    pass
                removed = await _clear(page)
                if screenshot is not None:
                    await page.screenshot(path=str(screenshot), full_page=False)
            finally:
                await browser.close()
        if not removed:
            return "Мешающих окон не было."
        titles = "», «".join(removed)
        return f"Убрал: «{titles}»."

    async def reach_order(
        self,
        url: str,
        product: str,
        address: str,
        screenshot: str | Path | None = None,
    ) -> str:
        """Кладёт блюдо в корзину и доходит до оформления. Кнопку оплаты не нажимает."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=self.executable,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                page = await browser.new_page(viewport={"width": 1400, "height": 1100})
                await page.goto(_menu_url(url), wait_until="commit", timeout=45000)
                await page.wait_for_timeout(800)
                try:
                    await page.wait_for_function(_HAS_OVERLAY, timeout=4000)
                except Exception:
                    pass
                await _clear(page)
                added = await page.evaluate(_ADD_PRODUCT, product)
                if not added:
                    return f"Не нашёл «{product}» на странице. Кнопку оформления не нажимал."
                await page.wait_for_timeout(800)
                await page.locator("a[href*='order']").first.click(timeout=8000)
                await page.wait_for_timeout(800)
                chosen = await _fill_address(page, address)
                if screenshot is not None:
                    await page.evaluate("() => window.scrollTo(0, 0)")
                    await page.screenshot(path=str(screenshot), full_page=False)
                paid = await page.evaluate(
                    "() => document.body.innerText.includes('Заказ оформлен') || document.body.dataset.paid === '1'"
                )
            finally:
                await browser.close()
        if paid:
            return f"В корзине {product}. Адрес: {chosen}. Заказ уже был отправлен."
        return (
            f"В корзине {product}. Адрес: {chosen}. "
            "Кнопку «Оформить заказ» не нажимал."
        )


def _menu_url(url: str) -> str:
    if url.startswith("file:"):
        return url
    if "papajohns.ru" in url and not url.rstrip("/").endswith("/pizza"):
        return url.rstrip("/") + "/pizza"
    return url


_ADD_PRODUCT = """
(name) => {
  const title = [...document.querySelectorAll("*")].find((node) =>
    [...node.childNodes].some(
      (child) => child.nodeType === 3 && child.textContent.trim() === name
    )
  );
  if (!title) return false;
  let node = title;
  for (let step = 0; step < 10 && node; step += 1) {
    const button = [...node.querySelectorAll("button")].find(
      (item) => (item.innerText || "").trim() === "В корзину"
    );
    if (button) {
      button.click();
      return true;
    }
    node = node.parentElement;
  }
  return false;
}
"""


def _house_number(address: str) -> str:
    found = re.search(r"(\d+)\s*$", address.strip())
    return found.group(1) if found else ""


def _suggestion_score(text: str, word: str, number: str, address: str) -> int:
    lowered = text.casefold()
    score = 0
    if number and re.search(rf",\s*{re.escape(number)}(?:\D|$)", text):
        score += 10
    if f"{word.casefold()} улица" in lowered:
        score += 4
    if "ямск" in lowered and "ямск" not in address.casefold():
        score -= 5
    return score


def _street_word(address: str) -> str:
    skip = {"улица", "город", "москва", "дом", "квартира"}
    words = [
        part
        for part in re.split(r"[^0-9A-Za-zА-Яа-яЁё]+", address)
        if len(part) > 3 and part.casefold() not in skip
    ]
    words.sort(key=len, reverse=True)
    return words[0] if words else address


async def _fill_address(page: object, address: str) -> str:
    field = page.locator("input[name='address_in_line'], input[placeholder='Адрес']").first  # type: ignore[attr-defined]
    if await field.count() == 0:  # type: ignore[attr-defined]
        return address
    await field.scroll_into_view_if_needed()  # type: ignore[attr-defined]
    await field.click()  # type: ignore[attr-defined]
    await field.fill(address)  # type: ignore[attr-defined]
    word = _street_word(address)
    options = page.locator("li").filter(has_text=word)  # type: ignore[attr-defined]
    try:
        await options.first.wait_for(state="visible", timeout=5000)  # type: ignore[attr-defined]
        count = min(await options.count(), 8)  # type: ignore[attr-defined]
        best = 0
        best_score = -999
        number = _house_number(address)
        for index in range(count):
            text = await options.nth(index).inner_text()  # type: ignore[attr-defined]
            score = _suggestion_score(text, word, number, address)
            if score > best_score:
                best_score = score
                best = index
        await options.nth(best).click()  # type: ignore[attr-defined]
        await page.wait_for_timeout(1200)  # type: ignore[attr-defined]
    except Exception:
        pass
    current = await field.input_value()  # type: ignore[attr-defined]
    return current or address


async def _clear(page: object) -> list[str]:
    removed: list[str] = []
    quiet = 0
    for step in range(_MAX_PASSES):
        found = await page.evaluate(_DISMISS_ONE)  # type: ignore[attr-defined]
        if not found:
            quiet += 1
            if quiet >= 3 and step >= 6:
                break
            await page.wait_for_timeout(500)  # type: ignore[attr-defined]
            continue
        quiet = 0
        short = " ".join(str(found["title"]).split())[:60]
        if found["x"] and found["y"]:
            await page.mouse.click(found["x"], found["y"])  # type: ignore[attr-defined]
        await page.keyboard.press("Escape")  # type: ignore[attr-defined]
        await page.wait_for_timeout(300)  # type: ignore[attr-defined]
        still = await page.evaluate(  # type: ignore[attr-defined]
            "(title) => (document.body.innerText || '').includes(title.slice(0, 24))",
            short,
        )
        if still:
            await page.evaluate(_HIDE_TOP)  # type: ignore[attr-defined]
        if short not in removed:
            removed.append(short)
        await page.wait_for_timeout(300)  # type: ignore[attr-defined]
    return removed
