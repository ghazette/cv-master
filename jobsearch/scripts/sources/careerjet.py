"""Careerjet : API de recherche v4 (programme éditeurs).

Endpoint : GET https://search.api.careerjet.net/v4/query
Doc      : https://www.careerjet.com/partners/api (exemple curl : https://www.careerjet.com/partners/api/curl)
Clé      : compte éditeur, https://www.careerjet.com/partners/register/as-publisher

Auth : HTTP Basic, identifiant = clé API, mot de passe vide.
Paramètres (doc v4) :
    user_ip, user_agent   OBLIGATOIRES : IP et user-agent de l'utilisateur final
    locale_code           ex. fr_FR (en_GB par défaut)
    keywords, location    location vide = tout le pays de la locale
    radius                entier, km ou miles selon le pays (5 par défaut)
    contract_type         p (permanent) | c (contract) | t (temporary) | i (internship) | v (volunteering)
    work_hours            f | p
    sort                  relevance | date | salary
    page (1-10), page_size (1-100, 20 par défaut), offset, fragment_size (extrait, 120 car. par défaut)

Réponse : {"type": "JOBS", "hits": 62, "message": "...", "pages": 4, "response_time": 0.3, "jobs": [...]}
Erreurs documentées : 400 « Unsupported locale code », 403 « Missing param user_ip or user_agent ».
Constaté avec une fausse clé : 401 {"error": "Invalid API key provided", "type": "ERROR"}.

user_ip : on n'a pas d'« utilisateur final » ; on envoie l'IP publique IPv4 de la machine
(https://api.ipify.org), ou CAREERJET_USER_IP si défini dans le .env, sinon 127.0.0.1.
Quota : non documenté. On reste sobre (pause entre appels, MIN_INTERVAL_H = 12).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "careerjet"
LABEL = "Careerjet"
KIND = "api"
REQUIRES = ["CAREERJET_API_KEY"]
MIN_INTERVAL_H = 12

API = "https://search.api.careerjet.net/v4/query"
LOCALE = "fr_FR"
PAGE_SIZE_MAX = 100
MAX_PAGES = 2
FRAGMENT_SIZE = 600      # extrait plus long que les 120 caractères par défaut, utile au scoring
PAUSE_S = 1.5

# Famille (a) : lieux de recherche de la config (search_areas : commune et rayon en km).

# salary_type (doc) -> période du contrat commun. W (hebdo) n'a pas d'équivalent : montant ignoré.
SALARY_PERIOD = {"Y": "year", "M": "month", "D": "day", "H": "hour"}

# Extrait de réponse attendue (doc https://www.careerjet.com/partners/api, section « Job structure ») :
_SAMPLE_ITEM: dict[str, Any] = {
    "title": "Python Developer",
    "company": "NBC",
    "date": "Wed,15 Nov 2025 19:13:43 GMT",
    "description": "Job description excerpt",
    "locations": "London",
    "salary": "$30000 - 33000",
    "salary_currency_code": "USD",
    "salary_max": 33000.0,
    "salary_min": 30000.0,
    "salary_type": "Y",
    "url": "https://jobviewtrack.com/v2/unique link",
}

_IPV4 = re.compile(r"\d{1,3}(\.\d{1,3}){3}")
_ip_cache: dict[str, str] = {}


def _user_ip(ctx: Context) -> str:
    if ctx.env.get("CAREERJET_USER_IP"):
        return ctx.env["CAREERJET_USER_IP"]
    if "ip" not in _ip_cache:
        ip = ""
        try:
            r = ctx.http.get("https://api.ipify.org", timeout=10)
            if r.ok and _IPV4.fullmatch(r.text.strip()):
                ip = r.text.strip()
        except requests.RequestException:
            pass
        _ip_cache["ip"] = ip or "127.0.0.1"
    return _ip_cache["ip"]


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse(item: dict[str, Any]) -> Job:
    title = html_to_text(item.get("title"))
    company = html_to_text(item.get("company"))
    locations = html_to_text(item.get("locations"))

    # Pas d'identifiant dans la réponse, et l'URL est un lien de tracking qui peut varier
    # d'un appel à l'autre : on dérive un id stable du triplet titre/entreprise/lieu.
    sid = hashlib.sha1(f"{title}|{company}|{locations}".lower().encode()).hexdigest()[:16]

    period = SALARY_PERIOD.get(str(item.get("salary_type") or "").upper(), "")
    return Job(
        source=NAME,
        source_id=sid,
        title=title,
        company=company,
        url=item.get("url") or "",
        description=html_to_text(item.get("description")),
        location=locations,
        country="FR",  # locale fr_FR
        salary_min=_num(item.get("salary_min")) if period else None,
        salary_max=_num(item.get("salary_max")) if period else None,
        salary_period=period,
        published_at=iso_date(item.get("date")),
        tags=[t for t in (item.get("salary"),) if t],
    )


def _plan(ctx: Context) -> Iterator[tuple[str, dict[str, Any]]]:
    for q in ctx.queries_fr:
        for area in ctx.areas:
            yield f"{q} @ {area['name']}", {"keywords": q, "location": area["city"],
                                            "radius": int(area["radius_km"])}
        if ctx.remote_wanted:
            # location absente = tout le pays de la locale
            yield f"{q} @ télétravail FR", {"keywords": f"{q} télétravail"}


def _search(ctx: Context, params: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    query = {
        "locale_code": LOCALE,
        "sort": "date",
        "page": page,
        "page_size": page_size,
        "fragment_size": FRAGMENT_SIZE,
        "user_ip": _user_ip(ctx),
        "user_agent": ctx.http.headers.get("User-Agent", "Mozilla/5.0"),
        **params,
    }
    headers = {"Accept": "application/json"}
    if ctx.env.get("CAREERJET_REFERER"):  # URL de la page « éditeur », si Careerjet l'exige
        headers["Referer"] = ctx.env["CAREERJET_REFERER"]
    r = ctx.http.get(API, params=query, headers=headers, auth=(ctx.env["CAREERJET_API_KEY"], ""), timeout=30)
    if r.status_code in (400, 401, 403):
        # clé refusée, locale non supportée, user_ip/user_agent manquants : aucune requête ne passera
        detail = " ".join(r.text[:300].split())
        raise RuntimeError(f"Careerjet : requête refusée (HTTP {r.status_code} : {detail}). "
                           "Vérifier CAREERJET_API_KEY (auth Basic, mot de passe vide) et les paramètres obligatoires.")
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
                data = _search(ctx, params, page, page_size)
            except (requests.RequestException, ValueError) as exc:
                ctx.log(f"[{NAME}] échec « {label} » page {page} : {exc}")
                break

            if data.get("type") != "JOBS":
                # ex. lieu ambigu (type "LOCATIONS" dans l'ancienne API) ou erreur applicative
                ctx.log(f"[{NAME}] réponse inattendue pour « {label} » : type={data.get('type')} {str(data)[:200]}")
                break

            jobs = data.get("jobs") or []
            for item in jobs:
                job = _parse(item)
                if job.source_id in seen:
                    continue
                age = age_days(job.published_at)
                if age is not None and age > ctx.max_age_days:
                    continue
                seen.add(job.source_id)
                kept += 1
                yield job
                if kept >= ctx.per_query:
                    break
            if kept >= ctx.per_query or page >= int(data.get("pages") or 1):
                break
