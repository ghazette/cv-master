"""APEC — offres cadres, via le webservice JSON (non documenté) du site apec.fr.

Endpoints (relevés dans le bundle Angular offres/dist/main-*.js le 15/09/2026)
------------------------------------------------------------------------------
- POST https://www.apec.fr/cms/webservices/rechercheOffre
    Corps (RechercheOffreCriteriaDto ; un champ inconnu → HTTP 500) :
      motsCles, lieux[] (ids texte), typesContrat[] (ids), typesTeletravail[] (ids),
      pointGeolocDeReference {latitude, longitude, distance (km)} — rayon actif
      seulement si `lieux` contient une commune —, typeClient="CADRE",
      sorts=[{type: "DATE", direction: "DESCENDING"}], pagination {range, startIndex},
      activeFiltre=true.
    Réponse : totalCount, offreFilters (facettes), resultats[] {id, numeroOffre, intitule,
      nomCommercial, lieuTexte, salaireTexte, texteOffre (extrait ~280 caractères),
      datePublication, latitude, longitude, typeContrat, idNomTeletravail}.
- GET /cms/webservices/referentielstatique/presentations/code/<CODE>/visuels
    Référentiels : LISTE_OPTIONS_TELETRAVAIL, RECHERCHE_OFFRE_TYPE_CONTRAT.
- GET /cms/webservices/autocompletion/lieuautocomplete?q=<texte>
    Réponse : [{lieuDisplay "Nantes - 44", lieuId 577013, lieuType FR_COMMUNE, latitude, longitude,
    citycode (INSEE), lieuxParentsIds ["44", "717"]}]. Ids : département = son numéro ("44", "7"),
    commune = lieuId. Le module résout chaque lieu de `search_areas` par son code postal (ou son
    nom) au début de la collecte ; à défaut, il cherche sur le département.
- Détail : GET /cms/webservices/offre/public?numeroOffre=<n> existe mais renvoie un
  captcha DataDome (403) hors navigateur → description limitée à l'extrait `texteOffre`.
- Offre publique : https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/<numeroOffre>

Pas de freelance sur l'APEC : on demande les CDI (et les CDD si la config les accepte).
"""
from __future__ import annotations

import re
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "apec"
LABEL = "APEC"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 12      # webservice sous DataDome : on reste discret

SITE = "https://www.apec.fr"
SEARCH_URL = f"{SITE}/cms/webservices/rechercheOffre"
OFFER_URL = f"{SITE}/candidat/recherche-emploi.html/emploi/detail-offre/{{}}"

CDI = 101888
CDD = 101887
TELETRAVAIL_TOTAL = 20767
LIEU_URL = f"{SITE}/cms/webservices/autocompletion/lieuautocomplete"

CONTRACT_MAP = {
    101888: "cdi", 101887: "cdd", 597171: "stage",
    101930: "interim", 101889: "interim", 597141: "interim",
    20053: "alternance", 597137: "alternance", 597138: "alternance",
    597139: "alternance", 597140: "alternance",
}
REMOTE_MAP = {20767: "full", 20765: "partial", 20766: "partial", 20949: "none"}

_DEPT = re.compile(r" - (\d{2}|2[AB]|97\d)$")
_TZ = re.compile(r"([+-]\d{2})(\d{2})$")


def _payload(query: str, start: int, size: int, contracts: list[int], **criteria: Any) -> dict[str, Any]:
    return {
        "motsCles": query,
        "lieux": [],
        "typesContrat": contracts,
        "typesTeletravail": [],
        "typeClient": "CADRE",
        "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
        "pagination": {"range": size, "startIndex": start},
        "activeFiltre": True,
        **criteria,
    }


def _lieu(ctx: Context, area: dict[str, Any]) -> dict[str, Any] | None:
    """Critères géographiques APEC d'un lieu de recherche : commune + rayon, sinon département."""
    for q in (area.get("postcode"), area.get("city")):
        if not q:
            continue
        try:
            hits = ctx.http.get(LIEU_URL, params={"q": q}, timeout=20).json()
        except (requests.RequestException, ValueError):
            hits = []
        for h in hits if isinstance(hits, list) else []:
            if h.get("lieuType") == "FR_COMMUNE" and (not area.get("insee") or h.get("citycode") == area["insee"]):
                lat, lon = area.get("lat") or h.get("latitude"), area.get("lon") or h.get("longitude")
                return {"lieux": [str(h["lieuId"])],
                        "pointGeolocDeReference": {"latitude": lat, "longitude": lon,
                                                   "distance": int(area["radius_km"])}}
        polite_sleep(1)
    if area.get("department"):
        return {"lieux": [str(area["department"]).lstrip("0") or "0"]}
    return None


