"""
.ai/templates/docx_helper.py

명세서 .docx 생성용 python-docx 헬퍼.
06_document 단계에서 이 파일을 import하여 내용만 채운다.

사용법:
    import sys
    sys.path.insert(0, ".ai/templates")
    from docx_helper import create_doc, add_h1, add_h2, add_paragraph, add_bullet, add_code_block, add_table

    doc = create_doc()
    add_h1(doc, "1. 개요")
    add_paragraph(doc, "기능 목적 요약...")
    doc.save(".ai/docs/feature-name_명세서.docx")
"""

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ── 문서 생성 ────────────────────────────────────────────────────────────────

def create_doc() -> Document:
    """A4, 한글 기본 스타일이 설정된 Document 객체를 반환한다."""
    doc = Document()

    # 페이지 (A4)
    sec = doc.sections[0]
    sec.page_width   = Cm(21.0)
    sec.page_height  = Cm(29.7)
    sec.left_margin  = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.top_margin   = Cm(2.5)
    sec.bottom_margin = Cm(2.5)

    # Normal
    s = doc.styles['Normal']
    s.font.name = '맑은 고딕'
    s.font.size = Pt(10)
    s.paragraph_format.space_after = Pt(4)

    # Heading 1 — 섹션 제목 (파란 계열 진한 색)
    h1 = doc.styles['Heading 1']
    h1.font.name = '맑은 고딕'
    h1.font.size = Pt(16)
    h1.font.bold = True
    h1.font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after  = Pt(6)

    # Heading 2 — 소항목
    h2 = doc.styles['Heading 2']
    h2.font.name = '맑은 고딕'
    h2.font.size = Pt(12)
    h2.font.bold = True
    h2.font.color.rgb = RGBColor(0x2E, 0x74, 0xB5)
    h2.paragraph_format.space_before = Pt(10)
    h2.paragraph_format.space_after  = Pt(4)

    return doc


# ── 콘텐츠 추가 헬퍼 ─────────────────────────────────────────────────────────

def add_h1(doc: Document, text: str):
    doc.add_heading(text, level=1)


def add_h2(doc: Document, text: str):
    doc.add_heading(text, level=2)


def add_paragraph(doc: Document, text: str):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(4)
    for run in p.runs:
        run.font.name = '맑은 고딕'


def add_bullet(doc: Document, text: str):
    """불릿 목록 한 줄 추가."""
    p = doc.add_paragraph(text, style='List Bullet')
    for run in p.runs:
        run.font.name = '맑은 고딕'
        run.font.size = Pt(10)


def add_code_block(doc: Document, text: str):
    """회색 배경 + Courier New 고정폭 코드 블록."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent  = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)

    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  'F2F2F2')
    pPr.append(shd)

    run = p.add_run(text)
    run.font.name = 'Courier New'
    run.font.size = Pt(9)


def add_table(doc: Document, headers: list, rows: list):
    """헤더 파란 배경 + 셀 테두리 테이블.

    headers : ['컬럼1', '컬럼2', ...]
    rows    : [['값1', '값2', ...], ...]
    """
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'

    # 헤더 행
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        run = cell.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.name = '맑은 고딕'
        run.font.size = Pt(9)
        _set_cell_bg(cell, 'D6E4F7')

    # 데이터 행
    for row_data in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row_data):
            cells[i].text = str(val)
            for para in cells[i].paragraphs:
                for run in para.runs:
                    run.font.name = '맑은 고딕'
                    run.font.size = Pt(9)

    doc.add_paragraph()  # 표 뒤 여백


# ── 내부 유틸 ────────────────────────────────────────────────────────────────

def _set_cell_bg(cell, hex_color: str):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)
