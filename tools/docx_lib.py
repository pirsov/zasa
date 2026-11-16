# -*- coding: utf-8 -*-
"""Оформление контрольных работ: А4, Times New Roman 14, интервал 1,5, абзац 1,25 см."""

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, Twips, Emu
from lxml import etree


FONT = "Times New Roman"


def _rfonts(rPr, name):
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), name)


def set_run_font(run, size=14, bold=False, italic=False, name=FONT):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = None
    rPr = run._element.get_or_add_rPr()
    _rfonts(rPr, name)
    # сбросить цвет темы, чтобы заголовки не становились синими
    for child in list(rPr):
        if child.tag == qn("w:color"):
            rPr.remove(child)
    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:val"), "ru-RU")
    lang.set(qn("w:eastAsia"), "ru-RU")


def _set_style_font(style, size=14):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = False
    style.font.italic = False
    style.font.color.rgb = None
    rPr = style.element.get_or_add_rPr()
    _rfonts(rPr, FONT)
    for child in list(rPr):
        if child.tag == qn("w:color"):
            rPr.remove(child)


def new_document():
    doc = Document()
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(30)
    section.right_margin = Mm(15)
    section.top_margin = Mm(20)
    section.bottom_margin = Mm(20)
    section.header_distance = Mm(10)
    section.footer_distance = Mm(10)
    section.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    _set_style_font(normal, 14)
    pf = normal.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.first_line_indent = Cm(1.25)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for style_name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        try:
            _set_style_font(doc.styles[style_name], 14)
        except KeyError:
            pass

    _add_page_number(section.footer)
    # титульный лист без номера
    fp = section.first_page_footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    core = doc.core_properties
    core.author = "Кисловская Виолетта"
    core.language = "ru-RU"
    return doc


def _add_page_number(footer):
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    run = p.add_run()
    set_run_font(run, size=12)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def _paragraph(doc, align, indent, before=0, after=0, spacing=1.5, keep_with_next=False, keep_together=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = align
    pf.first_line_indent = Cm(indent)
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = (
        WD_LINE_SPACING.ONE_POINT_FIVE if spacing == 1.5 else WD_LINE_SPACING.SINGLE
    )
    pf.keep_with_next = keep_with_next
    pf.keep_together = keep_together
    pPr = p._p.get_or_add_pPr()
    # запрет автоматического интервала Word
    auto = OxmlElement("w:autoSpaceDE")
    # не требуется
    return p


def add_runs(p, text, size=14, bold=False, italic=False):
    """Поддержка **жирного** внутри абзаца."""
    if text is None:
        return
    parts = str(text).split("**")
    for i, part in enumerate(parts):
        if part == "":
            continue
        run = p.add_run(part)
        set_run_font(run, size=size, bold=bold or (i % 2 == 1), italic=italic)


def body(doc, text, size=14):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, 1.25)
    add_runs(p, text, size=size)
    return p


def body_no_indent(doc, text, size=14, bold=False, center=False, before=0, after=0, spacing=1.5):
    align = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
    p = _paragraph(doc, align, 0, before=before, after=after, spacing=spacing)
    add_runs(p, text, size=size, bold=bold)
    return p


def center(doc, text, bold=False, size=14, before=0, after=0, spacing=1.0):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER, 0, before=before, after=after, spacing=spacing)
    add_runs(p, text, size=size, bold=bold)
    return p


def right(doc, text, size=14, spacing=1.0, before=0, after=0):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.RIGHT, 0, before=before, after=after, spacing=spacing)
    add_runs(p, text, size=size)
    return p


def heading(doc, text, level=1):
    before = 12 if level == 1 else 10
    after = 8 if level == 1 else 6
    align = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
    p = _paragraph(
        doc, align, 0, before=before, after=after, spacing=1.5, keep_with_next=True
    )
    add_runs(p, text, size=14, bold=True)
    return p


def formula(doc, text):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER, 0, before=6, after=6, spacing=1.5)
    add_runs(p, text, size=14, italic=False)
    return p


def caption(doc, text):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.LEFT, 0, before=10, after=4, spacing=1.0, keep_with_next=True)
    add_runs(p, text, size=14)
    return p


def figure_caption(doc, text):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER, 0, before=4, after=8, spacing=1.0)
    add_runs(p, text, size=14)
    return p


def source_line(doc, text="Источник: рассчитано по данным контрольного задания."):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.LEFT, 0, before=2, after=6, spacing=1.0)
    add_runs(p, text, size=12, italic=True)
    return p


def page_break(doc):
    doc.add_page_break()


def bibliography_item(doc, text):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.JUSTIFY, 0, before=0, after=2, spacing=1.5)
    pf = p.paragraph_format
    pf.left_indent = Cm(1.25)
    pf.first_line_indent = Cm(-1.25)
    add_runs(p, text, size=14)
    return p


