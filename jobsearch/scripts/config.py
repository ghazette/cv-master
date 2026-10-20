"""Config et profil de l'utilisateur : chemins, chargement, valeurs par défaut, contrôle « vierge ».

Tout ce qui est propre à l'utilisateur vit dans DATA_DIR (par défaut ~/Documents/jobsearch) :
- config.json  : domicile, zone acceptée pour le présentiel, politique remote, lieux et
                 requêtes de recherche, contrats, salaire, entreprises suivies ;
- profile.json : poids du pré-score, dérivés du CV maître.
Les modèles neutres sont dans assets/ ; `init.py` les copie au premier lancement.

Module sans dépendance externe (bibliothèque standard seulement) : init.py l'utilise
avant que `requests` ou `uv` soient installés.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JOBSEARCH_DIR", Path.home() / "Documents" / "jobsearch"))
ENV_FILE = Path(os.environ.get("JOBSEARCH_ENV", Path.home() / ".config" / "jobsearch" / ".env"))
CV_MASTER = Path(os.environ.get("JOBSEARCH_CV_MASTER", Path.home() / "Documents" / "cv" / "cv-master.md"))
TEMPLATE_CONFIG = SKILL_DIR / "assets" / "config.default.json"
TEMPLATE_PROFILE = SKILL_DIR / "assets" / "profile.default.json"


def tilde(path: Path | str) -> str:
    """Chemin affichable, avec ~ à la place du dossier personnel."""
    s, home = str(path), str(Path.home())
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


INIT_CMD = f"python3 {tilde(SKILL_DIR / 'scripts' / 'init.py')}"


def norm(text: str) -> str:
    """Minuscules sans accents : les motifs restent lisibles et tolèrent « télétravail » / « teletravail »."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


# --- valeurs par défaut -------------------------------------------------------------

# Clés absentes d'un config.json (ancien ou incomplet) : complétées en mémoire, jamais écrites.
DEFAULTS: dict[str, Any] = {
    "home": {"city": "", "postcode": "", "lat": None, "lon": None},
    "onsite": {"max_days_on_site": 5, "zone": [], "zone_departments": [], "zone_postcodes": [],
               "zone_patterns": []},
    "remote": {"accepted": True, "countries": ["FR"],
               "scope_patterns": [r"\bfran(ce|cia)\b", r"\bfrench\b", r"\bfr\b"]},
    "search_areas": [],
    "queries": {"fr": [], "en": []},
    "prefilter": {"title": [], "title_exclude": [], "stack": [], "stack_text": []},
    "contracts_allowed": ["cdi", "unknown"],
    "salary_target": {"year": None, "day": None, "min_year": None, "min_day": None},
    "esn_ok": True,
    "scrape": True,
    "max_age_days": 30,
    "per_query": 50,
    "llm_review_top": 30,
    "ats_companies": {},
    "sources_disabled": [],
}

# Rayon par défaut d'un lieu de recherche, et rayon minimal quand on le déduit de la zone :
# les plateformes géolocalisent mal, on cherche large et le filtre tranche ensuite.
AREA_RADIUS_KM = 30
AREA_MIN_RADIUS_KM = 20
ZONE_RADIUS_KM = 10


