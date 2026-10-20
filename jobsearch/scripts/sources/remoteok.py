"""Remote OK — board 100 % remote, flux global unique.

Endpoint : GET https://remoteok.com/api
  - Pas de clé, pas de recherche : ~100 dernières offres, tous métiers confondus.
  - Le 1er élément du tableau est un avis légal ({"last_updated", "legal"}), à ignorer.
  - Champs : id, slug, epoch, date (ISO), company, position, tags[] (très bruités : un poste RH
    peut être tagué "python"), description (HTML), location (texte libre, souvent vide ou ville du
    siège), salary_min/salary_max (0 = inconnu, USD/an), url, apply_url.
  - Encodage : une partie des textes arrive en mojibake (UTF-8 décodé en Latin-1) → réparé.
Contraintes (CGU) : lien retour obligatoire vers Remote OK et mention de la source → `url` = page
Remote OK. Flux rafraîchi lentement → MIN_INTERVAL_H = 6. Pré-filtre métier local indispensable.
"""
from __future__ import annotations

import re
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "remoteok"
LABEL = "Remote OK"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 6

API = "https://remoteok.com/api"

# Pré-filtre métier : config.json `prefilter` (voir scripts/prefilter.py), via ctx.prefilter.


def _fix(text: str | None) -> str:
    """Répare le mojibake « Ã© » → « é ». Sans effet sur un texte déjà correct
    (un vrai caractère non Latin-1 ou une séquence non UTF-8 fait échouer l'aller-retour)."""
    if not text:
        return ""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _contract(tags: list[str]) -> str:
    t = {x.lower().strip() for x in tags}
    if t & {"internship", "intern"}:
        return "stage"
    has_ct = bool(t & {"contract", "contractor", "freelance"})
    has_ft = bool(t & {"full time", "full-time", "permanent"})
    if has_ct and not has_ft:
        return "freelance"
    if has_ft and not has_ct:
        return "cdi"
    return "unknown"


def _to_job(raw: dict) -> Job | None:
    url = raw.get("url") or ""
    title = html_to_text(_fix(raw.get("position")))
    if not url or not title or not raw.get("id"):
        return None
    tags = [_fix(t) for t in raw.get("tags") or []]
    smin, smax = raw.get("salary_min") or 0, raw.get("salary_max") or 0
    # fourchettes fantaisistes fréquentes (10 000–750 000) : ignorées plutôt que de fausser le score
    salary_ok = smin > 0 and smax >= smin and smax <= smin * 4
    return Job(
        source=NAME,
        source_id=str(raw["id"]),
        title=title,
        company=html_to_text(_fix(raw.get("company"))),
        url=url,
        description=html_to_text(_fix(raw.get("description"))),
        remote="full",
        remote_scope=_fix(raw.get("location")).strip(" ,"),  # brut ; vide = non précisé
        country="FR" if re.search(r"\bfrance\b", _fix(raw.get("location")), re.I) else "",
        contract=_contract(tags),
        salary_min=float(smin) if salary_ok else None,
        salary_max=float(smax) if salary_ok else None,
        salary_period="year" if salary_ok else "",
        published_at=iso_date(raw.get("date") or raw.get("epoch")),
        tags=tags,
    )


def fetch(ctx: Context) -> Iterator[Job]:
    try:
        resp = ctx.http.get(API, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        ctx.log(f"[{NAME}] requête en échec : {exc}")
        return
    finally:
        polite_sleep()

    seen: set[str] = set()
    kept = 0
    for raw in data if isinstance(data, list) else []:
        if not isinstance(raw, dict) or "legal" in raw:  # avis légal en tête de tableau
            continue
        job = _to_job(raw)
        if job is None or job.uid in seen:
            continue
        age = age_days(job.published_at)
        if age is not None and age > ctx.max_age_days:
            continue
        if not ctx.prefilter.pertinent(job.title, job.tags, job.description):
            continue
        seen.add(job.uid)
        kept += 1
        yield job
        if kept >= ctx.per_query:
            return
