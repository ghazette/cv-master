"""LinkedIn, Indeed (et optionnellement Glassdoor, Google Jobs) via python-jobspy.

Scraping en mode invité, sans compte, à faible volume :
- famille « zone » : quelques requêtes FR autour de chaque lieu de `search_areas` (rayon plafonné à ~40 km) ;
- famille « remote » : quelques requêtes EN en France avec le filtre télétravail du site (si le remote est accepté).

Chaque appel ne vise qu'un site à la fois, avec une pause entre deux appels, pour
pouvoir désactiver proprement un site qui bloque sans perdre les autres.

La lib est importée dans fetch() : son absence ne casse pas les autres sources.
Lancement : `uv run --with python-jobspy --with requests python ...`

Fiabilité du remote : jobspy calcule `is_remote` en cherchant "remote"/"wfh" dans le texte
(LinkedIn, Indeed, Google) ou d'après un type de lieu (Glassdoor). Rien de structuré et les
offres françaises disent « télétravail » : on renseigne donc toujours remote="unknown" et on
marque les offres issues d'une recherche remote avec le tag "recherche-remote".
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterator

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "jobspy"
LABEL = "LinkedIn / Indeed (python-jobspy)"
KIND = "scrape"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 12

# Sites actifs par défaut (surchargeables par config["jobspy_sites"]).
# Au 2026-09-15, depuis la France :
# - linkedin, indeed : fonctionnent ;
# - glassdoor : 400 sur la résolution de lieu (findPopularLocationAjax), aucun résultat ;
# - google : 0 résultat (page de consentement / rendu JS), quelle que soit la formulation.
DEFAULT_SITES = ("linkedin", "indeed")

# LinkedIn (paramètre `distance`) et Indeed (`radiusUnit: MILES`) attendent des miles.
MAX_DISTANCE_MILES = 25  # ≈ 40 km : au-delà, les sites renvoient surtout du bruit
REMOTE_LOCATION = "France"
QUERIES_PER_FAMILY = 3
PAUSE_S = 6.0            # entre deux appels jobspy
MAX_EMPTY_STREAK = 4     # appels consécutifs vides/en erreur avant de couper un site

_CONTRACT = (  # ordre significatif : "fulltime, contract" -> freelance
    ("internship", "stage"),
    ("contract", "freelance"),
    ("temporary", "cdd"),
    ("fulltime", "cdi"),
)
_PERIOD = {"yearly": "year", "monthly": "month", "daily": "day", "hourly": "hour"}
_COUNTRY = {"france": "FR", "fr": "FR"}


def _clean(value: Any) -> Any:
    """None pour les valeurs absentes du DataFrame (None, NaN, NaT, "nan")."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if str(value).strip().lower() in ("", "nan", "nat", "none"):
        return None
    return value


def _text(value: Any) -> str:
    v = _clean(value)
    return str(v).strip() if v is not None else ""


def _country(location: str) -> str:
    """Dernier segment du libellé : "Nantes, PDL, FR" (Indeed), "Nantes, Pays de la Loire, France" (LinkedIn)."""
    if not location:
        return ""
    last = location.split(",")[-1].strip().lower()
    if last in _COUNTRY:
        return _COUNTRY[last]
    return last.upper() if len(last) == 2 and last.isalpha() else ""


def _contract(job_type: str) -> str:
    t = job_type.lower()
    for key, value in _CONTRACT:
        if key in t:
            return value
    return "unknown"


def _num(value: Any) -> float | None:
    v = _clean(value)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _pick(queries: list[str]) -> list[str]:
    """Sous-ensemble court et sans doublon des requêtes (l'ordre de la config fait foi)."""
    out: list[str] = []
    for q in queries:
        if q and q.lower() not in (x.lower() for x in out):
            out.append(q)
        if len(out) >= QUERIES_PER_FAMILY:
            break
    return out


