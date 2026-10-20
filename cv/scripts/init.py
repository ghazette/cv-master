#!/usr/bin/env python3
"""Initialise le skill cv : crée le workspace, importe le CV existant, écrit la config.

    python3 init.py                                   # interactif
    python3 init.py --cv ~/Téléchargements/mon-cv.pdf
    python3 init.py --cv Basic_LinkedInDataExport.zip  # archive de données LinkedIn
    python3 init.py --cv scan.pdf --ocr                # CV scanné, tesseract requis
    python3 init.py --yes --workspace ~/Documents/cv --cv mon-cv.docx --name "Camille Martin"

Le CV d'origine (pdf, docx, odt, doc, rtf, txt, md, archive ou dossier
d'export LinkedIn) peut être :
  - passé avec --cv, il est alors copié dans <workspace>/import/ (un dossier
    LinkedIn est lu sur place, pas copié),
  - ou déposé à la main dans <workspace>/import/ avant de lancer l'init.
Son texte est extrait par extract_cv.py dans <workspace>/import/cv-extrait.txt,
que Claude lit pour construire cv-master.md. La photo éventuelle se pose dans
<workspace>/ sous le nom photo.jpg ou photo.png (ou via --photo).

Les templates sont déposés avec leur marqueur « <!-- TEMPLATE » en première
ligne : il déclenche l'onboarding et bloque le rendu tant que le master n'est
pas rempli. Relancer l'init ne réécrit jamais profil.md, ni un cv-master.md
rempli ou en cours de remplissage : seul un squelette intact est régénéré.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from extract_cv import ExtractError, extract, looks_scanned

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
CONFIG = SKILL_DIR / "config.json"
TEMPLATE_MARK = "<!-- TEMPLATE"
EXTRACT = "cv-extrait.txt"
CV_FORMATS = {".pdf", ".docx", ".odt", ".doc", ".rtf", ".txt", ".md", ".zip"}
PHOTO_FORMATS = {".jpg", ".jpeg", ".png"}


def ask(question: str, default: str, interactive: bool) -> str:
    if not interactive:
        return default
    answer = input(f"{question} [{default}] : ").strip()
    return answer or default


def is_template(path: Path) -> bool:
    """Même test que build_cv.py : le marqueur en première ligne."""
    return path.read_text(encoding="utf-8").lstrip().startswith(TEMPLATE_MARK)


# marqueur TEMPLATE éventuel, puis front matter « --- ... --- », puis corps
FRONT_MATTER = re.compile(r"\A(\s*(?:<!--[^\n]*-->\n)?---\n)(.*?)(\n---\n)(.*)\Z", re.S)


def body_of(text: str) -> str:
    """Tout ce qui suit le front matter."""
    match = FRONT_MATTER.match(text)
    return match.group(4) if match else text


def front_matter(text: str) -> dict:
    match = FRONT_MATTER.match(text)
    pairs = (l.split(":", 1) for l in (match.group(2) if match else "").splitlines() if ":" in l)
    return {k.strip(): v.strip() for k, v in pairs}


def guess_name(text: str) -> str:
    """pdftotext met en général le nom sur la première ligne non vide."""
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    plausible = (first and len(first) <= 40 and len(first.split()) <= 5
                 and not re.search(r"[\d@#:/|]", first))
    return first if plausible else ""


def set_front_matter(text: str, values: dict) -> str:
    """Remplace les clés du front matter du template. None retire la ligne.

    Seul le bloc entre les deux `---` est touché : la ligne marqueur qui le
    précède et le corps qui le suit restent tels quels."""
    match = FRONT_MATTER.match(text)
    if not match:
        return text
    opening, head, closing, body = match.groups()
    for key, value in values.items():
        if value is None:
            head = re.sub(rf"^{key}:.*$\n?", "", head, flags=re.M)
        elif value:
            head = re.sub(rf"^{key}:.*$", lambda _: f"{key}: {value}", head, flags=re.M)
    return opening + head.rstrip("\n") + closing + body


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
    parser.add_argument("--cv", type=Path, help="CV existant à importer (fichier, .zip ou dossier LinkedIn)")
    parser.add_argument("--ocr", action="store_true", help="CV scanné : passe par tesseract")
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
    source = None
    if cv_path:
        cv_path = cv_path.expanduser()
        if cv_path.is_dir():
            source = cv_path  # export LinkedIn décompressé : lu sur place
        elif cv_path.is_file():
            source = importdir / cv_path.name
            if cv_path.resolve() != source.resolve():
                shutil.copy2(cv_path, source)
            print(f"  CV copié dans {source}")
        else:
            sys.exit(f"introuvable : {cv_path}")
    else:
        sources = [p for p in importdir.iterdir()
                   if p.is_file() and p.suffix.lower() in CV_FORMATS and p.name != EXTRACT]
        source = max(sources, key=lambda p: p.stat().st_mtime) if sources else None

    extracted = ""
    if source:
        try:
            extracted = extract(source, use_ocr=args.ocr)
            (importdir / EXTRACT).write_text(extracted.strip() + "\n", encoding="utf-8")
            print(f"  texte extrait de {source.name} : {len(extracted.split())} mots, dans {importdir / EXTRACT}")
            if looks_scanned(source, extracted, args.ocr):
                print("  ! très peu de texte : PDF scanné ou image ? Relance avec --ocr, "
                      "fournis un .docx, ou colle le texte à Claude.")
        except (ExtractError, OSError, ValueError) as error:
            print(f"  ! extraction impossible ({error}). Claude pourra lire le fichier directement.")
    elif (importdir / EXTRACT).is_file():
        extracted = (importdir / EXTRACT).read_text(encoding="utf-8")
        print(f"  extrait existant conservé : {importdir / EXTRACT}")
    else:
        print(f"  aucun CV importé. Dépose-le dans {importdir} puis relance l'init, "
              "ou laisse Claude te guider pour partir de zéro.")

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
    # un squelette déjà généré garde ses valeurs si on relance sans les préciser
    master = workspace / "cv-master.md"
    template = (ASSETS / "cv-master.template.md").read_text(encoding="utf-8")
    placeholder = front_matter(template)
    known = {k: v for k, v in front_matter(master.read_text(encoding="utf-8")).items()
             if v != placeholder.get(k)} if master.is_file() else {}
    name = args.name or ask("Nom complet", known.get("name") or guess_name(extracted) or "Prénom Nom", interactive)
    title = args.title or ask("Intitulé de poste visé (vide : Claude le déduira)", known.get("title", ""), interactive)
    contact = args.contact or ask("Ligne de contact, email · téléphone · ville (vide : plus tard)",
                                  known.get("contact", ""), interactive)
    signature = args.signature or ask("Signature des lettres (vide : nom seul)", "", interactive)

    if master.exists() and not is_template(master):
        print("  cv-master.md déjà rempli, conservé")
    elif master.exists() and body_of(master.read_text(encoding="utf-8")) != body_of(template):
        # marqueur présent mais corps modifié : onboarding en cours, rien n'est écrasé
        print("  cv-master.md en cours de remplissage (marqueur TEMPLATE), conservé")
    else:
        master.write_text(set_front_matter(template, {
            "name": name, "title": title, "contact": contact, "photo": photo,
        }), encoding="utf-8")
        print("  cv-master.md créé (squelette marqué TEMPLATE, à remplir avec Claude)")

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
