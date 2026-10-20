"""Filtres durs : contrat, fraîcheur, zone géographique, jours sur site et remote.

La règle se lit dans config.json (clés `onsite` et `remote`) et tient en une phrase :
présentiel ou hybride seulement dans la zone acceptée par l'utilisateur (et pas plus de
`onsite.max_days_on_site` jours sur site par semaine) ; ailleurs, full remote ouvert depuis
un pays de `remote.countries`, sinon l'offre sort. Tout le reste (pertinence, salaire)
relève du score, pas du filtre.

Verdicts :
- ok       : l'offre respecte la règle
- douteux  : remote ou rythme ambigu (« remote first », « télétravail possible »),
             à confirmer à la lecture ; jamais classé avec les offres sûres
- exclu    : incompatible, on garde la raison pour pouvoir auditer le filtre
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable

import requests

from common import Job, age_days
from config import norm  # noqa: F401  (réexporté : db.py, jobs.py, recap.py l'importent d'ici)


# --- remote -----------------------------------------------------------------

_FULL = [
    r"full[\s-]?remote", r"fully[\s-]remote", r"100\s?%\s*(en\s+)?(remote|teletravail|a distance)",
    r"teletravail\s+(total|complet|integral|a 100)", r"remote\s+(total|complet|integral)",
    r"entierement\s+(en\s+)?(remote|teletravail|a distance)",
    r"\b5\s*(j|jours)\s*(/\s*5\s*)?(de\s+|en\s+)?(teletravail|remote)",
    r"remote\s*:\s*(total|full|100)", r"poste\s+(100\s?%\s+)?(en\s+)?(full\s+)?remote\b(?!\s+partiel)",
]
_NONE = [
    r"pas\s+de\s+teletravail", r"100\s?%\s*(en\s+)?presentiel", r"sur\s+site\s+uniquement",
    r"\bno\s+remote\b", r"on[\s-]?site\s+only", r"teletravail\s+non\s+(possible|autorise)",
]
_PARTIAL = [
    r"\bhybride?\b", r"\bhybrid\b", r"teletravail\s+partiel", r"remote\s+partiel",
    r"\b[1-4]\s*(j|jours?)\s*(/\s*(semaine|sem))?\s*(de\s+|en\s+)?(teletravail|remote)",
    r"(teletravail|remote)\s*[:\-]?\s*[1-4]\s*(j|jours?)\b", r"flex\s?office",
]
_UNCLEAR = [
    r"remote[\s-]first", r"teletravail\s+(possible|flexible|a la carte|illimite|libre)",
    r"remote\s+(possible|friendly|flexible)", r"\bremote\b",
]
_RX = {k: [re.compile(p) for p in v] for k, v in
       {"full": _FULL, "none": _NONE, "partial": _PARTIAL, "unclear": _UNCLEAR}.items()}


def _first_match(kind: str, text: str) -> str | None:
    for rx in _RX[kind]:
        m = rx.search(text)
        if m:
            start = max(0, m.start() - 40)
            return text[start:m.end() + 40].replace("\n", " ").strip()
    return None


def detect_remote(job: Job) -> tuple[str, str]:
    """Renvoie (full|partial|none|unclear|unknown, extrait justificatif).

    Un champ structuré de la source l'emporte : il a été saisi par le recruteur.
    Sinon on lit le texte, du signal le plus fort au plus faible ; « none » passe
    avant « full » parce qu'une annonce qui dit « pas de télétravail » est formelle.
    """
    if job.remote in ("full", "partial", "none"):
        return job.remote, f"champ source : {job.remote}"
    text = norm(f"{job.title}\n{job.location}\n{job.description}")
    for kind in ("none", "full", "partial", "unclear"):
        ev = _first_match(kind, text)
        if ev:
            return kind, ev
    return "unknown", ""


# --- contrat ----------------------------------------------------------------

def detect_contract(job: Job) -> str:
    if job.contract != "unknown":
        return job.contract
    title, desc = norm(job.title), norm(job.description[:8000])
    # le titre est fiable ; la description cite souvent « stage » ou « CDD » hors contexte
    for kind, rx in (("stage", r"\b(stage|stagiaire|intern(ship)?)\b"),
                     ("alternance", r"\b(alternance|alternant|apprenti(ssage)?)\b"),
                     ("interim", r"\binterim\b"),
                     ("cdd", r"\bcdd\b"),
                     ("freelance", r"\b(freelance|free-lance|portage|independant|tjm)\b"),
                     ("cdi", r"\bcdi\b")):
        if re.search(rx, title):
            return kind
    if re.search(r"\bcdi\b", desc):
        return "cdi"
    if re.search(r"\b(freelance|portage salarial|tjm|taux journalier)\b", desc):
        return "freelance"
    if re.search(r"\bcdd\b", desc):
        return "cdd"
    return "unknown"




# --- jours sur site -------------------------------------------------------------

_DAYS_REMOTE = [
    re.compile(r"\b([0-5])\s*(?:j|jours?|days?)\s*(?:/\s*(?:semaine|sem|week|wk)|par semaine|per week|a week)?\s*"
               r"(?:de\s+|en\s+|of\s+)?(?:teletravail|remote|home office|wfh)"),
    re.compile(r"(?:teletravail|remote)\s*[:\-]?\s*([0-5])\s*(?:j|jours?|days?)\b"),
]
_DAYS_ONSITE = [
    re.compile(r"\b([0-5])\s*(?:j|jours?|days?)\s*(?:/\s*(?:semaine|sem|week|wk)|par semaine|per week|a week)?\s*"
               r"(?:sur site|en presentiel|de presentiel|au bureau|in (?:the )?office|on[\s-]?site|at the office)"),
    re.compile(r"(?:presentiel|sur site|on[\s-]?site|in[\s-]?office)\s*[:\-]?\s*([0-5])\s*(?:j|jours?|days?)\b"),
]


def onsite_days(job: Job, remote: str) -> int | None:
    """Jours sur site par semaine annoncés : 5 pour du présentiel, 0 pour du full remote,
    sinon lus dans le texte (« 2 jours de télétravail » → 3) ; None si rien d'explicite."""
    if remote == "full":
        return 0
    if remote == "none":
        return 5
    text = norm(f"{job.title}\n{job.description}")
    for rx in _DAYS_ONSITE:
        m = rx.search(text)
        if m:
            return int(m.group(1))
    for rx in _DAYS_REMOTE:
        m = rx.search(text)
        if m:
            return 5 - int(m.group(1))
    return None


