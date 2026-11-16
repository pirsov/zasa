# -*- coding: utf-8 -*-
"""Оформление контрольных работ: А4, Times New Roman 14, интервал 1,5, абзац 1,25 см."""

import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, Twips, Emu
from lxml import etree


FONT = "Times New Roman"
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dstu_logo.jpg")


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


def _page_start(section, start):
    sectPr = section._sectPr
    pgNumType = sectPr.find(qn("w:pgNumType"))
    if pgNumType is None:
        pgNumType = OxmlElement("w:pgNumType")
        sectPr.append(pgNumType)
    pgNumType.set(qn("w:start"), str(start))


def _format_title_section(section):
    """Поля как в образце титульного листа ДГТУ: левое 20 мм, правое 10 мм."""
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(20)
    section.right_margin = Mm(10)
    section.top_margin = Mm(15)
    section.bottom_margin = Mm(15)
    section.header_distance = Mm(8)
    section.footer_distance = Mm(8)
    section.different_first_page_header_footer = False
    try:
        section.footer.is_linked_to_previous = False
    except Exception:
        pass
    p = section.footer.paragraphs[0]
    p.clear()
    _page_start(section, 1)


def _format_body_section(section):
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = Mm(30)
    section.right_margin = Mm(15)
    section.top_margin = Mm(20)
    section.bottom_margin = Mm(20)
    section.header_distance = Mm(10)
    section.footer_distance = Mm(10)
    section.different_first_page_header_footer = False
    section.footer.is_linked_to_previous = False
    section.header.is_linked_to_previous = False
    p = section.footer.paragraphs[0]
    p.clear()
    _add_page_number(section.footer)
    _page_start(section, 2)


def new_document():
    doc = Document()
    _format_title_section(doc.sections[0])

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


def _nil_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        borders.append(el)
    tblPr.append(borders)


def _cell(cell, text, size=12, bold=False, align="left"):
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.clear()
    pf = p.paragraph_format
    pf.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }[align]
    pf.first_line_indent = Cm(0)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    add_runs(p, text, size=size, bold=bold)


def title_block(doc, discipline, variant, theme=None, new_section=False):
    """Титульный лист по образцу ДГТУ. Азовский филиал заменён на колледж в Ростове-на-Дону."""
    if new_section:
        section = doc.add_section(WD_SECTION.NEW_PAGE)
        _format_title_section(section)
    else:
        _format_title_section(doc.sections[-1])

    if os.path.exists(LOGO):
        p = _paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER, 0, before=0, after=2, spacing=1.0)
        run = p.add_run()
        run.add_picture(LOGO, width=Cm(1.7))

    center(doc, "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ", bold=True, size=12, spacing=1.0)
    center(doc, "РОССИЙСКОЙ ФЕДЕРАЦИИ", bold=True, size=12, spacing=1.0, before=0)
    center(doc, "", spacing=1.0)
    for line in (
        "ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ",
        "ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ",
        "«ДОНСКОЙ ГОСУДАРСТВЕННЫЙ ТЕХНИЧЕСКИЙ УНИВЕРСИТЕТ»",
        "КОЛЛЕДЖ ЭКОНОМИКИ, УПРАВЛЕНИЯ И ПРАВА",
    ):
        center(doc, line, bold=True, size=14, spacing=1.0)

    center(doc, "", spacing=1.0)
    center(doc, "Заочное отделение", size=12, spacing=1.0)
    center(doc, "Специальность 38.02.01", size=12, spacing=1.0)
    center(doc, "«Экономика и бухгалтерский учёт (по отраслям)»", size=12, spacing=1.0)

    center(doc, "", spacing=1.0)
    center(doc, "КОНТРОЛЬНАЯ РАБОТА", bold=True, size=14, spacing=1.0, before=6)
    center(doc, "", spacing=1.0)

    rows = [
        ("Дисциплина", f"«{discipline}»"),
        ("Номер зачетной книжки", "2621578"),
        ("Номер варианта", str(variant)),
        ("Группа", "____________________"),
    ]
    if theme:
        rows.insert(1, ("Тема", theme))
    table = doc.add_table(rows=len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_widths(table, [55, 125])
    _nil_borders(table)
    for i, (label, value) in enumerate(rows):
        _cell(table.rows[i].cells[0], label, size=12, align="left")
        _cell(table.rows[i].cells[1], value, size=12, bold=True, align="left")

    center(doc, "", spacing=1.0)
    sign = doc.add_table(rows=4, cols=3)
    sign.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_widths(sign, [70, 55, 55])
    _nil_borders(sign)
    _cell(sign.rows[0].cells[0], "Обучающийся", size=12)
    _cell(sign.rows[0].cells[1], "________________", size=12, align="center")
    _cell(sign.rows[0].cells[2], "В. Кисловская", size=12, align="right")
    _cell(sign.rows[1].cells[1], "подпись, дата", size=9, align="center")
    _cell(sign.rows[2].cells[0], "Контрольную работу проверил", size=12)
    _cell(sign.rows[2].cells[1], "________________", size=12, align="center")
    _cell(sign.rows[3].cells[1], "подпись, дата", size=9, align="center")

    center(doc, "", spacing=1.0)
    center(doc, "Ростов-на-Дону", size=12, spacing=1.0, before=8)
    center(doc, "2026", size=12, spacing=1.0)

    body_section = doc.add_section(WD_SECTION.NEW_PAGE)
    _format_body_section(body_section)