def _search(ctx: Context, query: str, criteria: dict[str, Any], contracts: list[int]) -> list[dict[str, Any]] | None:
    """Jusqu'à per_query offres, triées par date ; None si la première page échoue."""
    results: list[dict[str, Any]] = []
    size = max(1, min(ctx.per_query, 100))
    while len(results) < ctx.per_query:
        if results:
            polite_sleep(2)
        try:
            r = ctx.http.post(SEARCH_URL, json=_payload(query, len(results), size, contracts, **criteria),
                              headers={"Accept": "application/json",
                                       "Referer": f"{SITE}/candidat/recherche-emploi.html/emploi"},
                              timeout=30)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            ctx.log(f"apec: échec « {query} » {criteria} ({e})")
            return results or None
        batch = data.get("resultats") or []
        results += batch
        if len(batch) < size or len(results) >= (data.get("totalCount") or 0):
            break
        # Tri par date : on s'arrête dès que la page dépasse la limite d'âge.
        oldest = age_days(_date(batch[-1].get("datePublication")))
        if oldest is not None and oldest > ctx.max_age_days:
            break
    return results[: ctx.per_query]


def _date(value: Any) -> str:
    """APEC renvoie « 2026-09-08T09:55:47.000+0000 », que fromisoformat (3.10) refuse."""
    return iso_date(_TZ.sub(r"\1:\2", value) if isinstance(value, str) else value)


def _salary(text: str | None) -> tuple[float | None, float | None, str]:
    """« 45 - 55 k€ brut annuel », « A partir de 35 k€ brut annuel », « A négocier »."""
    t = (text or "").lower().replace(" ", " ").replace("\xa0", " ")
    nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", t.replace(" ", ""))]
    if "annuel" in t or "/an" in t:
        period = "year"
    elif "mensuel" in t or "mois" in t:
        period = "month"
    elif "jour" in t:
        period = "day"
    elif "heure" in t or "horaire" in t:
        period = "hour"
    else:
        return None, None, ""
    if not nums:
        return None, None, ""
    mult = 1000 if "k€" in t.replace(" ", "") else 1
    vals = [n * mult for n in nums[:2]]
    if "partir" in t:
        return vals[0], None, period
    if "jusqu" in t:
        return None, vals[0], period
    return vals[0], (vals[1] if len(vals) > 1 else vals[0]), period


def _float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if f else None
    except (TypeError, ValueError):
        return None


def _to_job(item: dict[str, Any], in_france: bool) -> Job | None:
    num, title = item.get("numeroOffre"), item.get("intitule")
    if not (num and title):
        return None
    lieu = (item.get("lieuTexte") or "").strip()
    smin, smax, period = _salary(item.get("salaireTexte"))
    return Job(
        source=NAME,
        source_id=str(num),
        title=title.strip(),
        company=(item.get("nomCommercial") or "").strip(),
        url=OFFER_URL.format(num),
        description=html_to_text(item.get("texteOffre")),
        location=lieu,
        lat=_float(item.get("latitude")),
        lon=_float(item.get("longitude")),
        country="FR" if in_france or _DEPT.search(lieu) else "",
        remote=REMOTE_MAP.get(item.get("idNomTeletravail"), "unknown"),
        contract=CONTRACT_MAP.get(item.get("typeContrat"), "unknown"),
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        published_at=_date(item.get("datePublication")),
    )


def fetch(ctx: Context) -> Iterator[Job]:
    allowed = ctx.config.get("contracts_allowed") or []
    contracts = [code for name, code in (("cdi", CDI), ("cdd", CDD)) if name in allowed]
    if not contracts:
        ctx.log("apec: ni CDI ni CDD acceptés dans la config, source sans objet")
        return
    # Familles : rayon autour de chaque lieu de recherche, puis télétravail total (France).
    families: list[tuple[dict[str, Any], bool]] = []
    for area in ctx.areas:
        criteria = _lieu(ctx, area)
        if criteria is None:
            ctx.log(f"apec: lieu « {area['name']} » introuvable, ignoré")
        else:
            families.append((criteria, True))
    if ctx.remote_wanted:
        families.append(({"typesTeletravail": [TELETRAVAIL_TOTAL]}, False))

    seen: set[str] = set()
    ok = failed = 0
    first = True
    for query in ctx.queries_fr:
        for criteria, in_france in families:
            if not first:
                polite_sleep(2)
            first = False
            items = _search(ctx, query, criteria, contracts)
            if items is None:
                failed += 1
                continue
            ok += 1
            for item in items:
                job = _to_job(item, in_france)
                if job is None or job.source_id in seen:
                    continue
                age = age_days(job.published_at)
                if age is not None and age > ctx.max_age_days:
                    continue
                seen.add(job.source_id)
                yield job
    if failed and not ok:
        raise RuntimeError("apec: aucune requête n'a abouti (DataDome ?)")
