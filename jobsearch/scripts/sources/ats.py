"""Offres publiées directement sur les ATS publics des entreprises ciblées.

Lit `config["ats_companies"]`, un dict {ats: [slug, ...]} pour :
lever, greenhouse, ashby, workable, recruitee, smartrecruiters.
Chaque entrée peut être un slug ("alan") ou un objet {"slug": "alan", "name": "Alan"}
(le nom sert pour Lever et Ashby, dont l'API ne renvoie pas le nom de l'entreprise).

Endpoints publics, sans clé :
- Lever            https://api.lever.co/v0/postings/<slug>?mode=json  (repli api.eu.lever.co)
- Greenhouse       https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true
- Ashby            https://api.ashbyhq.com/posting-api/job-board/<slug>?includeCompensation=true
- Workable         https://apply.workable.com/api/v1/widget/accounts/<slug>?details=true
                   + POST https://apply.workable.com/api/v3/accounts/<slug>/jobs (champ `workplace`)
- Recruitee        https://<slug>.recruitee.com/api/offers/
- SmartRecruiters  https://api.smartrecruiters.com/v1/companies/<id>/postings (+ détail par offre)

Pré-filtres légers (le tri fin reste central) :
- titre conforme au pré-filtre métier de la config (`prefilter`, voir scripts/prefilter.py) ;
- poste situé en France, en remote, ou de localisation inconnue ;
- publication plus récente que max_age_days ;
- au plus per_query offres par entreprise.
"""
from __future__ import annotations

import html
import re
from typing import Any, Callable, Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep

NAME = "ats"
LABEL = "ATS publics (Lever, Greenhouse, Ashby, Workable, Recruitee, SmartRecruiters)"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 12

TIMEOUT = 30

# --- Pré-filtre métier sur le titre -----------------------------------------------
# Motifs `prefilter.title` / `prefilter.title_exclude` de config.json (voir scripts/prefilter.py) :
# un « Sales Engineer » ou un « Business Developer » se règle par title_exclude.


# --- Localisation -------------------------------------------------------------------

_COUNTRY_NAMES = {
    "france": "FR", "france, metropolitan": "FR", "germany": "DE", "deutschland": "DE",
    "spain": "ES", "españa": "ES", "italy": "IT", "italia": "IT", "united kingdom": "GB",
    "uk": "GB", "england": "GB", "united states": "US", "usa": "US", "us": "US",
    "netherlands": "NL", "belgium": "BE", "belgique": "BE", "switzerland": "CH",
    "suisse": "CH", "portugal": "PT", "poland": "PL", "canada": "CA", "ireland": "IE",
    "india": "IN", "luxembourg": "LU", "austria": "AT", "sweden": "SE", "denmark": "DK",
}
# Indices qu'un libellé de lieu est en France (pays, grandes villes, régions) ;
# les lieux de l'utilisateur (domicile, zone, lieux de recherche) s'y ajoutent à la collecte.
_FR_HINT = re.compile(
    r"\bfrance\b|\bparis\b|marseille|toulouse|bordeaux|nantes|\blille\b|rennes|montpellier|\bnice\b|"
    r"strasbourg|sophia|clermont|\bdijon\b|\btours\b|\bbrest\b|\brouen\b|\bmetz\b|\bnancy\b|"
    r"[îi]le[- ]de[- ]france|auvergne|bretagne|normandie|occitanie|aquitaine|hauts[- ]de[- ]france|"
    r"grand[- ]est|pays de la loire|provence|bourgogne|centre[- ]val",
    re.I,
)
# Remote large (qui peut inclure la France) mentionné dans le libellé de lieu.
_WIDE_REMOTE = re.compile(r"europe|\beu\b|emea|worldwide|anywhere|global|international", re.I)


def _iso2(value: Any) -> str:
    """Nom ou code de pays -> ISO2 ; "" si inconnu."""
    if not value:
        return ""
    v = str(value).strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    return _COUNTRY_NAMES.get(v.lower(), "")


def _in_scope(job: Job, home_rx: re.Pattern | None = None) -> bool:
    """Garde les postes en France, en remote pouvant inclure la France, ou de lieu inconnu.

    Un remote limité à un autre pays ("Canada / United States", "Poland") est écarté :
    les grands comptes internationaux en publient des dizaines.
    """
    text = f"{job.location} {job.remote_scope}"
    if job.country == "FR" or _FR_HINT.search(text) or (home_rx and home_rx.search(text)):
        return True
    if _WIDE_REMOTE.search(text):
        return True
    if job.country:
        return False
    # Pays inconnu : on garde si le lieu est vide ou ne parle que de remote ("Remote").
    return not job.location or bool(re.search(r"remote|t[ée]l[ée]travail", job.location, re.I))


