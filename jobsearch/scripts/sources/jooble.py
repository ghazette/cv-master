"""Jooble : API REST partenaires.

Endpoint : POST https://jooble.org/api/<clé>   (corps JSON, Content-Type: application/json)
Doc      : https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation
           https://help.jooble.org/en/support/solutions/articles/60000922689-how-to-connect-to-the-jooble-rest-api-after-receiving-the-key
Clé      : https://jooble.org/api/about

Corps (doc) :
    keywords (requis)   mots-clés ; l'exemple officiel en sépare plusieurs par des virgules
    location (requis)   ville, région ou pays
    radius              "0" | "4" | "8" | "16" | "26" | "40" | "80" (km)
    salary, page, ResultOnPage, SearchMode, companysearch (true = chercher dans les noms d'entreprise)
Réponse : {"totalCount": n, "jobs": [{id, title, location, snippet, salary, source, type, link, company, updated}]}

Quota : 500 requêtes AU TOTAL pour une clé gratuite. Donc 2 requêtes par run, MIN_INTERVAL_H = 72,
et un plan tournant (un lieu de recherche chacun, puis télétravail France) : chaque run en prend 2 à la suite.
Toutes les requêtes FR tiennent dans un seul `keywords` séparé par des virgules.

Attention : depuis l'IP de test, jooble.org renvoie un challenge Cloudflare (HTTP 403 « Just a moment... »)
même en POST JSON. On le détecte et on lève une erreur explicite plutôt que de consommer le quota en silence.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "jooble"
LABEL = "Jooble"
KIND = "api"
REQUIRES = ["JOOBLE_API_KEY"]
MIN_INTERVAL_H = 72

API = "https://jooble.org/api/{key}"
REQUESTS_PER_RUN = 2
RADII = (0, 4, 8, 16, 26, 40, 80)
RESULTS_MAX = 100

# Extrait de réponse attendue (doc « REST API Documentation », exemple officiel) :
_SAMPLE_ITEM: dict[str, Any] = {
    "id": 1234567890,
    "title": "Sales Manager",
    "location": "Kyiv",
    "snippet": "This is a great opportunity to join our team...",
    "salary": "17,600 UAH",
    "source": "jooble",
    "type": "Full-time",
    "link": "https://ua.jooble.org/jdp/12345",
    "company": "ABC Corp",
    "updated": "2023-09-15T12:55:35.3870000",
}

# Libellé du champ structuré `type` -> contrat commun. "Full-time" / "Temps plein" ne dit rien du contrat.
_CONTRACT_WORDS = [
    ("freelance", r"freelance|ind[ée]pendant|contractor|prestataire|portage|lib[ée]ral"),
    ("alternance", r"alternance|apprenti\w*|apprenticeship|professionnalisation"),
    ("stage", r"stage|internship"),
    ("interim", r"int[ée]rim\w*"),
    ("cdd", r"cdd|fixed[- ]term|temporaire|temporary|saisonnier"),
    ("cdi", r"cdi|permanent"),
]

_PERIODS = [
    ("hour", r"heure|horaire|hour|hourly|/\s*h\b"),
    ("day", r"jour|journalier|tjm|day|daily"),
    ("month", r"mois|mensuel|month|monthly"),
    ("year", r"\ban\b|annuel|ann[ée]e|year|yearly|annual"),
]
_AMOUNT = re.compile(r"(\d[\d\s  .,]*\d|\d)\s*([kK]\b)?")


def _contract(label: str | None) -> str:
    low = (label or "").lower()
    for value, pattern in _CONTRACT_WORDS:
        if re.search(rf"\b(?:{pattern})\b", low):
            return value
    return "unknown"


def _amount(raw: str, thousands: str) -> float | None:
    s = re.sub(r"[\s  ]", "", raw)
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):   # 45.000 / 17,600 -> séparateurs de milliers
        s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        value = float(s)
    except ValueError:
        return None
    return value * 1000 if thousands else value


def _salary(text: str | None) -> tuple[float | None, float | None, str]:
    """« 45 000 € - 55 000 € par an », « 45K - 55K € », « 500 € par jour » -> (min, max, période)."""
    if not text:
        return None, None, ""
    low = text.lower()
    period = next((p for p, pattern in _PERIODS if re.search(pattern, low)), "")
    values = [v for v in (_amount(n, k) for n, k in _AMOUNT.findall(text)) if v]
    if not values:
        return None, None, ""
    if not period:
        # Sans unité explicite, seul un montant clairement annuel est interprétable.
        if min(values) < 12000:
            return None, None, ""
        period = "year"
    return min(values), max(values), period


def _parse(item: dict[str, Any]) -> Job:
    link = item.get("link") or ""
    sid = str(item.get("id") or "") or hashlib.sha1(link.encode()).hexdigest()[:16]
    smin, smax, period = _salary(item.get("salary"))
    return Job(
        source=NAME,
        source_id=sid,
        title=html_to_text(item.get("title")),
        company=html_to_text(item.get("company")),
        url=link,
        description=html_to_text(item.get("snippet")),
        location=html_to_text(item.get("location")),
        country="FR",  # toutes nos requêtes visent la France
        contract=_contract(item.get("type")),
        salary_min=smin,
        salary_max=smax,
        salary_period=period,
        # Jooble ne donne que la date de dernière mise à jour, faute de mieux.
        # Format « 2023-09-15T12:55:35.3870000 » (7 décimales) : Python < 3.11 n'en accepte que 3 ou 6.
        published_at=iso_date(re.sub(r"(\.\d{6})\d+", r"\1", str(item.get("updated") or ""))),
        tags=[t for t in (item.get("type"), item.get("source")) if t],
    )


def _plan(ctx: Context) -> list[tuple[str, dict[str, Any]]]:
    keywords = ", ".join(ctx.queries_fr)
    remote_keywords = ", ".join(f"{q} télétravail" for q in ctx.queries_fr)
    plan = []
    for area in ctx.areas:
        # rayons acceptés par Jooble : on prend le premier palier qui couvre le rayon voulu
        radius = next((r for r in RADII if r >= area["radius_km"]), RADII[-1])
        plan.append((f"{area['name']} {radius} km",
                     {"keywords": keywords, "location": area["city"], "radius": str(radius)}))
    if ctx.remote_wanted:
        plan.append(("télétravail France", {"keywords": remote_keywords, "location": "France"}))
    return plan


def _todays_slice(plan: list, n: int) -> list:
    """Rotation par tranche de 3 jours : chaque run prend n entrées consécutives du plan."""
    start = (date.today().toordinal() // 3) % len(plan)
    return [plan[(start + i) % len(plan)] for i in range(min(n, len(plan)))]


def _search(ctx: Context, body: dict[str, Any]) -> dict[str, Any]:
    r = ctx.http.post(API.format(key=ctx.env["JOOBLE_API_KEY"]), json=body,
                      headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=30)
    if r.status_code in (401, 403):
        if "Just a moment" in r.text or r.headers.get("cf-mitigated"):
            raise RuntimeError("Jooble : bloqué par Cloudflare (HTTP 403, challenge « Just a moment... »). "
                               "L'API n'est pas joignable depuis ce client/cette IP ; aucune requête consommée côté Jooble.")
        raise RuntimeError(f"Jooble : clé refusée (HTTP {r.status_code} : {r.text[:200].strip()}). Vérifier JOOBLE_API_KEY.")
    r.raise_for_status()
    return r.json()


def fetch(ctx: Context) -> Iterator[Job]:
    seen: set[str] = set()
    plan = _plan(ctx)
    if not plan:
        return
    for i, (label, params) in enumerate(_todays_slice(plan, REQUESTS_PER_RUN)):
        if i:
            polite_sleep(2)
        body = {**params, "page": 1, "ResultOnPage": max(1, min(ctx.per_query, RESULTS_MAX))}
        try:
            data = _search(ctx, body)
        except (requests.RequestException, ValueError) as exc:
            ctx.log(f"[{NAME}] échec « {label} » : {exc}")
            continue

        kept = 0
        for item in data.get("jobs") or []:
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
