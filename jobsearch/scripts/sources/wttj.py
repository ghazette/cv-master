"""Welcome to the Jungle (WTTJ) — offres via l'index Algolia public du site.

Endpoints
---------
- GET  https://www.welcometothejungle.com/api/env
    Script chargé par la page /fr/jobs : ``window.env = {...}``. On y relit
    PUBLIC_ALGOLIA_APPLICATION_ID et PUBLIC_ALGOLIA_API_KEY_CLIENT (la clé de
    recherche publique qu'utilise le navigateur). Repli sur les valeurs connues.
- POST https://<app>-dsn.algolia.net/1/indexes/*/queries
    Multi-requêtes Algolia sur l'index ``wttj_jobs_production_fr`` (toutes langues).
- Offre publique : https://www.welcometothejungle.com/fr/companies/<organization.slug>/jobs/<slug>

Valeurs observées dans l'index (15/09/2026)
-------------------------------------------
- remote : fulltime | partial | punctual | no | unknown
- contract_type : full_time (= CDI) | temporary (= CDD) | internship | apprenticeship |
  freelance | part_time | vie | graduate_program | volunteer | idv | other
- salary_period : yearly | monthly | daily ; salary_currency : EUR | USD | GBP
- offices[] : city, district, state, country_code ; _geoloc[] : lat, lng (même ordre)
- Pas de description complète dans l'index : on assemble summary + key_missions
  + profile (+ avantages), sans appeler la page de chaque offre.

Stratégie (queries_fr, deux familles)
-------------------------------------
- géographique : aroundLatLng sur chaque lieu de `search_areas` (lat/lon, radius_km) ;
- full remote France : ``remote:fulltime AND offices.country_code:FR`` (si le remote est accepté).
Les offres plus vieilles que max_age_days sont exclues côté Algolia
(numericFilters sur published_at_timestamp, en secondes).
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Iterator
from urllib.parse import urlencode

import requests

from common import Context, Job, html_to_text, iso_date, polite_sleep

NAME = "wttj"
LABEL = "Welcome to the Jungle"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 4

SITE = "https://www.welcometothejungle.com"
ENV_URL = f"{SITE}/api/env"
INDEX = "wttj_jobs_production_fr"
# Valeurs relevées le 15/09/2026, utilisées si /api/env est illisible.
FALLBACK_APP_ID = "CSEKHVMS53"
FALLBACK_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"

REMOTE_FILTER = "remote:fulltime AND offices.country_code:FR"

REMOTE_MAP = {"fulltime": "full", "partial": "partial", "punctual": "partial", "no": "none"}
CONTRACT_MAP = {"full_time": "cdi", "temporary": "cdd", "freelance": "freelance",
                "internship": "stage", "apprenticeship": "alternance"}
PERIOD_MAP = {"yearly": "year", "monthly": "month", "daily": "day", "hourly": "hour"}

# Champs ramenés par Algolia (évite les gros blocs organization/_highlightResult).
ATTRIBUTES = [
    "objectID", "reference", "name", "slug", "organization.name", "organization.slug",
    "offices", "_geoloc", "remote", "contract_type", "salary_minimum", "salary_maximum",
    "salary_period", "salary_currency", "published_at", "summary", "key_missions",
    "profile", "benefits", "new_profession.pivot_name", "sectors.name",
]


def _read_credentials(ctx: Context) -> tuple[str, str]:
    """Relit app id + clé publique dans window.env ; repli sur les valeurs connues."""
    try:
        r = ctx.http.get(ENV_URL, timeout=20)
        r.raise_for_status()
        start = r.text.index("{", r.text.index("window.env"))
        env, _ = json.JSONDecoder().raw_decode(r.text[start:])
        return env["PUBLIC_ALGOLIA_APPLICATION_ID"], env["PUBLIC_ALGOLIA_API_KEY_CLIENT"]
    except (requests.RequestException, ValueError, KeyError) as e:
        ctx.log(f"wttj: clé Algolia non relue depuis {ENV_URL} ({e}), valeur connue utilisée")
        return FALLBACK_APP_ID, FALLBACK_API_KEY


class _Algolia:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.app_id, self.api_key = _read_credentials(ctx)

    def search(self, batch: list[dict[str, str]]) -> list[dict[str, Any]] | None:
        """Envoie un lot de requêtes ; réessaie une fois après relecture de la clé si 403."""
        for attempt in (1, 2):
            url = f"https://{self.app_id.lower()}-dsn.algolia.net/1/indexes/*/queries"
            headers = {
                "X-Algolia-Application-Id": self.app_id,
                "X-Algolia-API-Key": self.api_key,
                "Origin": SITE,
                "Referer": f"{SITE}/",
            }
            try:
                r = self.ctx.http.post(url, json={"requests": batch}, headers=headers, timeout=30)
            except requests.RequestException as e:
                self.ctx.log(f"wttj: échec Algolia ({e})")
                return None
            if r.status_code == 403 and attempt == 1:
                self.ctx.log("wttj: 403 Algolia, relecture de la clé publique")
                self.app_id, self.api_key = _read_credentials(self.ctx)
                continue
            if r.status_code != 200:
                self.ctx.log(f"wttj: HTTP {r.status_code} Algolia : {r.text[:200]}")
                return None
            try:
                return r.json().get("results") or []
            except ValueError:
                self.ctx.log("wttj: réponse Algolia non JSON")
                return None
        return None


def _params(query: str, per_query: int, cutoff_ts: int, **extra: Any) -> str:
    p: dict[str, Any] = {
        "query": query,
        "hitsPerPage": max(1, min(per_query, 1000)),
        "page": 0,
        "attributesToRetrieve": json.dumps(ATTRIBUTES),
        "attributesToHighlight": "[]",
        "attributesToSnippet": "[]",
        "numericFilters": f"published_at_timestamp>={cutoff_ts}",
        "analytics": "false",
    }
    p.update(extra)
    return urlencode(p)


def _nearest(points: list[dict[str, Any]], lat: float | None, lon: float | None) -> int:
    """Indice du point le plus proche de (lat, lon) ; 0 si pas de référence."""
    if lat is None or lon is None or len(points) < 2:
        return 0
    k = math.cos(math.radians(lat))
    dist = [((p["lat"] - lat) ** 2 + ((p["lng"] - lon) * k) ** 2) for p in points]
    return dist.index(min(dist))


def _to_job(hit: dict[str, Any], ref_lat: float | None, ref_lon: float | None) -> Job | None:
    org = hit.get("organization") or {}
    slug, org_slug = hit.get("slug"), org.get("slug")
    sid = hit.get("reference") or hit.get("objectID")
    if not (slug and org_slug and sid and hit.get("name")):
        return None

    # Plusieurs bureaux possibles : on garde les coordonnées du plus proche de la
    # référence (centre de recherche ou domicile), le libellé cite les autres.
    offices = hit.get("offices") or []
    geolocs = hit.get("_geoloc") or []
    if isinstance(geolocs, dict):
        geolocs = [geolocs]
    geolocs = [g for g in geolocs if g.get("lat") is not None and g.get("lng") is not None]
    lat = lon = None
    office = offices[0] if offices else {}
    if geolocs:
        i = _nearest(geolocs, ref_lat, ref_lon)
        lat, lon = geolocs[i]["lat"], geolocs[i]["lng"]
        if len(geolocs) == len(offices):
            office = offices[i]
    label = ", ".join(x for x in (office.get("city"), office.get("district")) if x)
    others = sorted({o.get("city") for o in offices if o.get("city") and o is not office})
    if others:
        label += f" (+ {', '.join(others)})"
    codes = {o.get("country_code") for o in offices}
    country = "FR" if "FR" in codes else (office.get("country_code") or "")

    # Salaire : seulement en euros, faute de champ devise dans Job.
    smin = smax = None
    period = PERIOD_MAP.get(hit.get("salary_period") or "", "")
    if period and hit.get("salary_currency") in (None, "EUR"):
        smin, smax = hit.get("salary_minimum"), hit.get("salary_maximum")
        if smin is None and smax is None:
            period = ""
    else:
        period = ""

    parts = []
    if hit.get("summary"):
        parts.append(str(hit["summary"]).strip())
    missions = [m.strip() for m in hit.get("key_missions") or [] if m and m.strip()]
    if missions:
        parts.append("Missions clés :\n" + "\n".join(f"- {m}" for m in missions))
    profile = html_to_text(hit.get("profile"))
    if profile:
        parts.append("Profil recherché :\n" + profile)
    if hit.get("benefits"):
        parts.append("Avantages : " + " ; ".join(hit["benefits"]))

    tags = []
    pivot = (hit.get("new_profession") or {}).get("pivot_name")
    if pivot:
        tags.append(pivot)
    tags += [s["name"] for s in hit.get("sectors") or [] if s.get("name")]

    return Job(
        source=NAME,
        source_id=str(sid),
        title=hit["name"].strip(),
        company=(org.get("name") or "").strip(),
        url=f"{SITE}/fr/companies/{org_slug}/jobs/{slug}",
        description="\n\n".join(parts),
        location=label,
        lat=lat,
        lon=lon,
        country=country,
        remote=REMOTE_MAP.get(hit.get("remote") or "", "unknown"),
        contract=CONTRACT_MAP.get(hit.get("contract_type") or "", "unknown"),
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        published_at=iso_date(hit.get("published_at")),
        tags=tags,
    )


def fetch(ctx: Context) -> Iterator[Job]:
    algolia = _Algolia(ctx)
    cutoff = int(time.time() - ctx.max_age_days * 86400)
    home = ctx.config.get("home") or {}
    areas = [a for a in ctx.areas if a.get("lat") is not None and a.get("lon") is not None]
    for a in ctx.areas:
        if a not in areas:
            ctx.log(f"wttj: « {a['name']} » sans coordonnées (init.py --geocode), ignoré")
    seen: set[str] = set()
    ok = failed = 0

    for n, query in enumerate(ctx.queries_fr):
        if n:
            polite_sleep()
        # Un POST par requête texte, regroupant les variantes (un lieu de recherche chacune, puis remote).
        variants: list[tuple[dict[str, str], float | None, float | None]] = []
        for area in areas:
            params = _params(query, ctx.per_query, cutoff, aroundLatLng=f"{area['lat']},{area['lon']}",
                             aroundRadius=int(area["radius_km"] * 1000))
            variants.append(({"indexName": INDEX, "params": params}, area["lat"], area["lon"]))
        if ctx.remote_wanted:
            params = _params(query, ctx.per_query, cutoff, filters=REMOTE_FILTER)
            variants.append(({"indexName": INDEX, "params": params}, home.get("lat"), home.get("lon")))
        if not variants:
            break

        results = algolia.search([v[0] for v in variants])
        if results is None:
            failed += 1
            continue
        ok += 1
        for (_req, ref_lat, ref_lon), res in zip(variants, results):
            for hit in res.get("hits") or []:
                job = _to_job(hit, ref_lat, ref_lon)
                if job is None or job.source_id in seen:
                    continue
                seen.add(job.source_id)
                yield job

    if failed and not ok:
        raise RuntimeError("wttj: aucune requête Algolia n'a abouti")