# --- géographie ---------------------------------------------------------------

_REGIONS = (r"auvergne[- ]rhone[- ]alpes|bourgogne[- ]franche[- ]comte|bretagne|centre[- ]val[- ]de[- ]loire|"
            r"corse|grand[- ]est|hauts[- ]de[- ]france|ile[- ]de[- ]france|normandie|nouvelle[- ]aquitaine|"
            r"occitanie|pays de la loire|provence[- ]alpes[- ]cote d'?azur|paca|guadeloupe|martinique|guyane|"
            r"la reunion|mayotte")
_NOT_A_PLACE = re.compile(
    rf"^(france|metropole|{_REGIONS}|europe|emea|"
    r"remote|teletravail|a distance|full remote|worldwide|anywhere|hybride?)$")
_FOREIGN = re.compile(
    r"\b(germany|allemagne|deutschland|spain|espagne|uk|united kingdom|london|usa|united states|"
    r"canada|belgique|belgium|suisse|switzerland|portugal|italy|italie|netherlands|pays-bas|"
    r"luxembourg|poland|pologne|romania|roumanie|morocco|maroc|tunisie|tunisia|india)\b")
# département dans un libellé : « 44 - NANTES » (France Travail), « Nantes - 44 » (APEC), « Nantes (44) »
_DEPT_IN_LABEL = [re.compile(r"^\s*(\d{2}|2[ab]|97\d)\s*-\s"), re.compile(r"\s-\s*(\d{2}|2[ab]|97\d)\s*$"),
                  re.compile(r"\((\d{2}|2[ab]|97\d)\)")]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def in_zone(coords: tuple[float, float], zone: list[dict]) -> str | None:
    for area in zone:
        if area.get("lat") is None or area.get("lon") is None:
            continue
        if haversine_km(coords, (area["lat"], area["lon"])) <= area.get("radius_km", 10):
            return area.get("name") or area.get("city") or "zone"
    return None


def department_of(postcode: str) -> str:
    """Code postal → département (« 44000 » → « 44 », « 97411 » → « 974 », Corse « 20xxx » → « 20 »)."""
    if not postcode:
        return ""
    return postcode[:3] if postcode.startswith("97") else postcode[:2]


