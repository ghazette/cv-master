"""Jobicy — board 100 % remote, offres dev ouvertes aux candidats basés en France.

Endpoint : GET https://jobicy.com/api/v2/remote-jobs?geo=france&industry=dev&count=N
  - Pas de clé. count 1–100. `industry=dev` est traduit côté API en "engineering".
  - `geo=france` renvoie les offres accessibles depuis la France : jobGeo peut valoir "France",
    mais aussi "Europe", "EMEA", "Anywhere", "Brazil, Canada, France, UK, USA"… On ne demande PAS
    geo=europe (hors cible).
  - Champs : id, url, jobTitle, companyName, jobIndustry[], jobType[] ("Full-Time", "Contract",
    "Part-Time", "Internship"), jobGeo, jobLevel, jobExcerpt, jobDescription (HTML),
    pubDate (ISO), salaryMin/salaryMax/salaryCurrency/salaryPeriod ("yearly"…).
Contraintes (CGU) : 1 appel par heure maximum → une seule requête, MIN_INTERVAL_H = 1 ;
crédit obligatoire → `url` = page Jobicy de l'offre, jamais le lien de candidature direct.
"""
from __future__ import annotations

import re
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "jobicy"
LABEL = "Jobicy"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 1

API = "https://jobicy.com/api/v2/remote-jobs"

_PERIOD = {"yearly": "year", "annual": "year", "monthly": "month", "weekly": "",
           "daily": "day", "hourly": "hour"}


def _contract(types: list[str]) -> str:
    t = " ".join(types).lower().replace("-", " ")
    if "intern" in t:
        return "stage"
    has_ft, has_ct = "full time" in t, ("contract" in t or "freelance" in t)
    if has_ct and not has_ft:
        return "freelance"
    if has_ft and not has_ct:
        return "cdi"
    return "unknown"  # "Part-Time", mixte ou vide


def _to_job(raw: dict) -> Job | None:
    url = raw.get("url") or ""
    title = html_to_text(raw.get("jobTitle"))
    if not url or not title:
        return None
    geo = re.sub(r"\s*,\s*", ", ", (raw.get("jobGeo") or "").strip())  # "APAC,  EMEA" → "APAC, EMEA"
    types = raw.get("jobType") or []
    if isinstance(types, str):
        types = [types]
    smin, smax = raw.get("salaryMin"), raw.get("salaryMax")
    tags = list(raw.get("jobIndustry") or [])
    if raw.get("jobLevel"):
        tags.append(raw["jobLevel"])
    return Job(
        source=NAME,
        source_id=str(raw.get("id") or url),
        title=title,
        company=html_to_text(raw.get("companyName")),
        url=url,
        description=html_to_text(raw.get("jobDescription")) or html_to_text(raw.get("jobExcerpt")),
        remote="full",
        remote_scope=geo,
        country="FR" if re.search(r"\bfrance\b", geo, re.I) else "",
        contract=_contract(types),
        salary_min=float(smin) if smin else None,
        salary_max=float(smax) if smax else None,
        salary_period=_PERIOD.get((raw.get("salaryPeriod") or "").lower(), "") if (smin or smax) else "",
        published_at=iso_date(raw.get("pubDate")),
        tags=tags,
    )


def fetch(ctx: Context) -> Iterator[Job]:
    # industry : "dev" par défaut ; autre métier → `jobicy_industry` dans config.json (liste sur jobicy.com)
    params = {"geo": "france", "industry": ctx.config.get("jobicy_industry") or "dev",
              "count": max(1, min(100, ctx.per_query))}
    try:
        resp = ctx.http.get(API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        ctx.log(f"[{NAME}] requête en échec : {exc}")
        return
    finally:
        polite_sleep()

    seen: set[str] = set()
    for raw in data.get("jobs") or []:
        job = _to_job(raw)
        if job is None or job.uid in seen:
            continue
        age = age_days(job.published_at)
        if age is not None and age > ctx.max_age_days:
            continue
        seen.add(job.uid)
        yield job
