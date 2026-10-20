"""Jobgether — offres 100 % remote, via l'API publique destinée aux agents.

Endpoints
---------
- GET https://jobgether.com/api/v1/jobs      (doc : https://jobgether.com/astroapi/ai/jobs/docs)
    keyword, locations (slug pays/continent : france, europe…), contractType,
    experience, remoteType, includeHybrid, salaryMin/salaryMax + currency,
    sort=relevance|date, page (≤ 10), limit (≤ 25).
    Réponse : jobs[] {id, title, company, url, location, remote, contractType,
    experience, salaryRange?, jobFunctions[], postedAt} + pagination {page, limit, hasMore}.
- GET <job.url> = https://jobgether.com/offer/<id>-<slug>
    Page de l'offre ; son JSON-LD JobPosting contient la description HTML complète
    (servie sans charset : décoder en UTF-8).

Constats du 15/09/2026
----------------------
- Toutes les offres renvoyées sont « Full Remote » : remoteType=hybrid|remote-first,
  includeHybrid et les slugs de ville (paris, nantes…) sont acceptés mais sans effet.
  Pas de famille géographique possible ; seule la famille « remote France » existe.
- locations=france filtre bien : offres ouvertes aux résidents français ; le champ
  `location` donne alors la portée brute du remote ("France", "Europe", "EMEA", "Anywhere"…).
- experience filtre bien mais exclut les ~25 % d'offres sans niveau renseigné :
  non utilisé, le niveau est mis en tag.
- salaryRange rare, annuel ("190000-190000 USD").
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "jobgether"
LABEL = "Jobgether"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 12

API = "https://jobgether.com/api/v1/jobs"
PAGE_SIZE = 25          # plafond de l'API
MAX_PAGES = 10          # plafond de l'API
DETAIL_MAX = 80         # pages d'offre lues au plus par collecte (description)

CONTRACT_MAP = {"full time": "cdi", "freelance": "freelance", "fixed term": "cdd",
                "internships": "stage", "internship": "stage"}
REMOTE_MAP = {"full remote": "full", "hybrid": "partial"}

_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_SALARY = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*([A-Z]{3})")


def _queries(ctx: Context) -> list[str]:
    """queries_en d'abord (plateforme internationale), puis les requêtes FR non redondantes
    (des offres françaises n'ont que des titres en français)."""
    out, seen = [], set()
    for q in ctx.queries_en + ctx.queries_fr:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def _search(ctx: Context, keyword: str) -> list[dict[str, Any]] | None:
    """Offres remote France les plus récentes pour un mot-clé ; None si la 1re page échoue."""
    jobs: list[dict[str, Any]] = []
    pages = min(MAX_PAGES, max(1, math.ceil(ctx.per_query / PAGE_SIZE)))
    for page in range(1, pages + 1):
        if page > 1:
            polite_sleep()
        params = {"keyword": keyword, "locations": "france", "sort": "date",
                  "limit": PAGE_SIZE, "page": page}
        try:
            r = ctx.http.get(API, params=params, timeout=40)
            data = r.json()
            if r.status_code != 200:
                raise ValueError(f"HTTP {r.status_code} {data.get('code')} {data.get('detail')}")
        except (requests.RequestException, ValueError) as e:
            ctx.log(f"jobgether: échec « {keyword} » page {page} ({e})")
            return jobs if page > 1 else None
        batch = data.get("jobs") or []
        jobs += batch
        # Tri par date : inutile d'aller plus loin si la page atteint déjà la limite d'âge.
        oldest = age_days(iso_date(batch[-1].get("postedAt"))) if batch else None
        if not (data.get("pagination") or {}).get("hasMore") or (
                oldest is not None and oldest > ctx.max_age_days):
            break
    return jobs[: ctx.per_query]


def _posting_ld(ctx: Context, url: str) -> dict[str, Any] | None:
    """JSON-LD JobPosting de la page de l'offre."""
    try:
        r = ctx.http.get(url, timeout=40)
        r.raise_for_status()
    except requests.RequestException as e:
        ctx.log(f"jobgether: page offre illisible {url} ({e})")
        return None
    page = r.content.decode("utf-8", "replace")
    for m in _LD.finditer(page):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                return d
    return None


def _to_job(item: dict[str, Any]) -> Job | None:
    sid, url, title = item.get("id"), item.get("url"), item.get("title")
    if not (sid and url and title):
        return None
    smin = smax = None
    period = ""
    m = _SALARY.search(item.get("salaryRange") or "")
    if m and m.group(3) == "EUR":     # Job n'a pas de champ devise : euros seulement
        smin, smax, period = float(m.group(1)), float(m.group(2)), "year"
    tags = list(item.get("jobFunctions") or [])
    if item.get("experience"):
        tags.append(item["experience"])
    scope = (item.get("location") or "").strip()
    return Job(
        source=NAME,
        source_id=str(sid),
        title=title.strip(),
        company=(item.get("company") or "").strip(),
        url=url,
        location=scope,
        country="FR",                  # requête locations=france : offre ouverte depuis la France
        remote=REMOTE_MAP.get((item.get("remote") or "").lower(), "unknown"),
        remote_scope=scope,
        contract=CONTRACT_MAP.get((item.get("contractType") or "").lower(), "unknown"),
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        published_at=iso_date(item.get("postedAt")),
        tags=tags,
    )


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()
    ok = failed = details = 0
    for n, keyword in enumerate(_queries(ctx)):
        if n:
            polite_sleep()
        items = _search(ctx, keyword)
        if items is None:
            failed += 1
            continue
        ok += 1
        for item in items:
            job = _to_job(item)
            if job is None or job.source_id in seen:
                continue
            age = age_days(job.published_at)
            if age is not None and age > ctx.max_age_days:
                continue
            seen.add(job.source_id)
            # Description complète : une page par offre retenue, plafonnée.
            if details < DETAIL_MAX:
                polite_sleep(0.5)
                details += 1
                ld = _posting_ld(ctx, job.url)
                if ld:
                    job.description = html_to_text(ld.get("description"))
            yield job
    if failed and not ok:
        raise RuntimeError("jobgether: aucune requête n'a abouti")
