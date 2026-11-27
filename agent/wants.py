"""«Я хочу …»: человек называет результат, агент сам выбирает, где его взять."""

from __future__ import annotations

import re
import shlex
from urllib.parse import quote_plus

from agent.tool_runner import ToolRunner

_WANT = re.compile(
    r"^(?:я хочу|хочу|мне нужно|мне нужна|мне нужен|закажи|заказать)\s+(.+)$",
    re.IGNORECASE,
)
# Еда, которую можно заказать с доставкой в Москве. Остальное уходит в поиск.
_ORDERS: tuple[tuple[str, str, str], ...] = (
    ("пицц", "Папа Джонс, Москва", "https://papajohns.ru/moscow"),
)


class Wants:
    """Превращает желание в страницу заказа."""

    def __init__(self, runner: ToolRunner | None = None) -> None:
        self.runner = runner or ToolRunner()

    async def fulfill(self, task: str) -> str | None:
        text = " ".join(task.strip().split())
        found = _WANT.match(text)
        if found is None:
            return None
        item = found.group(1).strip(" .,!?:;")
        if not item or item.lower().startswith("список"):
            return None
        place, url = _place_for(item)
        await self.runner.execute(f"python -m webbrowser -t {shlex.quote(url)}")
        return f"Заказываю {item}. {place}: {url}"


def _place_for(item: str) -> tuple[str, str]:
    lowered = item.lower()
    for stem, place, url in _ORDERS:
        if stem in lowered:
            return place, url
    query = quote_plus(f"заказать {item} Москва")
    return "поиск заказа", f"https://yandex.ru/search/?text={query}"