# --- Contrat ----------------------------------------------------------------------

def _contract(value: Any) -> str:
    """Libellé libre de type de contrat (tous ATS) -> vocabulaire CONTRACT."""
    t = str(value or "").lower()
    if not t:
        return "unknown"
    if re.search(r"altern|apprenti|work[\s-]?study|working student|contrat pro", t):
        return "alternance"
    # bornes de mot : ne pas prendre "international", "internal" ou "early-stage"
    if re.search(r"\bintern(ship)?\b|^stage\b|\bstagiaire|\btrainee", t):
        return "stage"
    if re.search(r"permanent|\bcdi\b|unlimited|indefinite|ind[ée]termin", t):
        return "cdi"
    if re.search(r"fixed|\bcdd\b|temporary|short[\s-]?term|d[ée]termin", t):
        return "cdd"
    if re.search(r"int[ée]rim", t):
        return "interim"
    if re.search(r"freelance|contractor|contract|ind[ée]pendant|portage", t):
        return "freelance"
    if re.search(r"full[\s_-]?time|temps plein", t):
        return "cdi"
    return "unknown"


def _period(value: Any) -> str:
    """Intervalle de salaire libre ("1 YEAR", "per-year-salary", "month"…) -> Job.salary_period."""
    t = str(value or "").lower()
    for key in ("year", "month", "day", "hour"):
        if key in t:
            return key
    return ""


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# --- HTTP ---------------------------------------------------------------------------

class _NotFound(Exception):
    """Slug inexistant sur cet ATS (404)."""


def _get_json(ctx: Context, url: str, **kw: Any) -> Any:
    r = ctx.http.get(url, timeout=TIMEOUT, **kw)
    if r.status_code == 404:
        raise _NotFound(url)
    r.raise_for_status()
    return r.json()


