#!/usr/bin/env python3
"""Rend un CV markdown structuré en .docx ATS-safe, et optionnellement en .pdf.

Une seule colonne, aucun tableau, aucune zone de texte : tout ce qui casse le
parsing des ATS est structurellement impossible à produire ici.

    python3 build_cv.py cv-master.md --pdf
    python3 build_cv.py societe/cv.md --pdf --no-photo

Syntaxe d'entrée : voir references/cv-markdown.md
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

WORKSPACE = Path.home() / "Documents" / "cv"

FONT = "Calibri"
BODY_PT = 10
GRAY = RGBColor(0x59, 0x59, 0x59)
PHOTO_WIDTH_CM = 2.6


# --------------------------------------------------------------------------
# lecture
# --------------------------------------------------------------------------

def parse_source(path: Path):
    """Sépare le front matter (clé: valeur) du corps markdown."""
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            body = text[end + 4:]
    return meta, body


def resolve_photo(name: str, source_dir: Path):
    for candidate in (source_dir / name, WORKSPACE / name, Path(name)):
        if candidate.is_file():
            return candidate
    return None


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------

def setup_document(doc: Document, letter=False):
    """Un CV cherche la densité, une lettre cherche l'air. Seuls les interlignes
    et l'espacement changent, la structure ATS reste identique."""
    section = doc.sections[0]
    section.top_margin = section.bottom_margin = Cm(1.3 if not letter else 2.2)
    section.left_margin = section.right_margin = Cm(1.6 if not letter else 2.2)

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(BODY_PT if not letter else 10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.space_after = Pt(2 if not letter else 9)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.05 if not letter else 1.2

    bullet = doc.styles["List Bullet"]
    bullet.font.name = FONT
    bullet.font.size = Pt(BODY_PT)
    bullet.paragraph_format.space_after = Pt(1)
    bullet.paragraph_format.line_spacing = 1.05


def content_width_cm(doc: Document) -> float:
    section = doc.sections[0]
    return (section.page_width - section.left_margin - section.right_margin) / 360000


def right_tab(doc: Document, paragraph):
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Cm(content_width_cm(doc)), WD_TAB_ALIGNMENT.RIGHT
    )


def bottom_border(paragraph):
    borders = OxmlElement("w:pBdr")
    edge = OxmlElement("w:bottom")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), "6")
    edge.set(qn("w:space"), "1")
    edge.set(qn("w:color"), "808080")
    borders.append(edge)
    paragraph._p.get_or_add_pPr().append(borders)


# --------------------------------------------------------------------------
# rendu inline
# --------------------------------------------------------------------------

def add_runs(paragraph, text: str, bold=False, italic=False, size=None, color=None):
    """Écrit le texte en gérant **gras** inline."""
    for index, chunk in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not chunk:
            continue
        run = paragraph.add_run(chunk)
        run.bold = bold or index % 2 == 1
        run.italic = italic
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = color
    return paragraph


# --------------------------------------------------------------------------
# photo flottante
# --------------------------------------------------------------------------

ANCHOR = """<wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 distT="0" distB="0" distL="114300" distR="114300" simplePos="0" relativeHeight="2"
 behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">
<wp:simplePos x="0" y="0"/>
<wp:positionH relativeFrom="margin"><wp:align>right</wp:align></wp:positionH>
<wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV>
<wp:extent cx="{cx}" cy="{cy}"/>
<wp:effectExtent l="0" t="0" r="0" b="0"/>
<wp:wrapSquare wrapText="bothSides"/>
<wp:docPr id="101" name="photo"/>
<wp:cNvGraphicFramePr/>
{graphic}
</wp:anchor>"""


def add_floating_photo(paragraph, image: Path) -> bool:
    """Ancre la photo en flottant à droite. Retourne False si le rendu échoue.

    Une image inline pousserait tout le bloc d'en-tête vers le bas, alors que
    l'ancre permet au nom et aux coordonnées de rester en haut de page, ce que les
    parseurs ATS attendent.
    """
    from lxml import etree

    try:
        run = paragraph.add_run()
        run.add_picture(str(image), width=Cm(PHOTO_WIDTH_CM))
        inline = run._r.find(qn("w:drawing"))[0]
        extent = inline.find(qn("wp:extent"))
        graphic = inline.find(qn("a:graphic"))
        anchor = parse_xml(ANCHOR.format(
            cx=extent.get("cx"),
            cy=extent.get("cy"),
            graphic=etree.tostring(graphic, encoding="unicode"),
        ))
        inline.getparent().replace(inline, anchor)
        return True
    except Exception as error:  # noqa: BLE001, la photo est décorative, jamais bloquante
        print(f"  ! photo ignorée ({error})", file=sys.stderr)
        return False


# --------------------------------------------------------------------------
# rendu du document
# --------------------------------------------------------------------------

