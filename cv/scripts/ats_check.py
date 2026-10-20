#!/usr/bin/env python3
"""Contrôle mécanique de parsabilité ATS sur un .pdf ou un .docx.

Ne juge pas le contenu : mesure uniquement ce qu'une machine verrait du document.
Les items 2, 3, 5 et 6 de la grille d'audit se tranchent avec cette sortie.

    python3 ats_check.py <workspace>/build/cv.pdf
    python3 ats_check.py <workspace>/<societe>/build/lettre.pdf --letter
"""

import re
import shutil
import subprocess
import sys
import zipfile
from html import unescape
from pathlib import Path

SECTIONS = ["PROFIL", "COMPÉTENCE", "EXPÉRIENCE", "FORMATION", "LANGUE"]


def line(status: str, label: str, detail: str = ""):
    print(f"  {status} {label}{' : ' + detail if detail else ''}")


def check_pdf(path: Path, letter=False) -> list[str]:
    alerts = []
    if not shutil.which("pdftotext"):
        return ["pdftotext absent (poppler-utils) : extraction non vérifiable"]

    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True
    ).stdout

    pages = text.count("\f") or 1
    words = len(text.split())

    seuil = 800 if not letter else 400
    if len(text.strip()) < seuil:
        alerts.append("PDF plat ou scanné : quasi aucun texte extractible, "
                      "le contenu est invisible pour un ATS")
        line("✗", "extraction", f"{len(text)} caractères")
    else:
        line("✓", "extraction", f"{len(text)} caractères, {words} mots")

    line("·", "pages", str(pages))
    maxi = 2 if not letter else 1
    if pages > maxi:
        alerts.append(f"{pages} pages : viser {maxi} page(s) pour ce document")

    if not letter:
        alerts += check_sections(text)
    return alerts + check_punctuation(text)


def check_punctuation(text: str) -> list[str]:
    """Tiret cadratin et point-virgule signent un texte écrit par une IA.

    Un recruteur qui repère la signature relit tout le dossier avec ce soupçon,
    donc le coût dépasse de loin le confort stylistique de ces deux caractères.
    """
    alerts = []
    for char, name, fix in (
        ("—", "tiret cadratin", "remplacer par une virgule, un deux-points ou des parenthèses"),
        (";", "point-virgule", "couper en deux phrases"),
    ):
        count = text.count(char)
        if count:
            line("✗", name, f"{count} occurrence(s)")
            alerts.append(f"{count} {name} « {char} » : {fix}")
        else:
            line("✓", name, "aucun")
    return alerts


def check_sections(text: str) -> list[str]:
    upper = text.upper()
    missing = [s for s in SECTIONS if s not in upper]
    if missing:
        line("!", "sections", "manquantes : " + ", ".join(missing))
        return [f"sections attendues absentes du texte extrait : {', '.join(missing)}"]
    line("✓", "sections", "toutes détectées")
    return []


def check_docx(path: Path, letter=False) -> list[str]:
    alerts = []
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        images = [n for n in archive.namelist() if n.startswith("word/media/")]

    tables = xml.count("<w:tbl>")
    boxes = xml.count("<w:txbxContent>") + xml.count("<v:textbox")
    columns = len(re.findall(r'<w:cols[^>]*w:num="([2-9])"', xml))

    for count, label, message in (
        (tables, "tableaux", "un tableau se parse cellule par cellule dans un ordre imprévisible"),
        (boxes, "zones de texte", "une zone de texte est souvent ignorée par les parseurs"),
        (columns, "multi-colonnes", "les colonnes mélangent l'ordre de lecture"),
    ):
        if count:
            line("✗", label, str(count))
            alerts.append(f"{count} {label} : {message}")
        else:
            line("✓", label, "aucun")

    line("·", "images", f"{len(images)} (0 ou 1 attendue : la photo)")
    if len(images) > 1:
        alerts.append(f"{len(images)} images : seule la photo de profil est tolérée, "
                      "toute autre image ne produit aucun texte extractible")

    # unescape sinon « &amp; » compte comme un point-virgule
    text = unescape(" ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)))
    if not letter:
        alerts += check_sections(text)
    return alerts + check_punctuation(text)


def main():
    args = [a for a in sys.argv[1:] if a != "--letter"]
    # une lettre n'a pas les rubriques d'un CV : le controle de sections n'y a pas de sens
    letter = "--letter" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    path = Path(args[0]).expanduser()
    if not path.is_file():
        sys.exit(f"introuvable : {path}")

    print(f"\n{path.name}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        alerts = check_pdf(path, letter)
    elif suffix == ".docx":
        alerts = check_docx(path, letter)
    else:
        sys.exit(f"format {suffix} illisible par un ATS : fournir un PDF texte ou un .docx")

    if alerts:
        print("\nAlertes :")
        for alert in alerts:
            print(f"  ✗ {alert}")
        sys.exit(1)
    print("\n✓ document parsable")


if __name__ == "__main__":
    main()
