"""SerpApi : moteur Google Jobs (résultats de Google « Emplois »).

Endpoint : GET https://serpapi.com/search.json?engine=google_jobs
Doc      : https://serpapi.com/google-jobs-api
           https://serpapi.com/locations-api   (noms canoniques pour `location`)
           https://serpapi.com/account-api     (crédits restants : gratuit, hors quota)

Paramètres (doc) :
    q, api_key, gl=fr (pays), hl=fr (langue), google_domain (google.com par défaut)
    location   nom canonique « Commune,Region-Sans-Accents,France » (ex. « Nantes,Pays de la Loire,France »),
               à vérifier via https://serpapi.com/locations.json. Construit depuis `search_areas`
               (city + region), ou pris tel quel dans `serpapi_location` si le lieu le précise.
               Sans location, la recherche prend la localisation du proxy.
    lrad       rayon en km, indicatif (« does not strictly limit the radius »)
    next_page_token  pagination, 10 résultats par page (`start` n'est plus supporté par Google)
    no_cache   false par défaut : une recherche identique en cache (1 h) est gratuite
    ltype (télétravail) et chips : DÉPRÉCIÉS par Google. La famille remote passe donc par le mot-clé
    « télétravail » avec location=France.

Réponse : {"jobs_results": [...], "serpapi_pagination": {"next_page_token": "..."}}
Erreur d'auth (vérifiée avec une fausse clé, search.json et account.json) :
    HTTP 401 {"error": "Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key"}

Quota : 250 recherches/mois sur l'offre gratuite, soit 6 recherches max par run avec MIN_INTERVAL_H = 24.
On lit d'abord account.json (gratuit) pour ne jamais dépasser le solde restant.
Les requêtes FR tournent d'un jour à l'autre (2 par run) pour toutes les couvrir en quelques jours.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "serpapi_gjobs"
LABEL = "Google Jobs (SerpApi)"
KIND = "api"
REQUIRES = ["SERPAPI_KEY"]
MIN_INTERVAL_H = 24

SEARCH_URL = "https://serpapi.com/search.json"
ACCOUNT_URL = "https://serpapi.com/account.json"
MAX_SEARCHES = 6
QUERIES_PER_RUN = 2



def _locations(ctx: Context) -> list[tuple[str, str, int | None, str]]:
    """(libellé, location SerpApi, lrad km, suffixe de requête) : un par lieu de recherche, puis remote."""
    out = []
    for area in ctx.areas:
        loc = area.get("serpapi_location")
        if not loc:
            region = unicodedata.normalize("NFKD", area.get("region") or "")
            region = "".join(c for c in region if not unicodedata.combining(c))
            loc = ",".join(x for x in (area["city"], region, "France") if x)
        out.append((area["name"], loc, int(area["radius_km"]), ""))
    if ctx.remote_wanted:
        out.append(("télétravail FR", "France", None, " télétravail"))
    return out

# Extrait de réponse attendue (doc https://serpapi.com/google-jobs-api, exemple « Java Developer ») :
_SAMPLE_ITEM: dict[str, Any] = {
    "title": "Java Full stack Developer",
    "company_name": "Unique System Skills LLC",
    "location": "Anywhere",
    "via": "Dice",
    "share_link": "https://www.google.com/search?ibp=htl;jobs&q=Java+Developer&htidocid=um1LvoxLW2FiHLGIAAAAAA%3D%3D",
    "extensions": ["22 hours ago", "Work from home", "Contractor"],
    "detected_extensions": {
        "posted_at": "22 hours ago",
        "work_from_home": True,
        "schedule_type": "Contractor",
        "qualifications": "No degree mentioned",
    },
    "description": "We have an opening for Java Full stack Developer...",
    "apply_options": [{"title": "Dice",
                       "link": "https://www.dice.com/job-detail/f33faceb-9a02-4040-92f1-89d576143a1d"}],
    "job_id": "eyJqb2JfdGl0bGUiOiJKYXZhIEZ1bGwgc3RhY2sgRGV2ZWxvcGVyIiwiY29tcGFueV9uYW1lIjoiVW5pcXVlIFN5c3RlbSBTa2lsbHMgTExDIiwiaHRpZG9jaWQiOiJ1bTFMdm94TFcyRmlITEdJQUFBQUFBPT0ifQ==",
}

# schedule_type (« Contractor », « Prestataire », « Stage »...) -> contrat commun.
# « Full-time » / « À plein temps » décrit le temps de travail, pas le contrat : unknown.
_CONTRACT_WORDS = [
    ("freelance", r"freelance|ind[ée]pendant|contractor|prestataire"),
    ("alternance", r"alternance|apprenti\w*|apprenticeship"),
    ("stage", r"stage|internship"),
    ("interim", r"int[ée]rim\w*"),
    ("cdd", r"cdd|temporaire|temporary"),
    ("cdi", r"cdi"),
]
_PERIODS = [
    ("hour", r"heure|horaire|hour|hourly"),
    ("day", r"jour|journalier|day|daily"),
    ("month", r"mois|mensuel|month|monthly"),
    ("year", r"\ban\b|annuel|ann[ée]e|year|yearly|annual"),
]
_AMOUNT = re.compile(r"(\d[\d\s  .,]*\d|\d)\s*([kK]\b)?")
_RELATIVE = re.compile(r"(\d+)\s*\+?\s*(minutes?|min|heures?|hours?|h|jours?|days?|semaines?|weeks?|mois|months?)\b")


def _contract(label: str | None) -> str:
    low = (label or "").lower()
    for value, pattern in _CONTRACT_WORDS:
        if re.search(rf"\b(?:{pattern})\b", low):
            return value
    return "unknown"


def _amount(raw: str, thousands: str) -> float | None:
    s = re.sub(r"[\s  ]", "", raw)
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        value = float(s)
    except ValueError:
        return None
    return value * 1000 if thousands else value


def _salary(text: str | None) -> tuple[float | None, float | None, str]:
    """« 45 k € à 55 k € par an » -> (45000, 55000, "year"). Sans unité, seul un montant >= 12 000 est lu comme annuel."""
    if not text:
        return None, None, ""
    low = text.lower()
    period = next((p for p, pattern in _PERIODS if re.search(pattern, low)), "")
    values = [v for v in (_amount(n, k) for n, k in _AMOUNT.findall(text)) if v]
    if not values:
        return None, None, ""
    if not period:
        if min(values) < 12000:
            return None, None, ""
        period = "year"
    return min(values), max(values), period


def _posted_to_iso(text: str | None, now: datetime | None = None) -> str:
    """Date relative de Google (« il y a 3 jours », « 22 hours ago », « hier ») -> ISO UTC approximatif."""
    if not text:
        return ""
    now = now or datetime.now(timezone.utc)
    low = text.lower()
    if re.search(r"aujourd|today|just|instant|maintenant", low):
        delta = timedelta(0)
    elif re.search(r"\bhier\b|yesterday", low):
        delta = timedelta(days=1)
    else:
        m = _RELATIVE.search(low)
        if not m:
            return ""
        n, unit = int(m.group(1)), m.group(2)
        if unit.startswith("min"):
            delta = timedelta(minutes=n)
        elif unit.startswith(("heure", "hour")) or unit == "h":
            delta = timedelta(hours=n)
        elif unit.startswith(("jour", "day")):
            delta = timedelta(days=n)
        elif unit.startswith(("semaine", "week")):
            delta = timedelta(weeks=n)
        else:  # mois / month
            delta = timedelta(days=30 * n)
    return iso_date((now - delta).isoformat())


def _parse(item: dict[str, Any]) -> Job:
    ext = item.get("detected_extensions") or {}
    links = [o.get("link") for o in item.get("apply_options") or [] if o.get("link")]
    # job_id encode titre + entreprise + htidocid : stable, mais long. On le raccourcit.
    raw_id = item.get("job_id") or item.get("share_link") or f"{item.get('title')}|{item.get('company_name')}"
    smin, smax, period = _salary(ext.get("salary"))
    return Job(
        source=NAME,
        source_id=hashlib.sha1(raw_id.encode()).hexdigest()[:20],
        title=html_to_text(item.get("title")),
        company=html_to_text(item.get("company_name")),
        url=links[0] if links else item.get("share_link") or "",
        description=html_to_text(item.get("description")),
        location=item.get("location") or "",
        country="FR",  # gl=fr et localisations françaises
        # work_from_home est un drapeau structuré de Google (offre marquée télétravail, cf. jobLocationType
        # TELECOMMUTE). Son absence ne veut pas dire « sur site » : unknown.
        remote="full" if ext.get("work_from_home") is True else "unknown",
        contract=_contract(ext.get("schedule_type")),
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        published_at=_posted_to_iso(ext.get("posted_at")),
        tags=[t for t in (item.get("via"), ext.get("schedule_type")) if t],
    )


def _searches_left(ctx: Context) -> int | None:
    """Solde de recherches via account.json (ne consomme pas de crédit). None si inconnu."""
    try:
        r = ctx.http.get(ACCOUNT_URL, params={"api_key": ctx.env["SERPAPI_KEY"]}, timeout=20)
    except requests.RequestException as exc:
        ctx.log(f"[{NAME}] account.json injoignable ({exc}), budget par défaut")
        return None
    if r.status_code == 401:
        raise RuntimeError(f"SerpApi : clé refusée (HTTP 401 : {' '.join(r.text[:200].split())}). Vérifier SERPAPI_KEY.")
    try:
        r.raise_for_status()
        data = r.json()
        return int(data.get("total_searches_left", data.get("plan_searches_left")))
    except (requests.RequestException, ValueError, TypeError) as exc:
        ctx.log(f"[{NAME}] solde illisible ({exc}), budget par défaut")
        return None


def _plan(ctx: Context) -> list[tuple[str, dict[str, Any]]]:
    queries = ctx.queries_fr
    if not queries:
        return []
    start = date.today().toordinal() % len(queries)
    picked = [queries[(start + i) % len(queries)] for i in range(min(QUERIES_PER_RUN, len(queries)))]
    plan = []
    # requête d'abord, lieu ensuite : avec un budget réduit, chaque requête garde au moins le 1er lieu
    for q in picked:
        for label, location, lrad, suffix in _locations(ctx):
            params = {"q": q + suffix, "location": location}
            if lrad:
                params["lrad"] = lrad
            plan.append((f"{q}{suffix} @ {label}", params))
    return plan


def fetch(ctx: Context) -> Iterator[Job]:
    left = _searches_left(ctx)
    budget = MAX_SEARCHES if left is None else min(MAX_SEARCHES, left)
    if budget <= 0:
        ctx.log(f"[{NAME}] plus de recherches disponibles ce mois-ci, source sautée")
        return

    plan = _plan(ctx)[:budget]
    pages_per_search = max(1, budget // max(1, len(plan)))
    seen: set[str] = set()
    used = 0

    for label, params in plan:
        kept, token = 0, None
        for _ in range(pages_per_search):
            if used >= budget:
                return
            if used:
                polite_sleep(1.5)
            query = {"engine": "google_jobs", "gl": "fr", "hl": "fr", "api_key": ctx.env["SERPAPI_KEY"], **params}
            if token:
                query["next_page_token"] = token
            try:
                r = ctx.http.get(SEARCH_URL, params=query, timeout=60)
                used += 1
                if r.status_code == 401:
                    raise RuntimeError("SerpApi : clé refusée (HTTP 401). Vérifier SERPAPI_KEY.")
                if r.status_code == 429:
                    ctx.log(f"[{NAME}] quota ou débit dépassé (HTTP 429), arrêt : {r.text[:200]}")
                    return
                data = r.json()
            except (requests.RequestException, ValueError) as exc:
                ctx.log(f"[{NAME}] échec « {label} » : {exc}")
                break
            if data.get("error"):
                # « Google hasn't returned any results for this query. » n'est pas une panne
                if "hasn't returned any results" not in data["error"]:
                    ctx.log(f"[{NAME}] erreur « {label} » : {data['error']}")
                break

            for item in data.get("jobs_results") or []:
                job = _parse(item)
                if job.source_id in seen:
                    continue
                age = age_days(job.published_at)
                if age is not None and age > ctx.max_age_days:
                    continue
                seen.add(job.source_id)
                kept += 1
                yield job
                if kept >= ctx.per_query:
                    break
            token = (data.get("serpapi_pagination") or {}).get("next_page_token")
            if not token or kept >= ctx.per_query:
                break
