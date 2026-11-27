"""«Я хочу …»: город, адрес и телефон агент не выдумывает, а спрашивает."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from urllib.parse import quote_plus

from agent.tool_runner import ToolRunner

_WANT = re.compile(
    r"^(?:я хочу|хочу|мне нужно|мне нужна|мне нужен|закажи|заказать)\s+(.+)$",
    re.IGNORECASE,
)
_CITY = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-\s]{1,40}$")
_FIELDS = ("city", "address", "phone")
_QUESTIONS = {
    "city": "В каком городе доставить? Сам я город не знаю.",
    "address": "Какой адрес доставки? Сам я адрес не знаю.",
    "phone": "Какой номер телефона указать? Сам я телефон не знаю.",
}


class Wants:
    """Ведёт заказ и задаёт следующий недостающий вопрос."""

    def __init__(self, runner: ToolRunner | None = None, root: str | Path = "home") -> None:
        self.runner = runner or ToolRunner()
        self.root = Path(root)

    async def fulfill(self, task: str) -> str | None:
        text = " ".join(task.strip().split())
        if not text:
            return None
        order = _read_json(self._order_path())
        want = _WANT.match(text)
        if want is not None:
            item = want.group(1).strip(" .,!?:;")
            if not item or item.lower().startswith("список"):
                return None
            profile = _read_json(self._profile_path())
            order = {
                "item": item,
                "city": profile.get("city") or None,
                "address": profile.get("address") or None,
                "phone": profile.get("phone") or None,
            }
            _write_json(self._order_path(), order)
            return await self._continue(order)
        if not order or not order.get("item"):
            return None
        return await self._take_answer(order, text)

    async def _take_answer(self, order: dict[str, str | None], text: str) -> str:
        field = _missing(order)
        if field is None:
            return await self._continue(order)
        if not _accepts(field, text):
            return f"Это не похоже на ответ. {_QUESTIONS[field]}"
        order[field] = text
        profile = _read_json(self._profile_path())
        profile[field] = text
        _write_json(self._profile_path(), profile)
        _write_json(self._order_path(), order)
        return await self._continue(order)

    async def _continue(self, order: dict[str, str | None]) -> str:
        item = str(order["item"])
        field = _missing(order)
        if field is not None:
            known = _known_lines(order)
            prefix = f"Заказываю {item}."
            if known:
                prefix = prefix + " " + known
            return f"{prefix} {_QUESTIONS[field]}"
        city = str(order["city"])
        address = str(order["address"])
        phone = str(order["phone"])
        place, url = _place_for(item, city)
        await self.runner.execute(f"python -m webbrowser -t {shlex.quote(url)}")
        self._order_path().unlink(missing_ok=True)
        return (
            f"Заказ: {item}. Город: {city}. Адрес: {address}. Телефон: {phone}. "
            f"Открываю {place}: {url}"
        )

    def _order_path(self) -> Path:
        return self.root / "order.json"

    def _profile_path(self) -> Path:
        return self.root / "profile.json"


def _missing(order: dict[str, str | None]) -> str | None:
    for field in _FIELDS:
        if not order.get(field):
            return field
    return None


def _known_lines(order: dict[str, str | None]) -> str:
    labels = {"city": "Город", "address": "Адрес", "phone": "Телефон"}
    parts = [f"{labels[field]}: {order[field]}." for field in _FIELDS if order.get(field)]
    return " ".join(parts)


def _accepts(field: str, value: str) -> bool:
    if field == "phone":
        return 10 <= len(re.sub(r"\D", "", value)) <= 15
    if field == "city":
        return _CITY.fullmatch(value) is not None
    return len(value) >= 5


def _place_for(item: str, city: str) -> tuple[str, str]:
    if "пицц" in item.lower() and city.casefold() in {"москва", "мск"}:
        return "Папа Джонс", "https://papajohns.ru/moscow"
    query = quote_plus(f"заказать {item} {city}")
    return "поиск заказа", f"https://yandex.ru/search/?text={query}"


def _read_json(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value}


def _write_json(path: Path, payload: dict[str, str | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
