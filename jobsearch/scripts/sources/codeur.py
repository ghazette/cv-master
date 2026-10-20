"""Codeur.com — place de marché de missions freelance françaises, flux RSS global.

Endpoint : GET https://www.codeur.com/projects.rss (RSS 2.0, public, sans clé)
  - Pas de flux par catégorie ni de recherche : ~35 derniers projets tous métiers (≈ 24 h de
    publication). Une collecte quotidienne ou plus fréquente est nécessaire pour ne rien rater.
  - <item> : title (entités HTML), link, guid (id numérique), pubDate (RFC 2822),
    description HTML : « <p>Budget : 500 € à 1 000 € - Catégories : Full-stack, API, …</p>
    <p>extrait tronqué …</p> <p><a>Voir ce projet sur Codeur</a></p> ».
  - Le budget est un montant de projet (pas un TJM) → mis en tag, pas dans salary_*.
Pré-filtre métier : motifs `prefilter` de la config (ou mots des requêtes) cherchés dans le titre
et les catégories du projet. Source sautée si la config n'accepte pas le freelance.
Contrat : missions freelance, réalisées à distance, clients en France.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "codeur"
LABEL = "Codeur.com"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 2

FEED = "https://www.codeur.com/projects.rss"

# Pré-filtre métier : config.json `prefilter` (voir scripts/prefilter.py), sur titre + catégories.
_META = re.compile(r"Budget\s*:\s*(?P<budget>.*?)\s*-\s*Catégories\s*:\s*(?P<cats>[^<]*)", re.I | re.S)
_LINK_P = re.compile(r"<p>\s*<a[^>]*>\s*Voir ce projet sur Codeur\s*</a>\s*</p>", re.I)


def _item_to_job(item: ET.Element) -> tuple[Job, list[str]] | None:
    link = (item.findtext("link") or "").strip()
    title = html_to_text(item.findtext("title"))
    if not link or not title:
        return None
    html_desc = item.findtext("description") or ""
    meta = _META.search(html_desc)
    cats = [html_to_text(c).strip() for c in meta.group("cats").split(",")] if meta else []
    cats = [c for c in cats if c]
    budget = html_to_text(meta.group("budget")) if meta else ""
    m_id = re.search(r"/projects/(\d+)", link)
    tags = cats + ([f"Budget : {budget}"] if budget else [])
    job = Job(
        source=NAME,
        source_id=(item.findtext("guid") or "").strip() or (m_id.group(1) if m_id else link),
        title=title,
        company="",  # client anonyme dans le flux
        url=link,
        description=html_to_text(_LINK_P.sub("", html_desc)),
        remote="full",
        remote_scope="France",
        country="FR",
        contract="freelance",
        published_at=iso_date(item.findtext("pubDate")),
        tags=tags,
    )
    return job, cats


def fetch(ctx: Context) -> Iterator[Job]:
    if "freelance" not in (ctx.config.get("contracts_allowed") or []):
        ctx.log(f"[{NAME}] freelance non accepté dans la config, source sans objet")
        return
    try:
        resp = ctx.http.get(FEED, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as exc:
        ctx.log(f"[{NAME}] flux en échec : {exc}")
        return
    finally:
        polite_sleep()

    seen: set[str] = set()
    kept = 0
    for item in root.iterfind("./channel/item"):
        parsed = _item_to_job(item)
        if parsed is None:
            continue
        job, cats = parsed
        if job.uid in seen or not ctx.prefilter.any_signal(" ".join([job.title, *cats])):
            continue
        age = age_days(job.published_at)
        if age is not None and age > ctx.max_age_days:
            continue
        seen.add(job.uid)
        kept += 1
        yield job
        if kept >= ctx.per_query:
            return
