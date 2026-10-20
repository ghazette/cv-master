#!/usr/bin/env python3
"""Premier lancement du skill jobsearch : crée les dossiers et fichiers de l'utilisateur.

    python3 ~/.claude/skills/jobsearch/scripts/init.py            # crée ce qui manque, n'écrase rien
    python3 ~/.claude/skills/jobsearch/scripts/init.py --check    # config encore vierge ? quoi remplir ?
    python3 ~/.claude/skills/jobsearch/scripts/init.py --geocode  # complète lat/lon/INSEE… des lieux de config.json

Crée, seulement s'ils n'existent pas :
- ~/Documents/jobsearch/{review,offres,candidatures}/
- ~/Documents/jobsearch/config.json et profile.json (copies des modèles neutres de assets/)
- ~/.config/jobsearch/.env (chmod 600) : noms des variables des sources à clé, valeurs vides

Idempotent : relancé, il ne touche à aucun fichier existant et redit ce qui reste à faire.
Bibliothèque standard seulement (fonctionne avant toute installation).
Code retour de --check : 0 prêt, 1 encore à remplir.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (CV_MASTER, DATA_DIR, ENV_FILE, INIT_CMD, TEMPLATE_CONFIG, TEMPLATE_PROFILE,  # noqa: E402
                    complete_places, config_gaps, normalize_config, profile_gaps, tilde)

# Sources à clé : (variables, plateforme, lien d'inscription, note). Toutes optionnelles.
KEYS = [
    (["FRANCETRAVAIL_CLIENT_ID", "FRANCETRAVAIL_CLIENT_SECRET"], "France Travail (API Offres d'emploi v2)",
     "https://francetravail.io/data/api/offres-emploi",
     "créer une application, l'abonner à « API Offres d'emploi v2 », copier identifiant et clé secrète"),
    (["ADZUNA_APP_ID", "ADZUNA_APP_KEY"], "Adzuna", "https://developer.adzuna.com/signup",
     "gratuit, 250 appels/jour"),
    (["SERPAPI_KEY"], "Google Jobs via SerpApi", "https://serpapi.com/users/sign_up",
     "gratuit, 250 recherches/mois"),
    (["JOOBLE_API_KEY"], "Jooble", "https://jooble.org/api/about",
     "500 requêtes au total pour une clé gratuite ; parfois bloqué par Cloudflare"),
    (["CAREERJET_API_KEY"], "Careerjet", "https://www.careerjet.com/partners/register/as-publisher",
     "compte éditeur ; CAREERJET_USER_IP et CAREERJET_REFERER optionnels"),
]
OPTIONAL_VARS = ["CAREERJET_USER_IP", "CAREERJET_REFERER"]
DIRS = ("review", "offres", "candidatures")
CV_PLACEHOLDERS = ("<!-- TEMPLATE", "À REMPLIR", "A REMPLIR", "TODO", "{{", "[Prénom", "[Nom", "Lorem ipsum")


def env_template() -> str:
    lines = [
        "# Clés API des sources optionnelles du skill jobsearch.",
        "# Remplis seulement celles que tu veux : une source sans clé est sautée proprement.",
        "# Ne colle jamais une clé dans le chat ; édite ce fichier toi-même (chmod 600).",
        "# Vérification (noms seulement, jamais les valeurs) : run.py --list ou init.py --check.",
        "",
    ]
    for names, label, url, note in KEYS:
        lines.append(f"# {label} : {url} ({note})")
        lines += [f"{n}=" for n in names]
        if names == ["CAREERJET_API_KEY"]:
            lines += [f"# {n}=" for n in OPTIONAL_VARS]
        lines.append("")
    return "\n".join(lines)


def declared_keys(path: Path = ENV_FILE) -> set[str]:
    """Noms des variables qui ont une valeur dans .env (les valeurs ne sont jamais affichées)."""
    filled = set()
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip().strip('"').strip("'"):
                    filled.add(k.strip())
    return filled


def create() -> list[str]:
    done = []
    for d in DIRS:
        path = DATA_DIR / d
        if not path.exists():
            path.mkdir(parents=True)
            done.append(f"créé    {tilde(path)}/")
    for template, name in ((TEMPLATE_CONFIG, "config.json"), (TEMPLATE_PROFILE, "profile.json")):
        path = DATA_DIR / name
        if path.exists():
            done.append(f"gardé   {tilde(path)} (déjà présent)")
        else:
            shutil.copyfile(template, path)
            done.append(f"créé    {tilde(path)} (modèle vierge)")
    if ENV_FILE.exists():
        done.append(f"gardé   {tilde(ENV_FILE)} (déjà présent)")
    else:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(env_template())
        os.chmod(ENV_FILE, 0o600)
        done.append(f"créé    {tilde(ENV_FILE)} (chmod 600, variables vides)")
    return done


def cv_state() -> tuple[bool, str]:
    if not CV_MASTER.exists():
        return False, f"{tilde(CV_MASTER)} absent : passe d'abord par le skill cv (premier lancement)"
    text = CV_MASTER.read_text(errors="replace")
    filled_lines = [x for x in text.splitlines() if x.strip() and not x.lstrip().startswith(("<!--", "#"))]
    marker = next((m for m in CV_PLACEHOLDERS if m.lower() in text.lower()), None)
    if len(filled_lines) < 15 or marker:
        why = f"contient encore « {marker} »" if marker else "presque vide"
        return False, f"{tilde(CV_MASTER)} {why} : termine-le avec le skill cv avant de dériver profile.json"
    return True, f"{tilde(CV_MASTER)} présent ({len(filled_lines)} lignes de contenu)"


def check() -> int:
    ready = True
    print("## État de la veille emploi\n")
    path = DATA_DIR / "config.json"
    if not path.exists():
        print(f"- config.json absent : lance `{INIT_CMD}`")
        ready = False
    else:
        try:
            cfg = normalize_config(json.loads(path.read_text()))
            blocking, advice = config_gaps(cfg)
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            print(f"- config.json illisible : {exc}")
            blocking, advice, ready = [], [], False
        if blocking:
            ready = False
            print("- config.json **vierge ou incomplète**, à remplir (onboarding) :")
            print("\n".join(f"  - {g}" for g in blocking))
        elif ready:
            print("- config.json : remplie")
        for a in advice:
            print(f"  - conseil : {a}")
    path = DATA_DIR / "profile.json"
    if not path.exists():
        print(f"- profile.json absent : lance `{INIT_CMD}`")
        ready = False
    else:
        try:
            gaps = profile_gaps(json.loads(path.read_text()))
        except json.JSONDecodeError as exc:
            gaps = [f"JSON illisible ({exc})"]
        if gaps:
            ready = False
            print("- profile.json **vierge**, à dériver du CV maître :")
            print("\n".join(f"  - {g}" for g in gaps))
        else:
            print("- profile.json : rempli")
    ok, msg = cv_state()
    print(f"- CV maître : {msg}")
    ready = ready and ok

    print("\n## Clés API (optionnelles)\n")
    if not ENV_FILE.exists():
        print(f"- {tilde(ENV_FILE)} absent : lance `{INIT_CMD}`")
    filled = declared_keys()
    for names, label, url, note in KEYS:
        state = "présente" if all(n in filled for n in names) else "absente (source sautée)"
        print(f"- {label} : {state} · {', '.join(names)} · {url}")

    print("\n## Outils\n")
    has_requests = importlib.util.find_spec("requests") is not None
    print(f"- python3 {sys.version.split()[0]} · requests : {'ok' if has_requests else 'ABSENT (pip install requests, ou passer par uv run)'}")
    print(f"- uv : {'ok' if shutil.which('uv') else 'absent (LinkedIn/Indeed via python-jobspy indisponibles ; voir references/onboarding.md)'}")
    print(f"\n{'Prêt : lance la collecte (SKILL.md, « Lancer une recherche »).' if ready else 'Pas encore prêt : suis references/onboarding.md.'}")
    return 0 if ready else 1


def geocode() -> int:
    path = DATA_DIR / "config.json"
    if not path.exists():
        print(f"config.json absent : lance d'abord `{INIT_CMD}`", file=sys.stderr)
        return 2
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"config.json illisible : {exc}", file=sys.stderr)
        return 2
    report = complete_places(cfg)
    if not report:
        print("Rien à compléter : chaque lieu a déjà ses coordonnées (ou aucun lieu n'a de champ city).")
        return 0
    print("\n".join(report))
    if any("complétés" in line for line in report):
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        print(f"→ {tilde(path)} mis à jour (seuls des champs vides ont été remplis).")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="dit si la config est encore vierge et quoi remplir")
    ap.add_argument("--geocode", action="store_true", help="complète les coordonnées des lieux de config.json")
    args = ap.parse_args()
    if args.check:
        sys.exit(check())
    if args.geocode:
        sys.exit(geocode())
    for line in create():
        print(line)
    print("\nReste à faire (détail : references/onboarding.md) :")
    print(f"  1. CV maître {tilde(CV_MASTER)} rempli (skill cv, premier lancement) ;")
    print("  2. entretien court, puis remplir config.json (domicile, zone, remote, contrats, métiers, salaire) ;")
    print(f"  3. `{INIT_CMD} --geocode` pour les coordonnées des lieux ;")
    print("  4. dériver profile.json du CV maître ;")
    print(f"  5. clés API optionnelles : l'utilisateur édite lui-même {tilde(ENV_FILE)} ;")
    print(f"  6. `{INIT_CMD} --check`, puis première collecte avec run.py.")


if __name__ == "__main__":
    main()
