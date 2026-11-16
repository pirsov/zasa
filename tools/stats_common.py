# -*- coding: utf-8 -*-
"""Общие расчёты и оформление контрольной по статистике."""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from docx_lib import (
    STUDENT_LINES,
    add_picture,
    add_table,
    bibliography_item,
    body,
    caption,
    figure_caption,
    formula,
    heading,
    new_document,
    source_line,
    title_block,
)

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False

CHARTS = "/tmp/charts"
os.makedirs(CHARTS, exist_ok=True)


def fmt(n, d=2):
    neg = n < 0
    s = f"{abs(n):.{d}f}"
    if "." in s:
        whole, frac = s.split(".")
    else:
        whole, frac = s, ""
    parts = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    whole = " ".join(reversed(parts)) or "0"
    out = whole if d == 0 else whole + "," + frac
    return ("−" if neg else "") + out


def pct(n, d=2):
    return fmt(n, d) + " %"


def join_sum(values, d=0):
    return " + ".join(fmt(v, d) if d else str(v) for v in values)


def wavg(prices, qty):
    return sum(p * q for p, q in zip(prices, qty)) / sum(qty)


LITERATURE = [
    "Долгова, В. Н. Статистика : учебник и практикум / В. Н. Долгова, Т. Ю. Медведева. — Москва : Юрайт, 2023.",
    "Ефимова, М. Р. Статистика. Практикум : учебное пособие для СПО / М. Р. Ефимова, Е. В. Петрова, О. И. Ганченко, М. А. Михайлов ; под ред. М. Р. Ефимовой. — Москва : Юрайт, 2021.",
    "Ефимова, М. Р. Статистика. Практикум : учебное пособие / М. Р. Ефимова, Е. В. Петрова, О. И. Ганченко, М. А. Михайлов ; под ред. М. Р. Ефимовой. — Москва : Юрайт, 2023.",
    "Об официальном статистическом учёте и системе государственной статистики в Российской Федерации : Федеральный закон от 29.11.2007 № 282-ФЗ.",
    "Сальникова, К. В. Статистика : учебник для СПО / К. В. Сальникова. — Саратов : Профобразование, 2021.",
    "Федеральная служба государственной статистики : официальный сайт. — URL: https://rosstat.gov.ru (дата обращения: 16.11.2026).",
]


def start(variant, letters, question):
    doc = new_document()
    doc.core_properties.title = f"Статистика. Вариант {variant}. Зачётная книжка 2621578"
    title_block(
        doc,
        "ОП.02 Статистика",
        [
            f"Вариант {variant}",
            "Кисловская Виолетта, буква «К»",
        ],
        STUDENT_LINES,
    )
    body(
        doc,
        "Фамилия студентки — Кисловская, заглавная буква «К». По методическим указаниям буквы К и Л соответствуют варианту 9, поэтому выполнен вариант 9. Номер зачётной книжки 2621578 на выбор варианта по статистике не влияет. Расчёты выполнены по исходным данным задания. Проценты в таблицах округлены; в формулах оставлены знаки, по которым результат можно пересчитать.",
    )
    heading(doc, "1. Теоретический вопрос")
    body(doc, question)
    return doc


def finish(doc, path):
    heading(doc, "Список использованной литературы")
    for i, src in enumerate(LITERATURE, 1):
        bibliography_item(doc, f"{i}. {src}")
    doc.save(path)


def line_chart(path, labels, series, ylabel, title):
    fig, ax = plt.subplots(figsize=(9.2, 4.8), dpi=160)
    for name, values, style in series:
        ax.plot(labels, values, marker="o", linewidth=2, label=name, linestyle=style)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def bar_chart(path, labels, series, ylabel, title):
    import numpy as np

    fig, ax = plt.subplots(figsize=(9.2, 4.8), dpi=160)
    x = np.arange(len(labels))
    width = 0.8 / len(series)
    for i, (name, values) in enumerate(series):
        ax.bar(x + i * width, values, width, label=name)
    ax.set_xticks(x + width * (len(series) - 1) / 2)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def interval_mean(groups, freqs, closed_width=40):
    """Открытые интервалы: ширина равна соседнему. Возвращает середины и среднюю."""
    mids = []
    for i, (a, b) in enumerate(groups):
        if a is None:
            mids.append(b - closed_width / 2)
        elif b is None:
            mids.append(a + closed_width / 2)
        else:
            mids.append((a + b) / 2)
    mean = sum(m * f for m, f in zip(mids, freqs)) / sum(freqs)
    return mids, mean


def mode_interval(x0, h, f_prev, f_mo, f_next):
    return x0 + h * (f_mo - f_prev) / ((f_mo - f_prev) + (f_mo - f_next))
