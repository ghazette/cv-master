"""France Travail : API Offres d'emploi v2.

Catalogue : https://francetravail.io/data/api/offres-emploi (la doc Swagger s'ouvre après connexion)
Débit     : 10 appels/s annoncés sur le catalogue ; on reste très en dessous.

Auth OAuth2 client_credentials. L'URL a été vérifiée : avec de faux identifiants elle répond
HTTP 400 {"error":"invalid_client"} :
    POST https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire
    form : grant_type=client_credentials, client_id, client_secret, scope="api_offresdemploiv2 o2dsoffre"
    -> {"access_token": "...", "token_type": "Bearer", "expires_in": 1499, "scope": "api_offresdemploiv2 o2dsoffre"}

Recherche :
    GET https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search   (Authorization: Bearer)
    motsCles       mots-clés séparés par des virgules, 2 caractères min chacun
    commune        code INSEE, jusqu'à 5 séparés par virgule ; distance = rayon en km autour
    departement    jusqu'à 5 ; region ; inclureLimitrophes
    typeContrat    CDI, CDD, MIS, LIB... (référentiel : GET .../offresdemploi/v2/referentiel/typesContrats)
    publieeDepuis  offres publiées depuis au plus X jours (ou minCreationDate/maxCreationDate)
    sort           0 pertinence, 1 date décroissante, 2 distance croissante
    range          "p-d", 150 résultats max par page, index max 3000
    Statuts : 200 tout est renvoyé ; 206 résultat partiel, paginer via range
              (en-tête Content-Range « offres 0-149/1247 ») ; 204 aucun résultat.
    Sans jeton valide : HTTP 401, corps vide (vérifié).

Recoupé avec : le SDK PyPI « france-travail-job-offers » (2026), le serveur GitHub
« francetravail-mcp » (2026), le dépôt creach-t/job-search-france-travail-api, et des sondes HTTP.

Télétravail : le schéma documenté n'a ni filtre ni champ structuré, donc remote="unknown".
La famille « remote » cherche avec le mot-clé « télétravail » sur toute la France.
"""
from __future__ import annotations

import re
import time
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "francetravail"
LABEL = "France Travail"
KIND = "api"
REQUIRES = ["FRANCETRAVAIL_CLIENT_ID", "FRANCETRAVAIL_CLIENT_SECRET"]
MIN_INTERVAL_H = 6

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
DETAIL_URL = "https://candidat.francetravail.fr/offres/recherche/detail/{id}"
SCOPE = "api_offresdemploiv2 o2dsoffre"

PAGE_SIZE_MAX = 150
INDEX_MAX = 3000
MAX_PAGES = 2
PAUSE_S = 0.5

# Paliers usuels de publieeDepuis, ceux du site candidat. Le SDK dit seulement « X jours » :
# à confirmer avec une vraie clé (un 400 est journalisé).
PUBLIEE_DEPUIS = (1, 3, 7, 14, 31)

# Famille (a) : un appel par lieu de recherche de la config (search_areas), sur le code INSEE
# de la commune (complété par `init.py --geocode`) et son rayon ; à défaut, le département.
# Famille (b) : mot-clé « télétravail » sur toute la France, si le remote est accepté.

# typeContrat -> contrat commun. CDI, CDD, MIS et LIB ont été vus dans les sources consultées ;
# SAI (saisonnier), DIN (CDI intérimaire), TTI et DDI (insertion) sont tirés du référentiel,
# à recouper avec /referentiel/typesContrats. FRA (franchise) et CCE restent en "unknown".
CONTRACT = {
    "CDI": "cdi", "CDD": "cdd", "MIS": "interim", "LIB": "freelance",
    "SAI": "cdd", "DDI": "cdd", "DIN": "interim", "TTI": "interim",
}

_SALARY_PERIOD = {"annuel": "year", "mensuel": "month", "journalier": "day", "horaire": "hour"}
_EUROS = re.compile(r"(\d+(?:[.,]\d+)?)\s*euros", re.I)