def _plan(ctx: Context, sites: list[str]) -> Iterator[tuple[str, str, dict[str, Any], list[str]]]:
    """Génère (site, libellé, kwargs scrape_jobs, tags) pour chaque appel prévu."""
    hours = ctx.max_age_days * 24
    areas = [(f"{a['city']}, France", max(5, min(MAX_DISTANCE_MILES, round(a["radius_km"] / 1.609))))
             for a in ctx.areas]
    for query in _pick(ctx.queries_fr):
        for location, miles in areas:
            for site in sites:
                kw: dict[str, Any] = dict(search_term=query, location=location,
                                          distance=miles, hours_old=hours)
                if site == "google":
                    # Google ignore location/distance : tout passe par la phrase de recherche.
                    kw["google_search_term"] = f"{query} emplois près de {location} depuis 1 mois"
                yield site, f"{query} @ {location}", kw, [f"jobspy:{site}"]
    for query in _pick(ctx.queries_en) if ctx.remote_wanted else []:
        for site in sites:
            kw = dict(search_term=query, location=REMOTE_LOCATION, is_remote=True, hours_old=hours)
            if site == "indeed":
                # Indeed ne combine pas le filtre de date et le filtre télétravail : avec
                # hours_old le filtre remote saute. On garde le remote et on filtre l'âge ici.
                kw.pop("hours_old")
            if site == "google":
                kw["google_search_term"] = f"{query} remote France depuis 1 mois"
            yield site, f"{query} @ remote France", kw, [f"jobspy:{site}", "recherche-remote"]


def _to_job(row: dict[str, Any], tags: list[str]) -> Job | None:
    site = _text(row.get("site"))
    raw_id = _text(row.get("id"))
    title = _text(row.get("title"))
    url = _text(row.get("job_url_direct")) or _text(row.get("job_url"))
    if not (site and raw_id and title and url):
        return None
    # "li-4467047330" -> "4467047330"
    native_id = raw_id.split("-", 1)[1] if re.match(r"^[a-z]{2}-", raw_id) else raw_id
    location = _text(row.get("location"))
    currency = _text(row.get("currency")).upper()
    period = _PERIOD.get(_text(row.get("interval")).lower(), "")
    # Salaire gardé seulement en euros (ou devise non précisée) et sur une période connue.
    with_salary = bool(period) and currency in ("", "EUR")
    return Job(
        source=NAME,
        source_id=f"{site}:{native_id}",
        title=title,
        company=_text(row.get("company")),
        url=url,
        description=html_to_text(_text(row.get("description"))),
        location=location,
        country=_country(location),
        remote="unknown",
        contract=_contract(_text(row.get("job_type"))),
        salary_min=_num(row.get("min_amount")) if with_salary else None,
        salary_max=_num(row.get("max_amount")) if with_salary else None,
        salary_period=period if with_salary else "",
        published_at=iso_date(_text(row.get("date_posted"))),
        tags=list(tags),
    )


def fetch(ctx: Context) -> Iterator[Job]:
    try:
        from jobspy import scrape_jobs  # import local : dépendance optionnelle
    except ImportError:
        ctx.log("jobspy : python-jobspy absent, source ignorée "
                "(lancer via `uv run --with python-jobspy --with requests python ...`)")
        return

    sites = [s for s in ctx.config.get("jobspy_sites", DEFAULT_SITES)
             if s in ("linkedin", "indeed", "glassdoor", "google")]
    empty_streak = {s: 0 for s in sites}
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str, str]] = set()
    first = True

    for site, label, kw, tags in _plan(ctx, sites):
        if empty_streak[site] >= MAX_EMPTY_STREAK:
            continue
        if not first:
            polite_sleep(PAUSE_S)
        first = False
        try:
            df = scrape_jobs(
                site_name=[site],
                results_wanted=ctx.per_query,
                country_indeed="France",
                linkedin_fetch_description=True,
                description_format="html",
                verbose=0,
                **kw,
            )
        except Exception as e:  # jobspy lève des exceptions hétérogènes selon le site
            ctx.log(f"jobspy/{site} « {label} » : échec ({type(e).__name__}: {str(e)[:200]})")
            empty_streak[site] += 1
            continue

        rows = df.to_dict("records") if df is not None and not df.empty else []
        empty_streak[site] = 0 if rows else empty_streak[site] + 1
        if empty_streak[site] >= MAX_EMPTY_STREAK:
            ctx.log(f"jobspy/{site} : {MAX_EMPTY_STREAK} appels sans résultat, site coupé "
                    "pour cette collecte (blocage probable)")

        for row in rows:
            job = _to_job(row, tags)
            if job is None or job.uid in seen_ids:
                continue
            age = age_days(job.published_at)
            if age is not None and age > ctx.max_age_days:
                continue
            # Même offre relayée par deux sites (ou deux requêtes) : on garde la première.
            key = (job.title.lower(), job.company.lower(), job.location.split(",")[0].lower())
            if key in seen_keys:
                continue
            seen_ids.add(job.uid)
            seen_keys.add(key)
            yield job
