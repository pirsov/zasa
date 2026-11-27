"""Открывает страницу и убирает окна, которые закрывают её."""

from __future__ import annotations

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
