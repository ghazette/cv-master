"""Remotive — board 100 % remote, flux public unique pré-filtré localement.

Endpoint : GET https://remotive.com/api/remote-jobs
  - Paramètres documentés : category (slugs réels via /api/remote-jobs/categories :
    "software-development", "artificial-intelligence"…), search, company_name, limit.
  - Constat (09/2026) : l'API publique renvoie le même échantillon (≈ 16 offres récentes, tous
    métiers) quelle que soit la catégorie, même invalide. Filtrer côté API ne sert donc à rien et
    coûte du quota → un seul appel sans filtre, puis pré-filtre métier local.
  - Champs : id, url, title, company_name, category, tags[] (parfois 40+ tags génériques sur une
    offre), job_type ("full_time", "contract", "freelance", "part_time", "internship"…),
    publication_date (ISO sans fuseau, UTC), candidate_required_location ("Worldwide", "Europe",
    "USA", "France, Japan, …"), salary (texte libre : "$31,2k- $52k"), description (HTML).
Contraintes (CGU) : 4 appels/jour max conseillés, offres diffusées avec 24 h de décalage, lien retour
obligatoire vers Remotive (`url`). → 1 appel par collecte, MIN_INTERVAL_H = 6.
"""
from __future__ import annotations

import re
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "remotive"
LABEL = "Remotive"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 6

API = "https://remotive.com/api/remote-jobs"

# Pré-filtre métier : config.json `prefilter` (voir scripts/prefilter.py), via ctx.prefilter.


def _contract(value: str | None) -> str:
    t = (value or "").lower()
    if "intern" in t:
        return "stage"
    if t in ("contract", "freelance"):
        return "freelance"
    if t in ("full_time", "permanent"):
        return "cdi"
    return "unknown"  # part_time, other, vide


def _parse_salary(text: str | None) -> tuple[float, float, str] | None:
    """Interprétation prudente du salaire texte libre ; None dès que c'est ambigu."""
    if not text or not re.search(r"\d", text):
        return None
    has_k = bool(re.search(r"\d\s*k\b", text, re.I))
    period = ("hour" if re.search(r"/\s*h(?:ou)?r\b|per hour|hourly", text, re.I)
              else "day" if re.search(r"/\s*day\b|per day|daily", text, re.I)
              else "month" if re.search(r"/\s*mo(?:nth)?\b|per month|monthly", text, re.I)
              else "year")
    values = []
    for num, k in re.findall(r"(\d+(?:[.,]\d+)*)\s*(k\b)?", text, re.I):
        if (k or has_k) and re.fullmatch(r"\d+[.,]\d{1,2}", num):
            v = float(num.replace(",", "."))          # "31,2k"
        else:
            v = float(re.sub(r"[.,]", "", num))       # "120,000"
        if k or (has_k and v < 1000):
            v *= 1000                                 # "$150 - 210K" → 150000
        values.append(v)
    values = [v for v in values if v >= (10000 if period == "year" else 1)][:2]
    if not values:
        return None
    return min(values), max(values), period


def _to_job(raw: dict) -> Job | None:
    url = raw.get("url") or ""
    title = html_to_text(raw.get("title"))
    if not url or not title:
        return None
    scope = (raw.get("candidate_required_location") or "").strip()
    salary = _parse_salary(raw.get("salary"))
    tags = list(raw.get("tags") or [])
    if raw.get("category"):
        tags.append(raw["category"])
    return Job(
        source=NAME,
        source_id=str(raw.get("id") or url),
        title=title,
        company=html_to_text(raw.get("company_name")).strip(),
        url=url,
        description=html_to_text(raw.get("description")),
        remote="full",
        remote_scope=scope,
        country="FR" if re.search(r"\bfrance\b", scope, re.I) else "",
        contract=_contract(raw.get("job_type")),
        salary_min=salary[0] if salary else None,
        salary_max=salary[1] if salary else None,
        salary_period=salary[2] if salary else "",
        published_at=iso_date(raw.get("publication_date")),  # sans fuseau → UTC
        tags=tags,
    )


def fetch(ctx: Context) -> Iterator[Job]:
    try:
        resp = ctx.http.get(API, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        ctx.log(f"[{NAME}] requête en échec : {exc}")
        return
    finally:
        polite_sleep()

    seen: set[str] = set()
    candidates = []
    for raw in data.get("jobs") or []:
        job = _to_job(raw)
        if job is None or job.uid in seen:
            continue
        age = age_days(job.published_at)
        if age is not None and age > ctx.max_age_days:
            continue
        # la catégorie ajoutée en dernier tag ne compte pas dans le signal de stack
        if not ctx.prefilter.pertinent(job.title, job.tags[:-1] if raw.get("category") else job.tags, job.description):
            continue
        seen.add(job.uid)
        candidates.append(job)
    # plafond de volume, en gardant les plus récentes
    candidates.sort(key=lambda j: j.published_at, reverse=True)
    yield from candidates[:ctx.per_query]
