#!/usr/bin/env python3
"""Initialise le skill cv : crée le workspace, importe le CV existant, écrit la config.

    python3 init.py                                   # interactif
    python3 init.py --cv ~/Téléchargements/mon-cv.pdf
    python3 init.py --yes --workspace ~/Documents/cv --cv mon-cv.docx --name "Camille Martin"

Le CV d'origine (pdf, docx, odt, txt, md) peut être :
  - passé avec --cv, il est alors copié dans <workspace>/import/,
  - ou déposé à la main dans <workspace>/import/ avant de lancer l'init.
Son texte est extrait dans <workspace>/import/cv-extrait.txt, que Claude lit
pour construire cv-master.md. La photo éventuelle se pose dans <workspace>/
sous le nom photo.jpg ou photo.png (ou via --photo).

Relancer l'init ne réécrit jamais profil.md ni un cv-master.md déjà rempli.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
CONFIG = SKILL_DIR / "config.json"
CV_FORMATS = {".pdf", ".docx", ".odt", ".doc", ".rtf", ".txt", ".md"}
PHOTO_FORMATS = {".jpg", ".jpeg", ".png"}


def ask(question: str, default: str, interactive: bool) -> str:
    if not interactive:
        return default
    answer = input(f"{question} [{default}] : ").strip()
    return answer or default


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        if not shutil.which("pdftotext"):
            raise RuntimeError("pdftotext absent (paquet poppler-utils)")
        return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, check=True).stdout
    if suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    # odt, doc, rtf : passage par LibreOffice
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("soffice introuvable, impossible de lire ce format")
    out = path.parent / ".conversion"
    out.mkdir(exist_ok=True)
    subprocess.run([soffice, "--headless", "--convert-to", "txt:Text",
                    "--outdir", str(out), str(path)], capture_output=True, check=True)
    txt = out / (path.stem + ".txt")
    text = txt.read_text(encoding="utf-8", errors="replace")
    shutil.rmtree(out, ignore_errors=True)
    return text


def set_front_matter(text: str, values: dict) -> str:
    """Remplace les clés du front matter du template. None retire la ligne."""
    head, sep, body = text.partition("\n---\n")
    for key, value in values.items():
        pattern = rf"^{key}:.*$\n?"
        if value is None:
            head = re.sub(pattern, "", head, flags=re.M)
        elif value:
            head = re.sub(rf"^{key}:.*$", f"{key}: {value}", head, flags=re.M)
    return head.rstrip("\n") + sep + body


def check_dependencies():
    print("\nDépendances :")
    try:
        import docx  # noqa: F401
        print("  ✓ python-docx")
    except ImportError:
        print("  ✗ python-docx : pip install --user python-docx")
    for tool, package, role in (
        ("pdftotext", "poppler-utils", "vérification ATS des PDF"),
        ("soffice", "libreoffice", "conversion docx vers pdf"),
    ):
        found = shutil.which(tool) or (tool == "soffice" and shutil.which("libreoffice"))
        print(f"  {'✓' if found else '✗'} {tool}" + ("" if found else f" : installer {package} ({role})"))


def main():
    parser = argparse.ArgumentParser(description="Initialise le skill cv")
    parser.add_argument("--workspace", type=Path, help="défaut : ~/Documents/cv")
    parser.add_argument("--cv", type=Path, help="CV existant à importer")
    parser.add_argument("--photo", type=Path, help="photo à copier dans le workspace")
    parser.add_argument("--name")
    parser.add_argument("--title")
    parser.add_argument("--contact")
    parser.add_argument("--signature", help="défaut : le nom seul")
    parser.add_argument("--yes", action="store_true", help="non interactif, valeurs par défaut")
    args = parser.parse_args()
    interactive = not args.yes and sys.stdin.isatty()

    previous = json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}
    default_ws = previous.get("workspace", str(Path.home() / "Documents" / "cv"))
    workspace = (args.workspace or Path(ask("Dossier de travail", default_ws, interactive))).expanduser().resolve()
    importdir = workspace / "import"
    for d in (workspace, importdir, workspace / "build"):
        d.mkdir(parents=True, exist_ok=True)
    print(f"\nWorkspace : {workspace}")

    # --- CV d'origine -------------------------------------------------------
    cv_path = args.cv
    if not cv_path and interactive and not any(p.suffix.lower() in CV_FORMATS for p in importdir.iterdir()):
        answer = input(f"Chemin de ton CV actuel (vide si tu le déposes plus tard dans {importdir}) : ").strip()
        cv_path = Path(answer) if answer else None
    if cv_path:
        cv_path = cv_path.expanduser()
        if not cv_path.is_file():
            sys.exit(f"introuvable : {cv_path}")
        shutil.copy2(cv_path, importdir / cv_path.name)
        print(f"  CV copié dans {importdir / cv_path.name}")

    sources = sorted(p for p in importdir.iterdir()
                     if p.is_file() and p.suffix.lower() in CV_FORMATS and p.name != "cv-extrait.txt")
    extracted = ""
    if sources:
        source = max(sources, key=lambda p: p.stat().st_mtime)
        try:
            extracted = extract_text(source)
            (importdir / "cv-extrait.txt").write_text(extracted, encoding="utf-8")
            print(f"  texte extrait de {source.name} : {len(extracted.split())} mots")
            if len(extracted.strip()) < 300:
                print("  ! très peu de texte : PDF scanné ou image ? Fournis un .docx ou colle le texte à Claude.")
        except Exception as error:  # noqa: BLE001
            print(f"  ! extraction impossible ({error}). Claude pourra lire le fichier directement.")
    else:
        print(f"  aucun CV importé. Dépose-le dans {importdir} puis relance l'init.")

    # --- photo -------------------------------------------------------------
    photo = None
    if args.photo:
        target = workspace / ("photo" + args.photo.suffix.lower())
        shutil.copy2(args.photo.expanduser(), target)
        photo = target.name
    else:
        found = [p for p in workspace.iterdir() if p.stem.lower() == "photo" and p.suffix.lower() in PHOTO_FORMATS]
        photo = found[0].name if found else None
    print(f"  photo : {photo or 'aucune (CV sans photo)'}")

    # --- identité ------------------------------------------------------------
    # pdftotext met en général le nom sur la première ligne non vide
    first_line = next((l.strip() for l in extracted.splitlines() if l.strip()), "")
    name = args.name or ask("Nom complet", first_line[:40] or "Prénom Nom", interactive)
    title = args.title or ask("Intitulé de poste visé (vide : Claude le déduira)", "", interactive)
    contact = args.contact or ask("Ligne de contact, email · téléphone · ville (vide : plus tard)", "", interactive)
    signature = args.signature or ask("Signature des lettres (vide : nom seul)", "", interactive)

    master = workspace / "cv-master.md"
    if master.exists() and "<!-- TEMPLATE" not in master.read_text(encoding="utf-8"):
        print("  cv-master.md déjà rempli, conservé")
    else:
        template = (ASSETS / "cv-master.template.md").read_text(encoding="utf-8")
        master.write_text(set_front_matter(template, {
            "name": name, "title": title, "contact": contact, "photo": photo,
        }), encoding="utf-8")
        print("  cv-master.md créé (squelette, à remplir avec Claude)")

    profil = workspace / "profil.md"
    if profil.exists():
        print("  profil.md existe déjà, conservé")
    else:
        text = (ASSETS / "profil.template.md").read_text(encoding="utf-8")
        if signature:
            text = re.sub(r"\*\*Signature des lettres\*\* :.*?(?=\n\*\*)",
                          f"**Signature des lettres** : {signature}", text, flags=re.S)
        profil.write_text(text, encoding="utf-8")
        print("  profil.md créé")

    CONFIG.write_text(json.dumps({"workspace": str(workspace)}, indent=2, ensure_ascii=False) + "\n")
    print(f"  config : {CONFIG}")

    check_dependencies()
    print(f"""
Étape suivante : lance Claude Code dans {workspace} et écris
  « construis mon cv-master à partir de mon CV importé »
  (ou « aide-moi à remplir mon CV master » si aucun CV n'a été importé)
Claude remplira le master, posera des questions sur ce qui manque, puis
complètera profil.md avec toi.""")


if __name__ == "__main__":
    main()