# Extrait de réponse attendue, reconstitué d'après le modèle documenté (champs réels, valeurs illustratives).
# Enveloppe : {"resultats": [...], "filtresPossibles": [{"filtre": "typeContrat", "agregation": [...]}]}
_SAMPLE_ITEM: dict[str, Any] = {
    "id": "048KLTP",
    "intitule": "Développeur Full Stack (H/F)",
    "description": "Au sein de l'équipe produit, vous développez...<br>Télétravail partiel possible.",
    "dateCreation": "2026-09-10T08:15:42.000Z",
    "dateActualisation": "2026-09-12T09:01:10.000Z",
    "lieuTravail": {"libelle": "44 - NANTES", "latitude": 47.2184, "longitude": -1.5536,
                    "codePostal": "44000", "commune": "44109"},
    "romeCode": "M1805",
    "romeLibelle": "Études et développement informatique",
    "entreprise": {"nom": "ACME SAS", "entrepriseAdaptee": False},
    "typeContrat": "CDI",
    "typeContratLibelle": "Contrat à durée indéterminée",
    "natureContrat": "Contrat travail",
    "experienceExige": "E",
    "experienceLibelle": "3 An(s)",
    "competences": [{"code": "300210", "libelle": "Développer une application web", "exigence": "S"}],
    "salaire": {"libelle": "Annuel de 45000.0 Euros à 55000.0 Euros sur 12.0 mois"},
    "dureeTravailLibelleConverti": "Temps plein",
    "alternance": False,
    "nombrePostes": 1,
    "origineOffre": {"origine": "1",
                     "urlOrigine": "https://candidat.francetravail.fr/offres/recherche/detail/048KLTP"},
}

# Jeton en mémoire, par client_id : (access_token, epoch d'expiration)
_tokens: dict[str, tuple[str, float]] = {}


class _BadRequest(Exception):
    pass


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _salary(salaire: dict[str, Any] | None) -> tuple[float | None, float | None, str]:
    """« Annuel de 45000.0 Euros à 55000.0 Euros sur 12.0 mois » -> (45000, 55000, "year")."""
    libelle = (salaire or {}).get("libelle") or ""
    period = _SALARY_PERIOD.get(libelle.split(" ", 1)[0].lower(), "") if libelle else ""
    values = [float(v.replace(",", ".")) for v in _EUROS.findall(libelle)]
    if not period or not values:
        return None, None, ""
    return min(values), max(values), period


def _parse(item: dict[str, Any]) -> Job:
    oid = str(item.get("id") or "")
    lieu = item.get("lieuTravail") or {}
    code = str(item.get("typeContrat") or "").upper()
    smin, smax, period = _salary(item.get("salaire"))

    tags = [t for t in (item.get("romeLibelle"), item.get("typeContratLibelle"),
                        item.get("dureeTravailLibelleConverti"), item.get("experienceLibelle")) if t]
    tags += [c["libelle"] for c in item.get("competences") or [] if c.get("libelle")]

    return Job(
        source=NAME,
        source_id=oid,
        title=html_to_text(item.get("intitule")),
        company=html_to_text((item.get("entreprise") or {}).get("nom")),
        # urlOrigine pointe vers le site du partenaire pour les offres partenaires
        url=(item.get("origineOffre") or {}).get("urlOrigine") or DETAIL_URL.format(id=oid),
        description=html_to_text(item.get("description")),
        location=lieu.get("libelle") or "",
        lat=_num(lieu.get("latitude")),
        lon=_num(lieu.get("longitude")),
        country="FR",
        contract="alternance" if item.get("alternance") else CONTRACT.get(code, "unknown"),
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        published_at=iso_date(item.get("dateCreation")),
        tags=tags,
    )


def _get_token(ctx: Context, force: bool = False) -> str:
    client_id = ctx.env["FRANCETRAVAIL_CLIENT_ID"]
    cached = _tokens.get(client_id)
    if cached and not force and cached[1] > time.time():
        return cached[0]
    try:
        r = ctx.http.post(TOKEN_URL, params={"realm": "/partenaire"}, timeout=30, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": ctx.env["FRANCETRAVAIL_CLIENT_SECRET"],
            "scope": SCOPE,
        })
    except requests.RequestException as exc:
        raise RuntimeError(f"France Travail : serveur d'authentification injoignable ({exc})") from exc
    if r.status_code in (400, 401, 403):
        raise RuntimeError(
            f"France Travail : authentification refusée (HTTP {r.status_code} : {r.text[:200]}). "
            "Vérifier FRANCETRAVAIL_CLIENT_ID / FRANCETRAVAIL_CLIENT_SECRET et que l'application "
            f"francetravail.io est abonnée à « API Offres d'emploi v2 » (scopes : {SCOPE}).")
    r.raise_for_status()
    data = r.json()
    # marge de 60 s pour ne pas utiliser un jeton qui expire pendant la requête
    _tokens[client_id] = (data["access_token"], time.time() + int(data.get("expires_in", 1499)) - 60)
    return data["access_token"]