def _fill(cfg: dict[str, Any], defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        if key not in cfg or cfg[key] is None:
            cfg[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(cfg[key], dict):
            _fill(cfg[key], value)


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Complète les clés manquantes et lit l'ancien format (zone et remote_scope à la racine)."""
    cfg = dict(cfg)
    if "zone" in cfg and "onsite" not in cfg:            # ancien format : zone = liste de cercles
        cfg["onsite"] = {"zone": cfg.pop("zone")}
    if "remote_scope" in cfg and "remote" not in cfg:    # ancien format : "FR"
        scope = cfg.pop("remote_scope")
        cfg["remote"] = {"countries": [scope] if isinstance(scope, str) else list(scope)}
    home = cfg.get("home") or {}
    if home.get("commune") and not home.get("city"):     # ancien format : « Commune (12345) »
        m = re.search(r"\((\d{5})\)", home["commune"])
        home = {**home, "city": re.sub(r"\s*\(.*?\)", "", home["commune"]).strip(),
                "postcode": home.get("postcode") or (m.group(1) if m else "")}
        cfg["home"] = home
    _fill(cfg, DEFAULTS)
    return cfg


# --- chargement -------------------------------------------------------------------

def _exit(msg: str) -> None:
    """Message clair au lieu d'une trace Python (code 2 = installation incomplète)."""
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def read_json(path: Path, what: str) -> dict[str, Any]:
    if not path.exists():
        _exit(f"{what} introuvable : {tilde(path)}\n"
              f"Premier lancement ? Lance `{INIT_CMD}`, puis l'onboarding "
              "(SKILL.md, section « Premier lancement »).")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        _exit(f"{what} illisible ({tilde(path)}, ligne {exc.lineno}, colonne {exc.colno}) : {exc.msg}.\n"
              "Corrige le JSON (virgule en trop, guillemet manquant…) puis relance.")
    if not isinstance(data, dict):
        _exit(f"{what} invalide ({tilde(path)}) : un objet JSON {{…}} est attendu.")
    return data


def config_gaps(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(manques bloquants, conseils) d'une config normalisée. Bloquant = la collecte n'a pas de sens."""
    blocking, advice = [], []
    home, onsite, remote = cfg["home"], cfg["onsite"], cfg["remote"]
    queries = cfg.get("queries") or {}
    if not (home.get("city") or "").strip():
        blocking.append("home.city : commune de domicile")
    if not (queries.get("fr") or queries.get("en")):
        blocking.append("queries.fr (et/ou queries.en) : intitulés de poste à chercher")
    if not cfg.get("contracts_allowed"):
        blocking.append("contracts_allowed : contrats acceptés (cdi, freelance, cdd…)")
    has_zone = any(onsite.get(k) for k in ("zone", "zone_departments", "zone_postcodes", "zone_patterns"))
    onsite_ok = int(onsite.get("max_days_on_site", 5)) > 0
    if not remote.get("accepted", True) and not (has_zone and onsite_ok):
        blocking.append("onsite.zone vide (ou max_days_on_site = 0) et remote.accepted = false : "
                        "aucune offre ne peut passer le filtre")
    elif onsite_ok and not has_zone:
        advice.append("onsite.zone vide : seules les offres full remote passeront le filtre")
    if remote.get("accepted", True) and not (remote.get("countries") or remote.get("scope_patterns")):
        blocking.append("remote.countries : pays depuis lesquels le remote doit être ouvert (ex. FR)")
    missing_geo = [z.get("name") or z.get("city") or "?" for z in onsite.get("zone", [])
                   if z.get("lat") is None or z.get("lon") is None]
    missing_geo += [a.get("name") or a.get("city") or "?" for a in cfg.get("search_areas", [])
                    if a.get("lat") is None or a.get("lon") is None]
    if missing_geo:
        advice.append(f"coordonnées manquantes ({', '.join(missing_geo)}) : lance `{INIT_CMD} --geocode`")
    if onsite_ok and has_zone and not search_areas(cfg):
        advice.append("search_areas vide et zone sans cercle : aucune recherche géographique, "
                      "seulement les recherches remote")
    sal = cfg.get("salary_target") or {}
    if not (sal.get("year") or sal.get("day")):
        advice.append("salary_target vide : pas de bonus salaire au pré-score")
    return blocking, advice


def load_config(require_ready: bool = False) -> dict[str, Any]:
    """Config normalisée. Absente → message « lance init ». `require_ready` : vierge → message « onboarding »."""
    cfg = normalize_config(read_json(DATA_DIR / "config.json", "config.json"))
    if require_ready:
        blocking, _ = config_gaps(cfg)
        if blocking:
            _exit("config.json est encore vierge ou incomplète :\n"
                  + "\n".join(f"  - {g}" for g in blocking)
                  + f"\nFais l'onboarding (SKILL.md, « Premier lancement ») ou `{INIT_CMD} --check`.")
    return cfg


def profile_gaps(profile: dict[str, Any]) -> list[str]:
    gaps = []
    if not profile.get("roles"):
        gaps.append("roles : métiers visés et motifs de titre")
    if not profile.get("skills"):
        gaps.append("skills : compétences du CV et leurs poids")
    return gaps


def load_profile(require_ready: bool = False) -> dict[str, Any]:
    profile = read_json(DATA_DIR / "profile.json", "profile.json")
    profile.setdefault("roles", [])
    profile.setdefault("skills", [])
    profile.setdefault("penalties", [])
    if require_ready:
        gaps = profile_gaps(profile)
        if gaps:
            _exit("profile.json est encore vierge :\n" + "\n".join(f"  - {g}" for g in gaps)
                  + f"\nDérive-le de {tilde(CV_MASTER)} (references/onboarding.md, étape 5).")
    return profile


def warn_if_blank() -> None:
    """Pour les commandes de consultation (top, rapport, récap) : avertit sans bloquer."""
    path = DATA_DIR / "config.json"
    if not path.exists():
        print(f"(config absente : lance `{INIT_CMD}` puis l'onboarding pour démarrer la veille)", file=sys.stderr)
        return
    try:
        blocking, _ = config_gaps(normalize_config(json.loads(path.read_text())))
    except (json.JSONDecodeError, TypeError, AttributeError, ValueError):
        print("(config.json illisible : corrige le JSON)", file=sys.stderr)
        return
    if blocking:
        print("(config encore vierge : fais l'onboarding, SKILL.md « Premier lancement »)", file=sys.stderr)


# --- lieux --------------------------------------------------------------------------

def search_areas(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Lieux autour desquels chercher les offres sur site ou hybrides.

    `search_areas` explicite si présent ; sinon déduit des cercles de `onsite.zone`
    (rayon élargi à AREA_MIN_RADIUS_KM). Vide si l'utilisateur refuse tout présentiel.
    """
    onsite = cfg.get("onsite") or {}
    if int(onsite.get("max_days_on_site", 5)) <= 0:
        return []
    raw = cfg.get("search_areas") or []
    derived = not raw
    if derived:
        raw = [z for z in onsite.get("zone", []) if z.get("city") or z.get("name")]
    out = []
    for a in raw:
        city = (a.get("city") or a.get("name") or "").strip()
        if not city:
            continue
        radius = a.get("radius_km") or (ZONE_RADIUS_KM if derived else AREA_RADIUS_KM)
        out.append({**a, "name": a.get("name") or city, "city": city,
                    "radius_km": max(radius, AREA_MIN_RADIUS_KM) if derived else radius})
    return out


GEO_API = "https://geo.api.gouv.fr/communes"


def commune_lookup(city: str, postcode: str = "") -> dict[str, Any] | None:
    """Commune française → {city, insee, postcode, department, region, lat, lon} (geo.api.gouv.fr, sans clé)."""
    params = {"fields": "nom,code,codesPostaux,centre,codeDepartement,region", "boost": "population", "limit": 1}
    if city:
        params["nom"] = city
    if postcode:
        params["codePostal"] = postcode
    url = f"{GEO_API}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "jobsearch-skill"}),
                                    timeout=15) as resp:
            hits = json.loads(resp.read().decode())
    except (OSError, ValueError):
        return None
    if not hits:
        return None
    h = hits[0]
    lon, lat = (h.get("centre") or {}).get("coordinates", [None, None])
    cps = h.get("codesPostaux") or []
    return {"city": h.get("nom", city), "insee": h.get("code", ""),
            "postcode": postcode if postcode in cps else (cps[0] if cps else ""),
            "department": h.get("codeDepartement", ""), "region": (h.get("region") or {}).get("nom", ""),
            "lat": lat, "lon": lon}


_GEO_FIELDS = ("lat", "lon", "postcode", "insee", "department", "region")


def complete_places(cfg: dict[str, Any], lookup=commune_lookup) -> list[str]:
    """Complète en place les champs géographiques manquants (domicile, zone, lieux de recherche).
    Renvoie un compte rendu ligne par ligne. Ne touche jamais une valeur déjà remplie."""
    report: list[str] = []
    entries: list[tuple[str, dict[str, Any], tuple[str, ...]]] = []
    if isinstance(cfg.get("home"), dict):
        entries.append(("domicile", cfg["home"], ("lat", "lon", "postcode", "department")))
    for z in (cfg.get("onsite") or {}).get("zone", []):
        entries.append(("zone", z, ("lat", "lon")))
    for a in cfg.get("search_areas") or []:
        entries.append(("recherche", a, _GEO_FIELDS))
    for kind, entry, wanted in entries:
        city = (entry.get("city") or "").strip()
        if not city or all(entry.get(k) not in (None, "") for k in wanted):
            continue
        hit = lookup(city, entry.get("postcode") or "")
        if not hit:
            report.append(f"{kind} « {city} » : commune introuvable (ou réseau indisponible), "
                          "vérifier l'orthographe ou compléter lat/lon à la main")
            continue
        filled = []
        for k in wanted:
            if entry.get(k) in (None, "") and hit.get(k) not in (None, ""):
                entry[k] = hit[k]
                filled.append(k)
        if kind == "zone" and not entry.get("radius_km"):
            entry["radius_km"] = ZONE_RADIUS_KM
            filled.append("radius_km")
        if filled:
            report.append(f"{kind} « {city} » : {', '.join(filled)} complétés ({hit['city']}, {hit['department']})")
    return report