def render_header(doc: Document, meta: dict, photo: Path | None):
    first = doc.add_paragraph()
    first.paragraph_format.space_after = Pt(0)
    if photo:
        add_floating_photo(first, photo)
    add_runs(first, meta.get("name", ""), bold=True, size=20)

    if meta.get("title"):
        para = doc.add_paragraph()
        para.paragraph_format.space_after = Pt(1)
        add_runs(para, meta["title"], size=10.5)

    if meta.get("contact"):
        para = doc.add_paragraph()
        para.paragraph_format.space_after = Pt(10)
        add_runs(para, meta["contact"], size=9.5, color=GRAY)


def render_section(doc: Document, title: str):
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(9)
    para.paragraph_format.space_after = Pt(4)
    add_runs(para, title.upper(), bold=True, size=11)
    bottom_border(para)


def render_job(doc: Document, line: str):
    employer, _, dates = line.partition("|")
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(6)
    para.paragraph_format.space_after = Pt(0)
    para.paragraph_format.keep_with_next = True
    right_tab(doc, para)
    add_runs(para, employer.strip(), bold=True)
    if dates.strip():
        para.add_run("\t")
        add_runs(para, dates.strip(), size=9.5, color=GRAY)


def render_role(doc: Document, text: str):
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(2)
    para.paragraph_format.keep_with_next = True
    add_runs(para, text, italic=True)


def render_stack(doc: Document, text: str):
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(4)
    add_runs(para, text, size=9, color=GRAY)


def render_skill_line(doc: Document, label: str, rest: str):
    para = doc.add_paragraph()
    add_runs(para, label, bold=True)
    add_runs(para, rest)


def render_body(doc: Document, body: str, letter=False):
    buffer: list[str] = []

    def flush():
        if buffer:
            para = add_runs(doc.add_paragraph(), " ".join(buffer))
            if letter and len(buffer) > 1:
                para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            buffer.clear()

    for raw in body.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush()
        elif stripped == "<!-- pagebreak -->":
            flush()
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif stripped.startswith("## "):
            flush()
            render_section(doc, stripped[3:])
        elif stripped.startswith("#### "):
            flush()
            render_role(doc, stripped[5:])
        elif stripped.startswith("### "):
            flush()
            render_job(doc, stripped[4:])
        elif stripped.startswith("> "):
            flush()
            render_stack(doc, stripped[2:])
        elif stripped.startswith("- "):
            flush()
            add_runs(doc.add_paragraph(style="List Bullet"), stripped[2:])
        else:
            match = re.match(r"^\*\*(.+?)\*\*\s*(:.*)$", stripped)
            if match:
                flush()
                render_skill_line(doc, match.group(1), match.group(2))
            else:
                buffer.append(stripped)
    flush()


# --------------------------------------------------------------------------
# sortie
# --------------------------------------------------------------------------

def to_pdf(docx_path: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("  ! soffice introuvable, PDF non généré", file=sys.stderr)
        return None
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf",
         "--outdir", str(docx_path.parent), str(docx_path)],
        check=True, capture_output=True,
    )
    pdf = docx_path.with_suffix(".pdf")
    return pdf if pdf.is_file() else None


def verify_extraction(pdf: Path, expected_name: str) -> bool:
    """Un PDF dont le texte ne ressort pas est invisible pour un ATS."""
    if not shutil.which("pdftotext"):
        return True
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True,
    ).stdout
    ok = len(text) > 1200 and expected_name.split()[0].lower() in text.lower()
    print(f"  extraction : {len(text)} caractères, {'OK' if ok else 'ÉCHEC'}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Rend un CV markdown en docx/pdf ATS-safe")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out-dir", type=Path, help="défaut : <dossier source>/build")
    parser.add_argument("--pdf", action="store_true", help="convertir aussi en PDF")
    parser.add_argument("--no-photo", action="store_true")
    parser.add_argument("--letter", action="store_true",
                        help="mise en page de lettre : marges larges, paragraphes aérés et justifiés")
    args = parser.parse_args()

    if not args.source.is_file():
        sys.exit(f"introuvable : {args.source}")

    meta, body = parse_source(args.source)
    photo = None
    if meta.get("photo") and not args.no_photo:
        photo = resolve_photo(meta["photo"], args.source.parent)
        if photo is None:
            print(f"  ! photo « {meta['photo']} » introuvable", file=sys.stderr)

    doc = Document()
    setup_document(doc, letter=args.letter)
    render_header(doc, meta, photo)
    render_body(doc, body, letter=args.letter)

    out_dir = args.out_dir or args.source.parent / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"{args.source.stem.replace('cv-master', 'cv')}.docx"
    doc.save(docx_path)
    print(f"  docx : {docx_path}")

    if args.pdf:
        pdf = to_pdf(docx_path)
        if pdf:
            print(f"  pdf  : {pdf}")
            if not verify_extraction(pdf, meta.get("name", "")):
                sys.exit("PDF non extractible, inutilisable pour un ATS")


if __name__ == "__main__":
    main()