def _entries(raw: list[Any]) -> Iterator[tuple[str, str]]:
    """Normalise les entrées de config en (slug, nom affiché)."""
    for item in raw or []:
        if isinstance(item, dict):
            slug = str(item.get("slug") or item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
        else:
            slug, name = str(item).strip(), ""
        if slug:
            yield slug, name or slug.replace("-", " ").title()


# --- Adaptateurs par ATS ------------------------------------------------------------

def _lever(ctx: Context, slug: str, name: str) -> Iterator[Job]:
    # Les comptes hébergés en Europe ne répondent que sur api.eu.lever.co.
    postings: list[dict] = []
    for host in ("api.lever.co", "api.eu.lever.co"):
        try:
            postings = _get_json(ctx, f"https://{host}/v0/postings/{slug}", params={"mode": "json"})
        except _NotFound:
            postings = []
        if postings:
            break
        polite_sleep(0.5)
    for p in postings:
        cat = p.get("categories") or {}
        locations = cat.get("allLocations") or [cat.get("location")]
        location = " / ".join(x for x in locations if x)
        remote = {"remote": "full", "hybrid": "partial", "onsite": "none"}.get(
            str(p.get("workplaceType") or "").lower(), "unknown")
        salary = p.get("salaryRange") or {}
        parts = [p.get("descriptionPlain") or html_to_text(p.get("description"))]
        for block in p.get("lists") or []:
            parts.append(f"{block.get('text', '')}\n{html_to_text(block.get('content'))}")
        parts.append(p.get("additionalPlain") or html_to_text(p.get("additional")))
        yield Job(
            source=NAME, source_id=f"lever:{slug}:{p['id']}", title=p.get("text", ""),
            company=name, url=p.get("hostedUrl") or p.get("applyUrl") or "",
            description="\n".join(x for x in parts if x).strip(),
            location=location, country=_iso2(p.get("country")),
            remote=remote, remote_scope=location if remote == "full" else "",
            contract=_contract(cat.get("commitment")),
            salary_min=_num(salary.get("min")), salary_max=_num(salary.get("max")),
            salary_period=_period(salary.get("interval")) if salary else "",
            published_at=iso_date(p.get("createdAt")),
            tags=[x for x in (cat.get("department"), cat.get("team")) if x],
        )


def _greenhouse(ctx: Context, slug: str, name: str) -> Iterator[Job]:
    data = _get_json(ctx, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                     params={"content": "true"})
    for p in data.get("jobs", []):
        location = (p.get("location") or {}).get("name", "")
        meta = {str(m.get("name", "")).lower(): m.get("value") for m in p.get("metadata") or []}
        # Pas de champ pays structuré standard. Le libellé ("Paris, Paris, France",
        # "Nantes; Paris…") prime : la métadonnée "Job Posting Country" est parfois fausse
        # (Doctolib : Germany sur des postes parisiens).
        first_location = location.split(";")[0]
        if _FR_HINT.search(location):
            country = "FR"
        else:
            country = (_iso2(first_location.split(",")[-1])
                       or _iso2(meta.get("job posting country")))
        contract_raw = next((v for k, v in meta.items() if "employment" in k or "contract" in k), None)
        yield Job(
            source=NAME, source_id=f"greenhouse:{slug}:{p['id']}", title=p.get("title", ""),
            company=p.get("company_name") or name, url=p.get("absolute_url", ""),
            # `content` est du HTML échappé (&lt;p&gt;) : on le déséchappe avant de retirer les balises.
            description=html_to_text(html.unescape(p.get("content") or "")),
            location=location, country=country,
            remote="unknown",  # aucun champ structuré sur l'API board
            contract=_contract(contract_raw),
            published_at=iso_date(p.get("first_published") or p.get("updated_at")),
            tags=[d["name"] for d in p.get("departments") or [] if d.get("name")],
        )


def _ashby(ctx: Context, slug: str, name: str) -> Iterator[Job]:
    data = _get_json(ctx, f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                     params={"includeCompensation": "true"})
    for p in data.get("jobs", []):
        if p.get("isListed") is False:
            continue
        addresses = [p.get("address")] + [s.get("address") for s in p.get("secondaryLocations") or []]
        countries = [_iso2(((a or {}).get("postalAddress") or {}).get("addressCountry")) for a in addresses]
        labels = [p.get("location")] + [s.get("location") for s in p.get("secondaryLocations") or []]
        location = " / ".join(x for x in labels if x)
        # Un poste ouvert sur plusieurs sites dont un en France est considéré "FR"
        # (adresse structurée, ou libellé du type "Anywhere in France, Belgium, Spain").
        if "FR" in countries or _FR_HINT.search(location):
            country = "FR"
        else:
            country = next((c for c in countries if c), "")
        # workplaceType est fiable ; isRemote vaut aussi True pour l'hybride, on ne s'en sert
        # que pour confirmer le présentiel quand workplaceType est absent.
        wp = p.get("workplaceType")
        remote = {"Remote": "full", "Hybrid": "partial", "OnSite": "none"}.get(wp or "", "unknown")
        if not wp and p.get("isRemote") is False:
            remote = "none"
        smin = smax = None
        period = ""
        for comp in (p.get("compensation") or {}).get("summaryComponents") or []:
            # On ne garde que le fixe en euros, comparable à salary_target.
            if comp.get("compensationType") == "Salary" and comp.get("currencyCode") == "EUR":
                smin, smax = _num(comp.get("minValue")), _num(comp.get("maxValue"))
                period = _period(comp.get("interval"))
                break
        yield Job(
            source=NAME, source_id=f"ashby:{slug}:{p['id']}", title=p.get("title", ""),
            company=name, url=p.get("jobUrl") or p.get("applyUrl") or "",
            description=p.get("descriptionPlain") or html_to_text(p.get("descriptionHtml")),
            location=location, country=country,
            remote=remote, remote_scope=location if remote == "full" else "",
            contract={"FullTime": "cdi", "Contract": "freelance", "Intern": "stage",
                      "Temporary": "cdd"}.get(p.get("employmentType") or "", "unknown"),
            salary_min=smin, salary_max=smax, salary_period=period if smin or smax else "",
            published_at=iso_date(p.get("publishedAt")),
            tags=[x for x in (p.get("department"), p.get("team")) if x],
        )


def _workable(ctx: Context, slug: str, name: str) -> Iterator[Job]:
    # Le widget donne description et localisation ; seul l'endpoint v3 expose `workplace`
    # (on_site / hybrid / remote). `telecommuting` du widget est ambigu : on ne s'en sert pas.
    data = _get_json(ctx, f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
                     params={"details": "true"})
    workplace: dict[str, str] = {}
    try:
        body: dict[str, Any] = {"query": ""}
        for _ in range(10):  # pagination par jeton, bornée
            polite_sleep(0.5)
            r = ctx.http.post(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
                              json=body, timeout=TIMEOUT)
            r.raise_for_status()
            page = r.json()
            workplace.update({x.get("shortcode"): x.get("workplace") for x in page.get("results", [])})
            if not page.get("nextPage"):
                break
            body["token"] = page["nextPage"]
    except (requests.RequestException, ValueError) as e:
        ctx.log(f"ats/workable {slug}: workplace indisponible ({e})")
    company = data.get("name") or name
    for p in data.get("jobs", []):
        locs = p.get("locations") or []
        codes = [_iso2(loc.get("countryCode") or loc.get("country")) for loc in locs]
        codes.append(_iso2(p.get("country")))
        country = "FR" if "FR" in codes else next((c for c in codes if c), "")
        location = ", ".join(x for x in (p.get("city"), p.get("state"), p.get("country")) if x)
        remote = {"remote": "full", "hybrid": "partial", "on_site": "none"}.get(
            workplace.get(p.get("shortcode"), ""), "unknown")
        yield Job(
            source=NAME, source_id=f"workable:{slug}:{p.get('shortcode')}", title=p.get("title", ""),
            company=company, url=p.get("url") or p.get("shortlink") or "",
            description=html_to_text(p.get("description")),
            location=location, country=country,
            remote=remote, remote_scope=location if remote == "full" else "",
            contract=_contract(p.get("employment_type")),
            published_at=iso_date(p.get("published_on") or p.get("created_at")),
            tags=[x for x in (p.get("department"), p.get("function")) if x],
        )


def _recruitee(ctx: Context, slug: str, name: str) -> Iterator[Job]:
    data = _get_json(ctx, f"https://{slug}.recruitee.com/api/offers/")
    for p in data.get("offers", []):
        if p.get("status") not in (None, "published"):
            continue
        locs = p.get("locations") or []
        codes = [_iso2(loc.get("country_code")) for loc in locs] + [_iso2(p.get("country_code"))]
        country = "FR" if "FR" in codes else next((c for c in codes if c), "")
        city_label = ", ".join(x for x in (p.get("city"), p.get("country")) if x)
        location = " / ".join(x for x in [p.get("location"), city_label] if x)
        if p.get("remote"):
            remote = "full"
        elif p.get("hybrid"):
            remote = "partial"
        elif p.get("on_site"):
            remote = "none"
        else:
            remote = "unknown"
        # La restriction du remote est portée par le nom/la note du lieu ("Anywhere in Europe").
        scope = " / ".join(x for loc in locs for x in (loc.get("name"), loc.get("note")) if x)
        salary = p.get("salary") or {}
        # "2026-05-28 13:33:37 UTC" n'est pas de l'ISO strict.
        published = str(p.get("published_at") or p.get("created_at") or "").replace(" UTC", "+00:00")
        yield Job(
            source=NAME, source_id=f"recruitee:{slug}:{p['id']}", title=p.get("title", ""),
            company=p.get("company_name") or name, url=p.get("careers_url") or "",
            description=html_to_text(f"{p.get('description') or ''}\n{p.get('requirements') or ''}"),
            location=location, country=country,
            remote=remote, remote_scope=scope if remote == "full" else "",
            contract=_contract(p.get("employment_type_code")),
            salary_min=_num(salary.get("min")), salary_max=_num(salary.get("max")),
            salary_period=_period(salary.get("period")) if salary.get("min") or salary.get("max") else "",
            published_at=iso_date(published),
            tags=[x for x in [p.get("department"), *(p.get("tags") or [])] if x],
        )


def _smartrecruiters(ctx: Context, slug: str, name: str) -> Iterator[Job]:
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    offset, pages = 0, 0
    while pages < 10:  # borné à 1000 offres
        data = _get_json(ctx, base, params={"limit": 100, "offset": offset})
        content = data.get("content") or []
        for p in content:
            loc = p.get("location") or {}
            if loc.get("remote"):
                remote = "full"
            elif loc.get("hybrid"):
                remote = "partial"
            else:
                remote = "none"  # drapeaux explicites du formulaire SmartRecruiters
            job = Job(
                source=NAME, source_id=f"smartrecruiters:{slug}:{p['id']}", title=p.get("name", ""),
                company=(p.get("company") or {}).get("name") or name,
                url=f"https://jobs.smartrecruiters.com/{slug}/{p['id']}",
                location=loc.get("fullLocation") or ", ".join(
                    x for x in (loc.get("city"), loc.get("country")) if x),
                lat=_num(loc.get("latitude")), lon=_num(loc.get("longitude")),
                country=_iso2(loc.get("country")), remote=remote,
                contract=_contract((p.get("typeOfEmployment") or {}).get("id")),
                published_at=iso_date(p.get("releasedDate")),
                tags=[x.get("label") for x in (p.get("department"), p.get("function")) if x and x.get("label")],
            )
            if job.remote == "full":
                job.remote_scope = job.location
            # La liste ne contient pas la description : un appel de détail, seulement
            # pour les offres qui passent les pré-filtres.
            if _keep(ctx, job):
                try:
                    polite_sleep(0.5)
                    detail = _get_json(ctx, f"{base}/{p['id']}")
                    sections = ((detail.get("jobAd") or {}).get("sections") or {}).values()
                    job.description = "\n".join(
                        f"{s.get('title', '')}\n{html_to_text(s.get('text'))}" for s in sections if s)
                    job.url = detail.get("postingUrl") or job.url
                except (requests.RequestException, ValueError, _NotFound) as e:
                    ctx.log(f"ats/smartrecruiters {slug}: détail {p['id']} indisponible ({e})")
            yield job
        offset += len(content)
        pages += 1
        if not content or offset >= int(data.get("totalFound") or 0):
            break
        polite_sleep(0.5)


ADAPTERS: dict[str, Callable[[Context, str, str], Iterator[Job]]] = {
    "lever": _lever,
    "greenhouse": _greenhouse,
    "ashby": _ashby,
    "workable": _workable,
    "recruitee": _recruitee,
    "smartrecruiters": _smartrecruiters,
}


# --- Point d'entrée -----------------------------------------------------------------

def _max_age(ctx: Context) -> int:
    """Âge maximal pour un ATS.

    Une offre encore listée sur un ATS est ouverte par définition, mais sa date est celle de
    la première publication : avec max_age_days (30 j) on perdrait des postes toujours actifs
    ouverts il y a deux mois. On tolère donc plus large, réglable via `ats_max_age_days`,
    tout en écartant les annonces « evergreen » de plusieurs années.
    """
    return int(ctx.config.get("ats_max_age_days", max(ctx.max_age_days, 90)))


def _keep(ctx: Context, job: Job, home_rx: re.Pattern | None) -> bool:
    if not job.title or not job.url or not ctx.prefilter.role(job.title):
        return False
    age = age_days(job.published_at)
    if age is not None and age > _max_age(ctx):
        return False
    return _in_scope(job, home_rx)


def fetch(ctx: Context) -> Iterator[Job]:
    companies = {k: v for k, v in (ctx.config.get("ats_companies") or {}).items() if not k.startswith("_")}
    names = ctx.place_names
    home_rx = re.compile("|".join(rf"\b{re.escape(n)}\b" for n in names), re.I) if names else None
    seen: set[str] = set()
    # ATS qui nous limitent (429 persistant) : on n'insiste pas sur leurs autres slugs.
    throttled: set[str] = set()
    for ats, raw in companies.items():
        adapter = ADAPTERS.get(ats)
        if adapter is None:
            if raw:
                ctx.log(f"ats: ATS inconnu « {ats} », ignoré")
            continue
        for slug, name in _entries(raw):
            kept = 0
            if ats in throttled:
                continue
            try:
                for job in adapter(ctx, slug, name):
                    if job.uid in seen or not _keep(ctx, job, home_rx):
                        continue
                    seen.add(job.uid)
                    kept += 1
                    yield job
                    if kept >= ctx.per_query:
                        break
            except _NotFound:
                ctx.log(f"ats/{ats} {slug}: introuvable (404), slug à corriger dans la config")
            except requests.exceptions.RetryError as e:
                # Les retries de make_session() ont épuisé les 429 : blocage IP temporaire
                # (constaté sur Workable après quelques dizaines d'appels).
                throttled.add(ats)
                ctx.log(f"ats/{ats} {slug}: limité (429 persistant), {ats} sauté pour cette collecte ({e})")
            except (requests.RequestException, ValueError, KeyError, TypeError) as e:
                ctx.log(f"ats/{ats} {slug}: échec ({type(e).__name__}: {e})")
            polite_sleep(1.0)
