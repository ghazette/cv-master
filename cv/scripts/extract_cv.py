#!/usr/bin/env python3
"""Extrait le texte brut d'un CV existant, pour l'onboarding (references/onboarding.md).

    python3 extract_cv.py ancien-cv.pdf
    python3 extract_cv.py ancien-cv.docx
    python3 extract_cv.py Profile.pdf                    # LinkedIn, « Enregistrer au format PDF »
    python3 extract_cv.py Basic_LinkedInDataExport.zip   # archive de données LinkedIn
    python3 extract_cv.py dossier-export-linkedin/
    python3 extract_cv.py scan.pdf --ocr                 # CV scanné, si tesseract est installé

Formats : .pdf (pdftotext), .docx (XML interne, tableaux et zones de texte
compris), .odt, .doc / .rtf (via LibreOffice), .txt / .md, archive ou dossier
d'export LinkedIn (CSV), image avec --ocr.

Ne structure rien : la mise au format du master se fait avec l'utilisateur.
Code de sortie : 0 texte extrait, 1 quasi aucun texte (document image ou scanné),
2 erreur.
"""

import csv
import io
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
ODT_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"

# Seuls ces fichiers de l'export LinkedIn sont lus. Les messages, contacts et
# invitations de l'archive ne concernent pas le CV et ne sortent jamais.
LINKEDIN = [
    ("Profile.csv", "PROFIL"),
    ("Positions.csv", "EXPÉRIENCES"),
    ("Education.csv", "FORMATION"),
    ("Certifications.csv", "CERTIFICATIONS"),
    ("Skills.csv", "COMPÉTENCES"),
    ("Languages.csv", "LANGUES"),
    ("Projects.csv", "PROJETS"),
    ("Courses.csv", "COURS"),
    ("Honors.csv", "DISTINCTIONS"),
    ("Volunteering.csv", "BÉNÉVOLAT"),
]

SEUIL_SCAN = 200


def docx_paragraphs(xml: bytes) -> list[str]:
    """Texte paragraphe par paragraphe, sans doubler les paragraphes imbriqués
    (zones de texte) ni les rendus de secours VML de Word."""
    root = ET.fromstring(xml)
    out = []

    def collect(node, acc):
        for child in node:
            if child.tag in (W + "p", MC_FALLBACK):
                continue
            if child.tag == W + "t" and child.text:
                acc.append(child.text)
            elif child.tag == W + "tab":
                acc.append(" ")
            collect(child, acc)

    for para in root.iter(W + "p"):
        acc = []
        collect(para, acc)
        line = "".join(acc).strip()
        if line and (not out or out[-1] != line):
            out.append(line)
    return out


def from_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        parts = sorted(n for n in names if n.startswith("word/header") and n.endswith(".xml"))
        parts.append("word/document.xml")
        parts += sorted(n for n in names if n.startswith("word/footer") and n.endswith(".xml"))
        blocks = []
        for name in parts:
            lines = docx_paragraphs(archive.read(name))
            if lines:
                label = "" if name == "word/document.xml" else f"[{Path(name).stem}]\n"
                blocks.append(label + "\n".join(lines))
    return "\n\n".join(blocks)


def from_odt(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    lines = []
    for node in root.iter():
        if node.tag in (ODT_TEXT + "p", ODT_TEXT + "h"):
            line = "".join(node.itertext()).strip()
            if line and (not lines or lines[-1] != line):
                lines.append(line)
    return "\n".join(lines)


def from_pdf(path: Path, layout=False) -> str:
    if not shutil.which("pdftotext"):
        sys.exit("pdftotext absent : installer poppler-utils, ou coller le texte du CV dans le chat")
    cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(path), "-"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def from_office(path: Path) -> str:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        sys.exit(f"{path.suffix} illisible sans LibreOffice : réenregistrer en .docx ou .pdf")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([soffice, "--headless", "--convert-to", "txt:Text",
                        "--outdir", tmp, str(path)], capture_output=True, check=False)
        out = Path(tmp) / (path.stem + ".txt")
        return out.read_text(encoding="utf-8", errors="replace") if out.is_file() else ""


def ocr(path: Path) -> str:
    if not shutil.which("tesseract"):
        sys.exit("tesseract absent : installer tesseract-ocr et tesseract-ocr-fra, "
                 "ou coller le texte du CV dans le chat")
    with tempfile.TemporaryDirectory() as tmp:
        images = [path]
        if path.suffix.lower() == ".pdf":
            subprocess.run(["pdftoppm", "-r", "300", "-png", str(path), f"{tmp}/page"],
                           check=True, capture_output=True)
            images = sorted(Path(tmp).glob("page*.png"))
        return "\n\f".join(
            subprocess.run(["tesseract", str(img), "-", "-l", "fra+eng"],
                           capture_output=True, text=True).stdout
            for img in images
        )


def linkedin_tables(read) -> str:
    """read(nom) renvoie le contenu texte d'un CSV de l'export, ou None."""
    blocks = []
    for name, title in LINKEDIN:
        raw = read(name)
        if not raw:
            continue
        rows = list(csv.DictReader(io.StringIO(raw)))
        if not rows:
            continue
        lines = [f"## {title}"]
        for row in rows:
            fields = [f"{k} : {v.strip()}" for k, v in row.items() if k and v and v.strip()]
            lines.append("\n".join(fields))
            lines.append("")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def from_linkedin_zip(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        by_name = {Path(n).name: n for n in archive.namelist()}

        def read(name):
            member = by_name.get(name)
            return archive.read(member).decode("utf-8-sig", errors="replace") if member else None

        return linkedin_tables(read)


def from_linkedin_dir(path: Path) -> str:
    def read(name):
        hits = list(path.rglob(name))
        return hits[0].read_text(encoding="utf-8-sig", errors="replace") if hits else None

    return linkedin_tables(read)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 1:
        print(__doc__)
        return 2
    path = Path(args[0]).expanduser()
    if not path.exists():
        print(f"introuvable : {path}", file=sys.stderr)
        return 2

    suffix = path.suffix.lower()
    if "--ocr" in flags:
        text = ocr(path)
    elif path.is_dir():
        text = from_linkedin_dir(path)
    elif suffix == ".zip":
        text = from_linkedin_zip(path)
    elif suffix == ".pdf":
        text = from_pdf(path, layout="--layout" in flags)
    elif suffix == ".docx":
        text = from_docx(path)
    elif suffix == ".odt":
        text = from_odt(path)
    elif suffix in (".doc", ".rtf", ".pages", ".wps"):
        text = from_office(path)
    elif suffix in (".txt", ".md", ".text", ""):
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"):
        print("image : relancer avec --ocr (tesseract requis), ou coller le texte", file=sys.stderr)
        return 1
    else:
        print(f"format {suffix} non géré : l'exporter en .pdf ou .docx", file=sys.stderr)
        return 2

    print(text.strip())
    # seul un PDF peu bavard trahit un scan, un export LinkedIn court est normal
    if suffix == ".pdf" and "--ocr" not in flags and len(text.strip()) < SEUIL_SCAN:
        print(f"\n! {len(text.strip())} caractères seulement : document probablement scanné "
              "ou en image. Relancer avec --ocr, ou demander à l'utilisateur de coller le texte.",
              file=sys.stderr)
        return 1
    if not text.strip():
        print("! aucun texte extrait : demander à l'utilisateur de coller le contenu", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
