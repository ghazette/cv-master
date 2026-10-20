"""Himalayas — board 100 % remote, recherche limitée aux postes ouverts depuis la France.

Endpoint : GET https://himalayas.app/jobs/api/search?q=<mots-clés>&country=FR[&page=N]
  - Pas de clé. 20 offres par page, `limit` ignoré par l'API.
  - Pagination : le flux /jobs/api annonce une pagination par `cursor` (champ `nextCursor`, l'offset
    est déprécié). La recherche ne renvoie pas (encore) de `nextCursor` mais accepte `page=` (1-based) :
    on suit `nextCursor` s'il est présent, sinon `page`.
  - Résultats triés par pertinence, pas par date : l'âge est filtré offre par offre.
  - Champs utiles : title, companyName, employmentType ("Full Time", "Contractor", "Part Time",
    "Intern", "Other"…), minSalary/maxSalary/currency/salaryPeriod ("annual"…),
    locationRestrictions (liste de pays ; vide = monde entier), categories, description (HTML),
    pubDate (epoch s), guid / applicationLink (page Himalayas).
Contraintes : usage raisonnable, lien retour obligatoire → `url` = page Himalayas (guid).
"""
from __future__ import annotations

import re
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "himalayas"
LABEL = "Himalayas"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 6

API = "https://himalayas.app/jobs/api/search"
PAGE_SIZE = 20  # imposé par l'API

_PERIOD = {"annual": "year", "yearly": "year", "year": "year", "monthly": "month", "month": "month",
           "weekly": "", "daily": "day", "day": "day", "hourly": "hour", "hour": "hour"}


def _contract(value: str | None) -> str:
    t = (value or "").lower().replace("-", " ")
    if "intern" in t:
        return "stage"
    if "contract" in t or "freelance" in t:
        return "freelance"
    if "temporary" in t:
        return "cdd"
    if "full time" in t or "permanent" in t:
        return "cdi"
    return "unknown"  # "Part Time", "Other", vide


def _to_job(raw: dict) -> Job | None:
    url = raw.get("guid") or raw.get("applicationLink") or ""
    title = html_to_text(raw.get("title"))
    if not url or not title:
        return None
    # identifiant stable = "<entreprise>/jobs/<slug>" (le slug n'a pas toujours d'id numérique)
    m = re.search(r"/companies/([^/]+/jobs/[^/?#]+)", url)
    restrictions = [c for c in (raw.get("locationRestrictions") or []) if c]
    salary_min = raw.get("minSalary") or None
    salary_max = raw.get("maxSalary") or None
    return Job(
        source=NAME,
        source_id=m.group(1) if m else url,
        title=title,
        company=html_to_text(raw.get("companyName")),
        url=url,
        description=html_to_text(raw.get("description")) or html_to_text(raw.get("excerpt")),
        remote="full",
        # liste exhaustive des pays autorisés ; liste vide = aucune restriction
        remote_scope=", ".join(restrictions) if restrictions else "Worldwide",
        # la requête filtre country=FR : on ne marque FR que si la France est nommée explicitement
        country="FR" if "France" in restrictions else "",
        contract=_contract(raw.get("employmentType")),
        salary_min=float(salary_min) if salary_min else None,
        salary_max=float(salary_max) if salary_max else None,
        salary_period=_PERIOD.get((raw.get("salaryPeriod") or "").lower(), "") if (salary_min or salary_max) else "",
        published_at=iso_date(raw.get("pubDate")),
        tags=list(raw.get("categories") or []),
    )


def _search(ctx: Context, query: str, seen: set[str]) -> Iterator[Job]:
    kept = 0
    page, cursor = 1, None
    max_pages = ctx.per_query // PAGE_SIZE + 3  # marge pour les offres trop vieilles ou déjà vues
    for _ in range(max_pages):
        params = {"q": query, "country": "FR"}
        if cursor:
            params["cursor"] = cursor
        elif page > 1:
            params["page"] = page
        try:
            resp = ctx.http.get(API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            ctx.log(f"[{NAME}] requête '{query}' page {page} en échec : {exc}")
            return
        finally:
            polite_sleep()

        jobs = data.get("jobs") or []
        for raw in jobs:
            job = _to_job(raw)
            if job is None or job.uid in seen:
                continue
            age = age_days(job.published_at)
            if age is not None and age > ctx.max_age_days:
                continue
            seen.add(job.uid)
            kept += 1
            yield job
            if kept >= ctx.per_query:
                return

        cursor = data.get("nextCursor")
        page += 1
        total = int(data.get("totalCount") or 0)
        if not jobs or (not cursor and (page - 1) * PAGE_SIZE >= total):
            return


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()  # déduplication entre requêtes
    for query in ctx.queries_en:
        yield from _search(ctx, query, seen)