def label_postcode(label: str) -> tuple[str, str]:
    """(code postal, département) lisibles directement dans un libellé de lieu, ou ("", "")."""
    raw = norm(label)
    m = re.search(r"\b(\d{5})\b", raw)
    if m:
        return m.group(1), department_of(m.group(1))
    for rx in _DEPT_IN_LABEL:
        m = rx.search(raw)
        if m:
            return "", m.group(1)
    return "", ""


def zone_match(onsite: dict[str, Any], coords: tuple[float, float] | None, postcode: str, dept: str,
               label: str) -> str | None:
    """Nom de la zone acceptée qui contient l'offre, ou None. Quatre façons de décrire la zone,
    cumulables : cercles (lat/lon/rayon), départements, préfixes de code postal, motifs regex."""
    if coords:
        hit = in_zone(coords, onsite.get("zone") or [])
        if hit:
            return hit
    dept = dept or department_of(postcode)
    for d in onsite.get("zone_departments") or []:
        d = str(d).lower()
        if dept and (dept == d or (dept == "20" and d in ("2a", "2b"))):
            return f"département {d.upper()}"
    for prefix in onsite.get("zone_postcodes") or []:
        if postcode and postcode.startswith(str(prefix)):
            return f"code postal {prefix}"
    text = norm(label)
    for pattern in onsite.get("zone_patterns") or []:
        if text and re.search(pattern, text):
            return f"lieu « {label.strip()[:40]} »"
    return None


class Geocoder:
    """Libellé de lieu → (lat, lon, code postal), via la Base Adresse Nationale (gratuite, sans clé).

    Le cache est injecté (table SQLite) pour ne jamais géocoder deux fois le même libellé.
    """

    URL = "https://api-adresse.data.gouv.fr/search/"

    def __init__(self, cache_get: Callable[[str], tuple | None], cache_put: Callable[[str, tuple | None], None],
                 http: requests.Session | None = None):
        self.get, self.put = cache_get, cache_put
        self.http = http or requests.Session()

    @staticmethod
    def clean(label: str) -> tuple[str, str] | None:
        """Extrait (commune, code postal) d'un libellé comme « 44 - NANTES 03 » ou « Nantes, Loire-Atlantique, France »."""
        raw = norm(label).strip()
        if not raw or _FOREIGN.search(raw):
            return None
        postcode = (re.search(r"\b(\d{5})\b", raw) or [None, ""])[1]
        s = re.sub(r"^\d{2,3}\s*-\s*", "", raw)                    # « 44 - nantes » (France Travail)
        s = re.split(r"[,;/|•]|\s-\s", s)[0]                        # « nantes, pays de la loire »
        s = re.sub(r"\(.*?\)|\b\d{5}\b", " ", s)
        s = re.sub(r"\b\d{1,2}\s*(e|er|eme)?\s*(arrondissement)?\b", " ", s)
        s = re.sub(r"\s+", " ", s).strip(" -")
        if not s or _NOT_A_PLACE.match(s):
            return None
        return s, postcode

    def locate(self, label: str) -> tuple[float, float, str] | None:
        cleaned = self.clean(label)
        if not cleaned:
            return None
        key = "|".join(cleaned)
        hit = self.get(key)
        if hit is not None:
            return hit if hit[0] is not None else None
        city, postcode = cleaned
        params = {"q": city, "type": "municipality", "limit": 1}
        if postcode:
            params["postcode"] = postcode
        found = None
        try:
            feats = self.http.get(self.URL, params=params, timeout=10).json().get("features", [])
            if feats:
                f = feats[0]
                name = re.sub(r"[^a-z]", "", norm(f["properties"].get("city") or f["properties"].get("name", "")))
                wanted = re.sub(r"[^a-z]", "", city)
                # garde-fou : la BAN trouve toujours « quelque chose », on exige que le nom corresponde
                if f["properties"].get("score", 0) >= 0.5 and name and (name in wanted or wanted in name):
                    lon, lat = f["geometry"]["coordinates"]
                    found = (lat, lon, f["properties"].get("postcode") or postcode or "")
        except (requests.RequestException, ValueError, KeyError):
            return None  # pas de cache sur erreur réseau : on retentera au prochain run
        self.put(key, found if found else (None, None, ""))
        return found


