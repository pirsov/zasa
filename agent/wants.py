"""«Я хочу …»: город, адрес, телефон, имя и почту агент не выдумывает, а спрашивает."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from urllib.parse import quote_plus

from agent.browser import PageCleaner
from agent.tool_runner import ToolRunner

_WANT = re.compile(
    r"^(?:я хочу|хочу|мне нужно|мне нужна|мне нужен|закажи|заказать)\s+(.+)$",
    re.IGNORECASE,
)
_CONFIRM = re.compile(r"^(?:подтверди|подтверждаю|подтвердить)\b", re.IGNORECASE)
_CODE = re.compile(r"^\d{4,6}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAME = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-\s]{1,40}$")
_CITY = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-\s]{1,40}$")
_FIELDS = ("city", "address", "phone")
_QUESTIONS = {
    "city": "В каком городе доставить? Сам я город не знаю.",
    "address": "Какой адрес доставки? Сам я адрес не знаю.",
    "phone": "Какой номер телефона указать? Сам я телефон не знаю.",
}


class Wants:
    """Ведёт заказ и задаёт следующий недостающий вопрос."""

    def __init__(
        self,
        runner: ToolRunner | None = None,
        root: str | Path = "home",
        pages: PageCleaner | None = None,
    ) -> None:
        self.runner = runner or ToolRunner()
        self.root = Path(root)
        self.pages = pages or PageCleaner()

    async def fulfill(self, task: str) -> str | None:
        text = " ".join(task.strip().split())
        if not text:
            return None
        order = _read_json(self._order_path())
        if order.get("status") == "awaiting_code" and _CODE.fullmatch(text):
            return await self._finish_code(order, text)
        if order.get("status") == "awaiting_code" and _WANT.match(text) is None:
            return "Жду код из смс. Пришлите цифры."
        if order.get("status") == "awaiting_name" and _WANT.match(text) is None:
            return await self._take_contact(order, "name", text)
        if order.get("status") == "awaiting_email" and _WANT.match(text) is None:
            return await self._take_contact(order, "email", text)
        if order.get("status") == "awaiting_confirm" and _CONFIRM.match(text):
            return await self._submit(order)
        if order.get("status") == "awaiting_confirm" and _WANT.match(text) is None:
            return "Жду подтверждения. Напишите «подтверди», чтобы оформить заказ."
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
                "name": profile.get("name") or None,
                "email": profile.get("email") or None,
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
        try:
            if "papajohns.ru" in url:
                cleared = await self.pages.reach_order(
                    url,
                    _pizza_name(item),
                    address,
                    confirm=False,
                    phone=phone,
                )
            else:
                cleared = await self.pages.open_and_clear(url)
        except Exception:
            await self.runner.execute(f"python -m webbrowser -t {shlex.quote(url)}")
            cleared = "До оформления дойти не удалось, страница открыта."
        order["status"] = "awaiting_confirm"
        order["place_url"] = url
        order["product"] = _pizza_name(item) if "papajohns.ru" in url else item
        _write_json(self._order_path(), order)
        return (
            f"Заказ: {item}. Город: {city}. Адрес: {address}. Телефон: {phone}. "
            f"Открываю {place}: {url}. {cleared} "
            "Подтвердить оформление? Напишите «подтверди»."
        )

    async def _take_contact(self, order: dict[str, str], field: str, text: str) -> str:
        if field == "name" and _NAME.fullmatch(text) is None:
            return "Это не похоже на имя. Как вас представить в заказе?"
        if field == "email" and _EMAIL.fullmatch(text) is None:
            return "Это не похоже на почту. Какая почта для чека?"
        order[field] = text
        profile = _read_json(self._profile_path())
        profile[field] = text
        _write_json(self._profile_path(), profile)
        _write_json(self._order_path(), order)
        return await self._submit(order)

    async def _submit(self, order: dict[str, str]) -> str:
        if not order.get("name"):
            order["status"] = "awaiting_name"
            _write_json(self._order_path(), order)
            return "Как вас представить в заказе? Сам я имя не знаю."
        if not order.get("email"):
            order["status"] = "awaiting_email"
            _write_json(self._order_path(), order)
            return "Какая почта для чека? Сам я почту не знаю."
        url = order.get("place_url") or ""
        product = order.get("product") or _pizza_name(str(order.get("item") or ""))
        address = str(order.get("address") or "")
        phone = str(order.get("phone") or "")
        try:
            result = await self.pages.reach_order(
                url,
                product,
                address,
                confirm=True,
                phone=phone,
                name=str(order.get("name") or ""),
                email=str(order.get("email") or ""),
                storage=self._storage_path(),
            )
        except Exception:
            return "Подтверждение есть, но сайт оформление не принял."
        if "Код отправлен" in result:
            order["status"] = "awaiting_code"
            _write_json(self._order_path(), order)
            return result
        self._order_path().unlink(missing_ok=True)
        return result

    async def _finish_code(self, order: dict[str, str], code: str) -> str:
        url = order.get("place_url") or ""
        product = order.get("product") or _pizza_name(str(order.get("item") or ""))
        address = str(order.get("address") or "")
        try:
            result = await self.pages.reach_order(
                url,
                product,
                address,
                confirm=True,
                phone=str(order.get("phone") or ""),
                code=code,
                storage=self._storage_path(),
            )
        except Exception:
            return "Код есть, но сайт оформление не принял."
        if _order_done(result):
            self._order_path().unlink(missing_ok=True)
            self._storage_path().unlink(missing_ok=True)
            Path(str(self._storage_path()) + ".url").unlink(missing_ok=True)
        return result

    def _storage_path(self) -> Path:
        return self.root / "browser_state.json"

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


def _order_done(result: str) -> bool:
    lowered = result.casefold()
    if "не нажимал" in lowered or "не сохранилась" in lowered or "неактивна" in lowered:
        return False
    return "заказ оформлен" in lowered or "номер заказа" in lowered or "нажал" in lowered


def _pizza_name(item: str) -> str:
    lowered = item.casefold()
    for name in ("Пепперони", "Маргарита", "Сырная"):
        if name.casefold() in lowered:
            return name
    return "Пепперони"


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