def _shade(cell, color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:fill"), color)
    shd.set(qn("w:val"), "clear")


def _set_cell_border(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)
    for edge in ("top", "left", "bottom", "right"):
        el = tcBorders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tcBorders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")


def _set_table_widths(table, widths_mm):
    table.autofit = False
    table.allow_autofit = False
    tbl = table._tbl
    tblPr = tbl.tblPr
    total = int(sum(widths_mm) * 56.7)
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), str(total))
    tblW.set(qn("w:type"), "dxa")
    # фиксированная раскладка
    layout = tblPr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tblPr.append(layout)
    layout.set(qn("w:type"), "fixed")
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    for w in widths_mm:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(int(w * 56.7)))
        grid.append(gc)
    tblPr.addnext(grid)
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW")
                tcPr.append(tcW)
            tcW.set(qn("w:w"), str(int(widths_mm[i] * 56.7)))
            tcW.set(qn("w:type"), "dxa")


def add_table(doc, headers, rows, widths=None, font=12, header_fill="D9E2F3", first_col_left=True):
    cols = len(headers)
    table = doc.add_table(rows=1 + len(rows), cols=cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    if widths is None:
        widths = [165 / cols] * cols
    _set_table_widths(table, widths)

    def fill(cell, text, bold=False, header=False, left=False):
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        # очистить абзац по умолчанию
        p = cell.paragraphs[0]
        p.clear()
        pf = p.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT if left else WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)
        pf.space_before = Pt(1)
        pf.space_after = Pt(1)
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        add_runs(p, "" if text is None else str(text), size=font, bold=bold or header)
        _set_cell_border(cell)
        if header:
            _shade(cell, header_fill)
        # поля ячейки
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        mar = tcPr.find(qn("w:tcMar"))
        if mar is None:
            mar = OxmlElement("w:tcMar")
            tcPr.append(mar)
        for edge, val in (("top", 40), ("bottom", 40), ("left", 60), ("right", 60)):
            el = mar.find(qn(f"w:{edge}"))
            if el is None:
                el = OxmlElement(f"w:{edge}")
                mar.append(el)
            el.set(qn("w:w"), str(val))
            el.set(qn("w:type"), "dxa")

    for j, h in enumerate(headers):
        fill(table.rows[0].cells[j], h, header=True, left=False)
    tr = table.rows[0]._tr
    trPr = tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    trPr.append(th)

    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            left = first_col_left and j == 0
            fill(table.rows[i + 1].cells[j], val, left=left)
    # небольшой отступ после таблицы — пустой абзац не добавляем, source_line или body даст интервал
    return table


def add_picture(doc, path, width_cm=15.5):
    p = _paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER, 0, before=4, after=2, spacing=1.0)
    run = p.add_run()
    run.add_picture(path, width=Cm(width_cm))
    return p


def title_block(doc, discipline, subject_lines, extra_lines):
    """Титульный лист колледжа ДГТУ. Интервал одинарный, кегль 14."""
    lines_top = [
        "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ",
        "РОССИЙСКОЙ ФЕДЕРАЦИИ",
        "",
        "ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ",
        "ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ",
        "«ДОНСКОЙ ГОСУДАРСТВЕННЫЙ",
        "ТЕХНИЧЕСКИЙ УНИВЕРСИТЕТ»",
        "(ДГТУ)",
        "",
        "Колледж экономики, управления и права",
        "",
        "Специальность 38.02.01",
        "Экономика и бухгалтерский учёт (по отраслям)",
        "Заочная форма обучения",
    ]
    for line in lines_top:
        center(
            doc,
            line,
            bold=line.startswith("«ДОНСКОЙ")
            or line.startswith("ТЕХНИЧЕСКИЙ")
            or line.startswith("Колледж"),
            spacing=1.0,
        )

    center(doc, "", spacing=1.0)
    center(doc, "КОНТРОЛЬНАЯ РАБОТА", bold=True, spacing=1.0, before=6)
    center(doc, f"по дисциплине «{discipline}»", spacing=1.0)
    center(doc, "", spacing=1.0)
    for line in subject_lines:
        center(doc, line, bold=True, spacing=1.0)

    center(doc, "", spacing=1.0)
    center(doc, "", spacing=1.0)
    for line in extra_lines:
        right(doc, line, spacing=1.0)

    # прижать город к низу за счёт пустых строк — их число подбирается так, чтобы лист остался одним
    for _ in range(2):
        center(doc, "", spacing=1.0)
    center(doc, "Ростов-на-Дону", spacing=1.0)
    center(doc, "2026", spacing=1.0)
    page_break(doc)


STUDENT_LINES = [
    "Выполнила студентка",
    "Кисловская Виолетта",
    "зачётная книжка № 2621578",
    "курс ______   группа ______",
    "",
    "Проверил преподаватель",
    "________________ / ФИО /",
    "",
    "Дата выполнения: 16 ноября 2026 г.",
]