# --- verdict ------------------------------------------------------------------

def remote_open_to_user(job: Job, remote_cfg: dict[str, Any]) -> bool:
    """Le remote doit être ouvert depuis un pays de l'utilisateur (`remote.countries`) :
    une portée « Europe » ou « Worldwide » sans le pays ne suffit pas, sauf motif ajouté
    exprès dans `remote.scope_patterns`."""
    scope = norm(job.remote_scope)
    if scope:
        return any(re.search(p, scope) for p in remote_cfg.get("scope_patterns") or [])
    return bool(job.country) and job.country in (remote_cfg.get("countries") or [])


_COUNTRY_LABEL = {"FR": "France", "BE": "Belgique", "CH": "Suisse", "LU": "Luxembourg", "CA": "Canada"}


@dataclass
class Verdict:
    level: str            # ok | douteux | exclu
    reason: str
    zone: str | None
    remote: str
    remote_evidence: str
    contract: str


def evaluate(job: Job, cfg: dict, geo: Geocoder) -> Verdict:
    contract = detect_contract(job)
    remote, evidence = detect_remote(job)
    onsite, remote_cfg = cfg["onsite"], cfg["remote"]
    max_days = int(onsite.get("max_days_on_site", 5))
    countries = remote_cfg.get("countries") or ["FR"]
    where = ", ".join(_COUNTRY_LABEL.get(c, c) for c in countries)

    def verdict(level: str, reason: str, zone: str | None = None) -> Verdict:
        return Verdict(level, reason, zone, remote, evidence, contract)

    if contract not in cfg["contracts_allowed"]:
        return verdict("exclu", f"contrat {contract}")
    age = age_days(job.published_at)
    if age is not None and age > cfg.get("max_age_days", 30):
        return verdict("exclu", f"publiée il y a {int(age)} jours")

    coords = (job.lat, job.lon) if job.lat is not None and job.lon is not None else None
    postcode, dept = label_postcode(job.location)
    # géocodage seulement si utile : coordonnées absentes, ou zone décrite par codes postaux
    needs_postcode = bool(onsite.get("zone_departments") or onsite.get("zone_postcodes")) and not (postcode or dept)
    if job.location and (coords is None or needs_postcode):
        found = geo.locate(job.location)
        if found:
            coords = coords or (found[0], found[1])
            postcode = postcode or found[2]
    zone = zone_match(onsite, coords, postcode, dept, job.location)

    if zone and remote == "full":
        return verdict("ok", f"full remote, bureau zone {zone}", zone)
    if zone and max_days >= 5:
        mode = {"partial": "hybride", "none": "présentiel"}.get(remote, "présentiel ou hybride")
        return verdict("ok", f"{mode}, bureau zone {zone}", zone)
    if zone:
        days = onsite_days(job, remote)
        limit = f"max {max_days} j/sem sur site"
        if days is not None and days > max_days:
            return verdict("exclu", f"{days} j/sem sur site en zone {zone} ({limit})", zone)
        if days is not None:
            return verdict("ok", f"{days} j/sem sur site, bureau zone {zone}", zone)
        return verdict("douteux", f"bureau zone {zone}, rythme sur site à confirmer ({limit})", zone)

    if job.country and job.country not in countries and remote != "full":
        return verdict("exclu", f"à l'étranger ({job.location or job.country}) sans full remote")
    if remote == "full":
        if not remote_cfg.get("accepted", True):
            return verdict("exclu", "full remote hors zone (remote non recherché)")
        if remote_open_to_user(job, remote_cfg):
            return verdict("ok", f"full remote {where}")
        return verdict("exclu", f"remote hors {where} ({job.remote_scope or job.country or 'portée inconnue'})")
    if remote == "unclear" and remote_cfg.get("accepted", True):
        if job.remote_scope and not remote_open_to_user(job, remote_cfg):
            return verdict("exclu", f"remote hors {where} ({job.remote_scope})")
        return verdict("douteux", "hors zone, remote à confirmer")
    if coords is None and not job.location:
        return verdict("exclu", "lieu et remote non précisés")
    place = job.location or "lieu inconnu"
    return verdict("exclu", f"hors zone ({place}), {remote if remote != 'unknown' else 'remote non mentionné'}")
