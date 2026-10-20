"""Free-Work — offres CDI et missions freelance IT, API JSON (API Platform / Hydra).

Endpoint
--------
GET https://www.free-work.com/api/job_postings   (Accept: application/ld+json)

Paramètres vérifiés le 15/09/2026 :
- searchKeywords=<texte>  mots-clés (ET logique entre les mots).
  NB : `q` est accepté mais n'a aucun effet (renvoie toutes les offres).
- contracts=permanent | contractor | fixed-term | internship | apprenticeship
  (une seule valeur scalaire ; `contracts[]` est refusé).
- remoteMode=full | partial | none
- locationKeys=fr~pays-de-la-loire~ (région), fr~pays-de-la-loire~loire-atlantique~
  (département), fr~~~ (France entière) ; plusieurs clés séparées par des virgules.
  Le module prend la région de chaque lieu de `search_areas` (slug du nom, sans accents) ;
  un lieu peut forcer sa clé avec `freework_location` (ex. "fr~bretagne~ille-et-vilaine~").
- itemsPerPage, page ; réponse : hydra:member, hydra:totalItems, hydra:view/hydra:next.
- Avec searchKeywords le tri est par pertinence, et publishedAt[after] est ignoré :
  le filtre d'âge se fait côté client.

Champs utiles d'une offre : id, slug, title, description (HTML), candidateProfile,
contracts[], remoteMode, min/maxAnnualSalary, min/maxDailySalary, currency,
location{label, latitude, longitude, countryCode}, company{name}, job{slug},
skills[]{name}, publishedAt.

Offre publique : https://www.free-work.com/fr/tech-it/job-mission/<job.slug>/<slug>
"""
from __future__ import annotations

import re
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep
from config import norm

NAME = "freework"
LABEL = "Free-Work"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 4

API = "https://www.free-work.com/api/job_postings"
SITE = "https://www.free-work.com"
FRANCE = "fr~~~"

CONTRACT_MAP = {"permanent": "cdi", "contractor": "freelance", "fixed-term": "cdd",
                "internship": "stage", "apprenticeship": "alternance", "temporary": "interim"}
# Ordre de préférence quand une offre propose plusieurs contrats.
CONTRACT_PRIORITY = ("cdi", "freelance", "cdd", "interim", "alternance", "stage")



def _location_keys(ctx: Context) -> str:
    keys: list[str] = []
    for area in ctx.areas:
        key = area.get("freework_location")
        if not key and area.get("region"):
            key = "fr~" + re.sub(r"[^a-z0-9]+", "-", norm(area["region"])).strip("-") + "~"
        if key and key not in keys:
            keys.append(key)
    return ",".join(keys)


def _families(ctx: Context) -> list[tuple[dict[str, str], str | None]]:
    """(paramètres natifs, contrat « attendu » de la famille ou None)."""
    allowed = ctx.config.get("contracts_allowed") or []
    out: list[tuple[dict[str, str], str | None]] = []
    keys = _location_keys(ctx)
    if keys:
        for native, contract in (("permanent", "cdi"), ("contractor", "freelance"), ("fixed-term", "cdd")):
            if contract in allowed:
                out.append(({"locationKeys": keys, "contracts": native}, contract))
    elif ctx.areas:
        ctx.log("freework: lieux de recherche sans région (init.py --geocode), famille géographique sautée")
    if ctx.remote_wanted:
        out.append(({"locationKeys": FRANCE, "remoteMode": "full"}, None))
    return out


def _search(ctx: Context, params: dict[str, str]) -> list[dict[str, Any]] | None:
    """Pagine jusqu'à per_query offres ; None si la première page échoue."""
    items: list[dict[str, Any]] = []
    page = 1
    size = max(1, min(ctx.per_query, 100))
    while len(items) < ctx.per_query:
        if page > 1:
            polite_sleep()
        try:
            r = ctx.http.get(API, params={**params, "itemsPerPage": size, "page": page},
                             headers={"Accept": "application/ld+json"}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            ctx.log(f"freework: échec {params} page {page} ({e})")
            return items if page > 1 else None
        items += data.get("hydra:member") or []
        if not (data.get("hydra:view") or {}).get("hydra:next"):
            break
        page += 1
    return items[: ctx.per_query]


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_job(item: dict[str, Any], preferred: str | None) -> Job | None:
    slug, sid = item.get("slug"), item.get("id")
    if not (slug and sid and item.get("title")):
        return None

    # Contrat : celui de la famille de requête s'il figure dans l'offre, sinon le
    # plus « haut » dans la liste ; tous les contrats proposés restent dans les tags.
    raw_contracts = item.get("contracts") or []
    mapped = [CONTRACT_MAP.get(c, "unknown") for c in raw_contracts]
    if preferred and preferred in mapped:
        contract = preferred
    else:
        contract = next((c for c in CONTRACT_PRIORITY if c in mapped), "unknown")

    # Salaire : TJM pour le freelance, annuel sinon (repli sur l'autre si absent).
    annual = (_float(item.get("minAnnualSalary")), _float(item.get("maxAnnualSalary")))
    daily = (_float(item.get("minDailySalary")), _float(item.get("maxDailySalary")))
    smin = smax = None
    period = ""
    if item.get("currency") in (None, "EUR"):
        has_a, has_d = any(v is not None for v in annual), any(v is not None for v in daily)
        if has_d and (contract == "freelance" or not has_a):
            (smin, smax), period = daily, "day"
        elif has_a:
            (smin, smax), period = annual, "year"

    loc = item.get("location") or {}
    remote = item.get("remoteMode")

    desc = html_to_text(item.get("description"))
    profile = html_to_text(item.get("candidateProfile"))
    if profile and profile not in desc:
        desc = f"{desc}\n\nProfil recherché :\n{profile}" if desc else profile

    job_slug = (item.get("job") or {}).get("slug")
    # Sans métier associé (jamais observé), l'URL retombe sur la fiche via son seul slug.
    path = f"job-mission/{job_slug}/{slug}" if job_slug else f"job-mission/{slug}"

    tags = [s["name"] for s in item.get("skills") or [] if s.get("name")]
    tags += [f"contrat:{c}" for c in raw_contracts]

    return Job(
        source=NAME,
        source_id=str(sid),
        title=item["title"].strip(),
        company=((item.get("company") or {}).get("name") or "").strip(),
        url=f"{SITE}/fr/tech-it/{path}",
        description=desc,
        location=loc.get("label") or loc.get("shortLabel") or "",
        lat=_float(loc.get("latitude")),
        lon=_float(loc.get("longitude")),
        country=loc.get("countryCode") or "",
        remote=remote if remote in ("full", "partial", "none") else "unknown",
        contract=contract,
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        published_at=iso_date(item.get("publishedAt")),
        tags=tags,
    )


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()
    ok = failed = 0
    first = True
    # recherche Free-Work = ET entre les mots : des mots courts (config queries.freework) ramènent bien plus
    families = _families(ctx)
    for query in ctx.queries_for("freework"):
        for params, preferred in families:
            if not first:
                polite_sleep()
            first = False
            items = _search(ctx, {"searchKeywords": query, **params})
            if items is None:
                failed += 1
                continue
            ok += 1
            for item in items:
                job = _to_job(item, preferred)
                if job is None or job.source_id in seen:
                    continue
                age = age_days(job.published_at)
                if age is not None and age > ctx.max_age_days:
                    continue
                seen.add(job.source_id)
                yield job
    if failed and not ok:
        raise RuntimeError("freework: aucune requête n'a abouti")