def _search(ctx: Context, params: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Renvoie (statut HTTP, offres). Un 401 déclenche un seul renouvellement du jeton."""
    for attempt in (1, 2):
        token = _get_token(ctx, force=attempt == 2)
        r = ctx.http.get(SEARCH_URL, params=params, timeout=30,
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        if r.status_code != 401:
            break
    if r.status_code == 401:
        raise RuntimeError("France Travail : jeton refusé par l'API Offres (HTTP 401) alors que "
                           "l'authentification a réussi. L'application est-elle abonnée à « API Offres d'emploi v2 » ?")
    if r.status_code == 204:
        return 204, []
    if r.status_code == 400:
        raise _BadRequest(r.text[:300])
    r.raise_for_status()
    return r.status_code, r.json().get("resultats") or []


def _search_tolerant(ctx: Context, params: dict[str, Any], label: str) -> tuple[int, list[dict[str, Any]]] | None:
    """Sur un 400, réessaie une fois avec des mots-clés sans ponctuation (« vue.js » -> « vue js »)."""
    try:
        return _search(ctx, params)
    except _BadRequest as exc:
        clean = re.sub(r"[^\w\s-]", " ", params.get("motsCles", "")).strip()
        clean = re.sub(r"\s+", " ", clean)
        if clean == params.get("motsCles"):
            ctx.log(f"[{NAME}] requête invalide « {label} » (HTTP 400) : {exc}")
            return None
        ctx.log(f"[{NAME}] HTTP 400 sur « {label} », nouvel essai avec motsCles={clean!r}")
        try:
            return _search(ctx, {**params, "motsCles": clean})
        except _BadRequest as exc2:
            ctx.log(f"[{NAME}] requête invalide « {label} » (HTTP 400) : {exc2}")
            return None


def _geo_params(area: dict[str, Any]) -> dict[str, Any] | None:
    if area.get("insee"):
        return {"commune": area["insee"], "distance": int(area["radius_km"])}
    if area.get("department"):
        return {"departement": area["department"]}
    return None


def _plan(ctx: Context) -> Iterator[tuple[str, dict[str, Any]]]:
    geo = []
    for area in ctx.areas:
        params = _geo_params(area)
        if params is None:
            ctx.log(f"[{NAME}] « {area['name']} » sans code INSEE ni département (init.py --geocode), ignoré")
        else:
            geo.append((area["name"], params))
    for q in ctx.queries_fr:
        for label, params in geo:
            yield f"{q} @ {label}", {"motsCles": q, **params}
        if ctx.remote_wanted:
            yield f"{q} @ télétravail FR", {"motsCles": f"{q} télétravail"}


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()
    page_size = max(1, min(ctx.per_query, PAGE_SIZE_MAX))
    since = next((d for d in PUBLIEE_DEPUIS if d >= ctx.max_age_days), PUBLIEE_DEPUIS[-1])
    first_call = True

    for label, params in _plan(ctx):
        kept = 0
        for page in range(MAX_PAGES):
            start = page * page_size
            if start >= INDEX_MAX:
                break
            if not first_call:
                polite_sleep(PAUSE_S)
            first_call = False
            query = {**params, "publieeDepuis": since, "sort": 1,
                     "range": f"{start}-{min(start + page_size, INDEX_MAX) - 1}"}
            try:
                result = _search_tolerant(ctx, query, label)
            except (requests.RequestException, ValueError) as exc:
                ctx.log(f"[{NAME}] échec « {label} » (range {query['range']}) : {exc}")
                break
            if result is None:
                break
            status, items = result

            for item in items:
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
            # 206 = il reste des résultats au-delà de ce range
            if status != 206 or kept >= ctx.per_query or len(items) < page_size:
                break
