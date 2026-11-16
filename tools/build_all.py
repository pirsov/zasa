# -*- coding: utf-8 -*-
"""Сборка всех контрольных и простановка страниц в содержании."""

import glob
import os
import re
import subprocess
import zipfile

from build_business import build as build_business
from build_russian import build as build_russian
from build_stats import build_all as build_stats

ROOT = "/workspace"
PDF = "/tmp/pdfs"
os.makedirs(PDF, exist_ok=True)

RU = os.path.join(
    ROOT,
    "готовые_работы/01_Русский_язык_и_культура_речи/Контрольная_работа_РЯиКР_2621578.docx",
)
BUS = os.path.join(
    ROOT,
    "готовые_работы/02_Основы_предпринимательской_деятельности/Контрольная_работа_вариант_8_2621578.docx",
)

# Подстроки заголовков в том же порядке, что пункты содержания.
HEADINGS = [
    "Введение",
    "1 Теоретический раздел",
    "1.1 Понятие антонимии",
    "1.2 Типы антонимов",
    "1.3 Антонимия и многозначность",
    "1.4 Роль антонимов",
    "1.5 Нормы употребления",
    "2 Практический раздел",
    "2.1 Словарные пары",
    "2.2 Антонимы в художественной",
    "2.3 Антонимы в профессиональной",
    "2.4 Редактирование текста",
    "Заключение",
    "Список литературы",
    "Приложение А",
]


def to_pdf(docx_path):
    subprocess.check_call(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            PDF,
            docx_path,
        ],
        stdout=subprocess.DEVNULL,
    )
    name = os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"
    return os.path.join(PDF, name)


def pages_text(pdf_path):
    raw = subprocess.check_output(["pdftotext", "-layout", pdf_path, "-"])
    text = raw.decode("utf-8", errors="replace")
    return text.split("\f")


def fill_contents(docx_path):
    pdf = to_pdf(docx_path)
    pages = pages_text(pdf)
    found = {}
    for i, key in enumerate(HEADINGS, 1):
        hits = [n for n, page in enumerate(pages, 1) if key in page]
        if not hits:
            raise SystemExit(f"Не найден заголовок: {key}")
        # содержание на ранней странице, сам раздел — позже
        found[i] = hits[-1]
        print(f"  content {i:02d} -> page {hits[-1]}  ({key})")
    with zipfile.ZipFile(docx_path, "r") as zin:
        xml = zin.read("word/document.xml").decode("utf-8")
        other = {name: zin.read(name) for name in zin.namelist() if name != "word/document.xml"}
    for i, page in found.items():
        xml = xml.replace(f"@@P{i:02d}@@", str(page))
    if "@@P" in xml:
        raise SystemExit("Остались незаполненные метки содержания")
    tmp = docx_path + ".tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in other.items():
            zout.writestr(name, data)
        zout.writestr("word/document.xml", xml.encode("utf-8"))
    os.replace(tmp, docx_path)
    print("contents filled", docx_path, "pdf pages", len(pages))
    return len(pages)


def main():
    print("russian")
    build_russian(RU)
    print("business")
    build_business(BUS)
    print("stats")
    build_stats()
    print("page numbers")
    fill_contents(RU)


if __name__ == "__main__":
    main()
