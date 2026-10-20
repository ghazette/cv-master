"""We Work Remotely — board 100 % remote, flux RSS par catégorie.

Endpoints (RSS 2.0, vérifiés) :
  https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss  (le plus fourni)
  https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss
  https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss
  https://weworkremotely.com/categories/remote-programming-jobs.rss            (agrégat, recoupe les autres)
  - Pas de recherche : on lit les flux entiers et on pré-filtre localement.
  - <item> : title ("Company: Role"), region ("Anywhere in the World", "USA Only",
    "North America Only", "Europe Only"…), country (liste de pays préfixés d'un drapeau emoji,
    souvent vide), state, skills, category, type ("Full-Time", "Contract"…), description (HTML,
    commence par « Headquarters: … »), pubDate (RFC 2822), expires_at, guid, link.
  - Les flux contiennent des offres anciennes (jusqu'à 2 ans) → filtre max_age_days.
Contraintes : la page /categories est protégée (403) mais les flux RSS sont publics ; lien retour
vers WWR (`url` = link). MIN_INTERVAL_H = 6.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "weworkremotely"
LABEL = "We Work Remotely"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 6

FEEDS = (
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
)

# Pré-filtre métier : config.json `prefilter` (voir scripts/prefilter.py), via ctx.prefilter.

_FLAG = re.compile("[\U0001F1E6-\U0001F1FF]+\\s*")  # drapeaux emoji (paires d'indicateurs régionaux)
_HQ = re.compile(r"<strong>\s*Headquarters:\s*</strong>\s*(.*?)\s*(?:<br|</p>)", re.I | re.S)


def _contract(value: str | None) -> str:
    t = (value or "").lower().replace("-", " ")
    if "intern" in t:
        return "stage"
    if "contract" in t or "freelance" in t:
        return "freelance"
    if "full time" in t:
        return "cdi"
    return "unknown"  # "Part-Time", vide


def _item_to_job(item: ET.Element) -> Job | None:
    link = (item.findtext("link") or item.findtext("guid") or "").strip()
    raw_title = html_to_text(item.findtext("title"))
    if not link or not raw_title:
        return None
    company, _, role = raw_title.partition(": ")
    if not role:  # titre sans préfixe entreprise
        company, role = "", raw_title

    html_desc = item.findtext("description") or ""
    hq = _HQ.search(html_desc)
    region = (item.findtext("region") or "").strip()
    countries = _FLAG.sub("", item.findtext("country") or "").strip()
    countries = re.sub(r",\s+and\s+", ", ", countries)  # "…, Viet Nam, and South Africa" (virgule d'Oxford seulement)
    state = (item.findtext("state") or "").strip()
    # l'état n'a de sens comme restriction que pour une offre limitée aux États-Unis
    # (sinon c'est l'état du siège, ex. "Delaware" avec 70 pays autorisés)
    if countries != "United States of America":
        state = ""
    # restriction brute et exhaustive : région + liste de pays (+ état US) quand elle est fournie
    scope = " — ".join(p for p in (region, countries, state) if p)
    skills = [re.sub(r"^and\s+", "", s.strip()) for s in (item.findtext("skills") or "").split(",") if s.strip()]
    category = (item.findtext("category") or "").strip()

    return Job(
        source=NAME,
        source_id=link.rstrip("/").rsplit("/", 1)[-1],  # slug stable
        title=role.strip(),
        company=company.strip(),
        url=link,
        description=html_to_text(html_desc),
        location=html_to_text(hq.group(1)) if hq else "",  # siège de l'entreprise, pas le lieu de travail
        remote="full",
        remote_scope=scope,
        country="FR" if re.search(r"\bfrance\b", countries, re.I) else "",
        contract=_contract(item.findtext("type")),
        published_at=iso_date(item.findtext("pubDate")),
        tags=skills + ([category] if category else []),
    )


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()
    # flux « programmation » par défaut ; un autre métier règle `weworkremotely_feeds` dans config.json
    for feed in ctx.config.get("weworkremotely_feeds") or FEEDS:
        try:
            resp = ctx.http.get(feed, timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as exc:
            ctx.log(f"[{NAME}] flux {feed} en échec : {exc}")
            continue
        finally:
            polite_sleep()

        kept = 0
        for item in root.iterfind("./channel/item"):
            job = _item_to_job(item)
            if job is None or job.uid in seen:
                continue
            age = age_days(job.published_at)
            if age is not None and age > ctx.max_age_days:
                continue
            if not ctx.prefilter.pertinent(job.title, job.tags, job.description, max_tags=None):
                continue
            seen.add(job.uid)
            kept += 1
            yield job
            if kept >= ctx.per_query:
                break
