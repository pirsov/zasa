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
from build_stats import variant_9
from docx_lib import new_document

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


def detect_pages(docx_path):
    pdf = to_pdf(docx_path)
    pages = pages_text(pdf)
    found = {}
    for i, key in enumerate(HEADINGS, 1):
        hits = [n for n, page in enumerate(pages, 1) if key in page]
        if not hits:
            raise SystemExit(f"Не найден заголовок: {key}")
        found[i] = hits[-1]
        print(f"  content {i:02d} -> page {hits[-1]}  ({key})")
    return found


COMBINED = os.path.join(ROOT, "готовые_работы/Все_контрольные_для_печати.docx")


def main():
    print("russian")
    build_russian(RU)
    print("page numbers")
    pages = detect_pages(RU)
    build_russian(RU, pages=pages)
    print("business")
    build_business(BUS)
    print("stats")
    build_stats()
    print("combined")
    doc = new_document()
    doc.core_properties.title = "Контрольные работы. Кисловская Виолетта. 2621578"
    build_russian(doc=doc, pages=pages)
    build_business(doc=doc, new_section=True)
    variant_9(doc=doc, new_section=True)
    doc.core_properties.title = "Контрольные работы. Кисловская Виолетта. 2621578"
    doc.save(COMBINED)
    print("saved", COMBINED)


if __name__ == "__main__":
    main()
