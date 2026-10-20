"""Adzuna : API de recherche d'offres, marché français.

Endpoint : GET https://api.adzuna.com/v1/api/jobs/fr/search/{page}
Doc      : https://developer.adzuna.com/docs/search
           https://developer.adzuna.com/activedocs (spec Swagger 1.2 : https://api.adzuna.com/v1/api-docs/adzuna)
Quotas   : 250 appels/jour et 2 500/mois par défaut
           (https://developer.adzuna.com/docs/terms_of_service)

Paramètres utilisés, vérifiés dans la spec : app_id, app_key (query), what (mots-clés),
where (lieu ou code postal), distance (km autour de `where`, 10 par défaut), max_days_old,
results_per_page, sort_by. `permanent=1` et `contract=1` existent mais on ne filtre pas
le contrat ici, c'est le rôle du module central.

Pas de filtre télétravail natif : la famille « remote » ajoute « télétravail » aux mots-clés
et cherche sur toute la France (sans `where`).

Erreur d'auth (vérifiée avec une fausse clé) :
    HTTP 401 {"__CLASS__":"Adzuna::API::Response::Exception","exception":"AUTH_FAIL",
              "doc":"https://api.adzuna.com/v1/doc","display":"Authorisation failed"}
"""
from __future__ import annotations

from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "adzuna"
LABEL = "Adzuna"
KIND = "api"
REQUIRES = ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"]
# 6 requêtes x 3 familles = 18 appels par run ; toutes les 12 h, ça fait ~36/jour et ~1 100/mois.
MIN_INTERVAL_H = 12

API = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"
PAGE_SIZE_MAX = 50       # au-delà, Adzuna tronque ; on reste bas de toute façon
MAX_PAGES = 2            # garde-fou sur le nombre d'appels par requête
PAUSE_S = 2.5            # < 25 appels/minute

# Famille (a) : lieux de recherche de la config (search_areas : commune et rayon en km).

# contract_type : "permanent" | "contract" (spec). "contract" regroupe CDD, missions et
# freelance sans distinction : on le laisse à "unknown" (valeur brute gardée dans tags).
CONTRACT = {"permanent": "cdi"}

# Extrait de réponse attendue (doc https://developer.adzuna.com/docs/search) :
_SAMPLE_ITEM: dict[str, Any] = {
    "__CLASS__": "Adzuna::API::Response::Job",
    "id": "129698749",
    "title": "Javascript Developer",
    "description": "JavaScript Developer Corporate ...",
    "created": "2013-11-08T18:07:39Z",
    "redirect_url": "http://adzuna.co.uk/jobs/land/ad/129698749...",
    "latitude": 51.571999,
    "longitude": -0.776902,
    "location": {"__CLASS__": "Adzuna::API::Response::Location",
                 "area": ["UK", "South East England", "Buckinghamshire", "Marlow"],
                 "display_name": "Marlow, Buckinghamshire"},
    "company": {"__CLASS__": "Adzuna::API::Response::Company",
                "display_name": "Corporate Project Solutions"},
    "category": {"__CLASS__": "Adzuna::API::Response::Category", "label": "IT Jobs", "tag": "it-jobs"},
    "salary_min": 50000,
    "salary_max": 55000,
    "salary_is_predicted": 0,
    "contract_type": "permanent",
    # "contract_time": "full_time" (champ optionnel)
}
# Enveloppe : {"__CLASS__": "Adzuna::API::Response::JobSearchResults", "count": 1234, "mean": ..., "results": [...]}


class _QuotaExceeded(Exception):
    pass


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse(item: dict[str, Any]) -> Job:
    company = (item.get("company") or {}).get("display_name") or ""
    loc = item.get("location") or {}
    contract_type = item.get("contract_type") or ""

    # Salaire estimé par Adzuna (salary_is_predicted=1) : ce n'est pas l'employeur qui le donne, on l'ignore.
    predicted = str(item.get("salary_is_predicted", "0")) == "1"
    smin = None if predicted else _num(item.get("salary_min"))
    smax = None if predicted else _num(item.get("salary_max"))

    tags = [t for t in ((item.get("category") or {}).get("label"), contract_type, item.get("contract_time")) if t]
    return Job(
        source=NAME,
        source_id=str(item.get("id") or ""),
        title=html_to_text(item.get("title")),
        company=html_to_text(company),
        url=item.get("redirect_url") or "",
        # full_description n'est présent que sur certains comptes ; description est tronquée à 500 caractères.
        description=html_to_text(item.get("full_description") or item.get("description")),
        location=loc.get("display_name") or ", ".join(loc.get("area") or []),
        lat=_num(item.get("latitude")),
        lon=_num(item.get("longitude")),
        country="FR",  # endpoint /jobs/fr/
        contract=CONTRACT.get(contract_type, "unknown"),
        salary_min=smin,
        salary_max=smax,
        salary_period="year" if (smin or smax) else "",  # Adzuna normalise les salaires en annuel
        published_at=iso_date(item.get("created")),
        tags=tags,
    )


def _plan(ctx: Context) -> Iterator[tuple[str, dict[str, Any]]]:
    for q in ctx.queries_fr:
        for area in ctx.areas:
            yield f"{q} @ {area['name']}", {"what": q, "where": area["city"], "distance": int(area["radius_km"])}
        if ctx.remote_wanted:
            yield f"{q} @ télétravail FR", {"what": f"{q} télétravail"}


def _search(ctx: Context, params: dict[str, Any], page: int) -> dict[str, Any]:
    query = {
        "app_id": ctx.env["ADZUNA_APP_ID"],
        "app_key": ctx.env["ADZUNA_APP_KEY"],
        "max_days_old": ctx.max_age_days,
        "sort_by": "date",
        "content-type": "application/json",
        **params,
    }
    r = ctx.http.get(API.format(page=page), params=query, timeout=30)
    if r.status_code == 401:
        raise RuntimeError(f"Adzuna : authentification refusée (HTTP 401, {r.text[:200]}). "
                           "Vérifier ADZUNA_APP_ID / ADZUNA_APP_KEY sur https://developer.adzuna.com/admin/access_details")
    if r.status_code == 429:
        raise _QuotaExceeded(r.text[:200])
    r.raise_for_status()
    return r.json()


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()
    page_size = max(1, min(ctx.per_query, PAGE_SIZE_MAX))
    first_call = True

    for label, params in _plan(ctx):
        kept = 0
        for page in range(1, MAX_PAGES + 1):
            if not first_call:
                polite_sleep(PAUSE_S)
            first_call = False
            try:
                data = _search(ctx, {**params, "results_per_page": page_size}, page)
            except _QuotaExceeded as exc:
                ctx.log(f"[{NAME}] quota atteint (HTTP 429), arrêt de la collecte : {exc}")
                return
            except (requests.RequestException, ValueError) as exc:
                ctx.log(f"[{NAME}] échec « {label} » page {page} : {exc}")
                break

            results = data.get("results") or []
            for item in results:
                job = _parse(item)
                if not job.source_id or job.source_id in seen:
                    continue
                age = age_days(job.published_at)
                if age is not None and age > ctx.max_age_days:
                    continue
                seen.add(job.source_id)
                kept += 1
                yield job
                if kept >= ctx.per_query:
                    break
            if kept >= ctx.per_query or len(results) < page_size:
                break
