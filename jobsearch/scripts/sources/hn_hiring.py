"""Hacker News « Ask HN: Who is hiring? » — fil mensuel, un commentaire de 1er niveau par entreprise.

Endpoints (API Algolia HN, sans clé) :
  1. GET https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring
     → le compte `whoishiring` publie aussi « Who wants to be hired? » et « Freelancer? » :
       on garde le plus récent dont le titre contient « Who is hiring ».
  2. GET https://hn.algolia.com/api/v1/items/<id>
     → arbre complet ; `children` = commentaires de 1er niveau (author, created_at_i, id, text HTML).
Format (convention, non garantie) : 1re ligne « Company | Role | Location | REMOTE | Full-time | $ »,
  puis la description. Le parsing est donc heuristique.
Filtre : mention de (remote|france|paris|europe|lieux de l'utilisateur) ET d'un motif métier de la
  config (`prefilter`, ou mots des requêtes) ; classement par pertinence puis plafond ctx.per_query.
Contraintes : un nouveau fil par mois → MIN_INTERVAL_H = 24. `url` = commentaire HN.
"""
from __future__ import annotations

import re
from typing import Iterator

import requests

from common import Context, Job, age_days, html_to_text, iso_date, polite_sleep
from config import norm

NAME = "hn_hiring"
LABEL = "HN Who is hiring"
KIND = "api"
REQUIRES: list[str] = []
MIN_INTERVAL_H = 24

SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
ITEM = "https://hn.algolia.com/api/v1/items/{id}"
HN_ITEM = "https://news.ycombinator.com/item?id={id}"

_WHERE_BASE = ["remote", "france", "paris", "europe"]

# classification des segments de la 1re ligne
_REMOTE = re.compile(r"\bremote\b", re.I)
_ONSITE = re.compile(r"\b(on[\s-]?site|in[\s-]?office|in[\s-]?person)\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_MONEY = re.compile(r"[$€£]|\b(usd|eur|gbp)\b", re.I)
_URL = re.compile(r"https?://\S+|\bwww\.\S+|\b[\w-]+\.(?:com|io|ai|co|dev|app|org|net|fr|so|tech)\b(?:/\S*)?", re.I)
_CONTRACT_WORDS = re.compile(r"\b(full[\s-]?time|part[\s-]?time|contract(?:or)?|freelance|intern(?:ship)?|"
                             r"permanent|fte|equity|visa)\b", re.I)
_ROLE = re.compile(r"\b(engineers?|engineering|developers?|devs?|swe|programmers?|architects?|scientists?|"
                   r"researchers?|designers?|leads?|managers?|head of|cto|founding|full[\s-]?stack|front[\s-]?end|"
                   r"back[\s-]?end|devops|sre|ml|roles?|positions?|staff|senior|principal)\b", re.I)
_WHERE_FIRST = re.compile(r"\W*(?:fully\s+|100\s*%\s+)?(remote|on[\s-]?site|hybrid|in[\s-]?office)\b", re.I)
# segments courts qui ne sont pas des lieux (exigences, stack, mentions diverses)
_NOT_PLACE = re.compile(r"\b(required|requis|skills?|fluen\w*|citizens?|visa|equity|yc|hiring|python|java\w*|"
                        r"typescript|react|go(?:lang)?|rust|kotlin|pytorch|tensorflow|django|rails|gmt|utc)\b", re.I)


def _latest_thread(ctx: Context) -> dict | None:
    try:
        resp = ctx.http.get(SEARCH, params={"tags": "story,author_whoishiring", "hitsPerPage": 10}, timeout=30)
        resp.raise_for_status()
        hits = resp.json().get("hits") or []
    except (requests.RequestException, ValueError) as exc:
        ctx.log(f"[{NAME}] recherche du fil en échec : {exc}")
        return None
    finally:
        polite_sleep()
    threads = [h for h in hits if re.search(r"who is hiring", h.get("title") or "", re.I)]
    return max(threads, key=lambda h: h.get("created_at_i") or 0) if threads else None


def _parse_salary(text: str) -> tuple[float, float, str] | None:
    """« €75k–110k », « $150 - 210K USD » → (min, max, période) ; None si ambigu."""
    has_k = bool(re.search(r"\d\s*k\b", text, re.I))
    period = ("hour" if re.search(r"/\s*h(?:ou)?r\b|per hour|hourly", text, re.I)
              else "day" if re.search(r"/\s*day\b|per day|daily", text, re.I)
              else "month" if re.search(r"/\s*mo(?:nth)?\b|per month|monthly", text, re.I)
              else "year")
    values = []
    for num, k in re.findall(r"(\d+(?:[.,]\d+)*)\s*(k\b)?", text, re.I):
        if (k or has_k) and re.fullmatch(r"\d+[.,]\d{1,2}", num):
            v = float(num.replace(",", "."))
        else:
            v = float(re.sub(r"[.,]", "", num))
        if k or (has_k and v < 1000):
            v *= 1000
        values.append(v)
    values = [v for v in values if v >= (10000 if period == "year" else 1)][:2]
    return (min(values), max(values), period) if values else None


def _contract(line: str) -> str:
    if re.search(r"\bintern(ship)?s?\b", line, re.I):
        return "stage"
    ft = bool(re.search(r"\b(full[\s-]?time|permanent|fte)\b", line, re.I))
    ct = bool(re.search(r"\b(contract(or)?s?|freelance)\b", line, re.I))
    if ft and not ct:
        return "cdi"
    if ct and not ft:
        return "freelance"
    return "unknown"  # part-time, mixte ou non précisé


def _remote(line: str) -> str:
    remote, onsite, hybrid = bool(_REMOTE.search(line)), bool(_ONSITE.search(line)), bool(_HYBRID.search(line))
    if remote and not (onsite or hybrid):
        return "full"
    if hybrid and not remote:
        return "partial"
    if onsite and not (remote or hybrid):
        return "none"
    return "unknown"  # « ONSITE/REMOTE », « Remote or hybrid »… : ambigu


def _relevance(ctx: Context, text: str, france: re.Pattern) -> int:
    """Ordre de priorité quand le plafond coupe : spécialité et France d'abord."""
    pf = ctx.prefilter
    low = norm(text)
    score = 0
    score += 3 if pf.stack is not None and pf.stack.search(low) else 0
    score += 3 if france.search(text) else 0
    score += 2 if re.search(r"\b(europe|eu|emea|cet)\b", text, re.I) else 0
    score += 1 if pf.title is not None and pf.title.search(low) else 0
    score += 1 if _REMOTE.search(text) else 0
    return score


def _comment_to_job(c: dict, france: re.Pattern) -> Job | None:
    html_text = c.get("text") or ""
    if not html_text or not c.get("id"):
        return None  # commentaire supprimé
    first = html_to_text(re.split(r"<p>", html_text, maxsplit=1, flags=re.I)[0]).replace("\n", " ").strip()
    parts = [p.strip() for p in first.split("|") if p.strip()]

    short = first if len(first) <= 120 else first[:117] + "…"
    if len(parts) >= 2:
        company = _URL.sub("", parts[0]).strip(" -–—()[]:")
        if not company:  # 1er segment réduit à un lien : nom tiré du domaine
            dom = re.search(r"(?:https?://)?(?:www\.)?([\w-]+)\.[a-z]{2,}", parts[0], re.I)
            company = dom.group(1) if dom else ""
    else:  # pas de format « | » : entreprise inconnue, sauf « … hiring at X »
        at = re.search(r"hiring at ([A-Z][\w.&-]*)", first)
        company = at.group(1) if at else ""

    title, where, places, salary = "", [], [], None
    for p in parts[1:]:
        if _MONEY.search(p) and re.search(r"\d", p):
            salary = salary or _parse_salary(p)
        elif not title and _ROLE.search(p) and not _WHERE_FIRST.match(p) and not _URL.fullmatch(p):
            title = p  # « Full-Stack Engineer (full-time, REMOTE) » reste un titre
        elif _REMOTE.search(p) or _ONSITE.search(p) or _HYBRID.search(p):
            where.append(p)
        elif _URL.search(p) and len(p.split()) <= 2:
            continue
        elif _CONTRACT_WORDS.search(p) and len(p) < 40:
            continue
        elif len(p) <= 40 and not re.search(r"\d", p) and not _ROLE.search(p) and not _NOT_PLACE.search(p):
            places.append(p)  # probablement une ville / un pays
    if not title:  # aucun segment ne ressemble à un poste : 1re ligne, tronquée
        title = short

    remote = _remote(first)
    scope = " | ".join(w for w in where if _REMOTE.search(w))
    if not scope and remote == "full":
        scope = "Remote"
    return Job(
        source=NAME,
        source_id=str(c["id"]),
        title=title,
        company=company,
        url=HN_ITEM.format(id=c["id"]),
        description=html_to_text(html_text),
        location=" | ".join(places + where),
        remote=remote,
        remote_scope=scope,
        country="FR" if france.search(first) else "",
        contract=_contract(first),
        salary_min=salary[0] if salary else None,
        salary_max=salary[1] if salary else None,
        salary_period=salary[2] if salary else "",
        published_at=iso_date(c.get("created_at_i") or c.get("created_at")),
    )


def fetch(ctx: Context) -> Iterator[Job]:
    thread = _latest_thread(ctx)
    if not thread:
        ctx.log(f"[{NAME}] aucun fil « Who is hiring » trouvé")
        return
    try:
        resp = ctx.http.get(ITEM.format(id=thread["objectID"]), timeout=60)
        resp.raise_for_status()
        story = resp.json()
    except (requests.RequestException, ValueError) as exc:
        ctx.log(f"[{NAME}] lecture du fil {thread['objectID']} en échec : {exc}")
        return
    finally:
        polite_sleep()

    places = [re.escape(n) for n in ctx.place_names]
    where = re.compile(r"\b(" + "|".join(_WHERE_BASE + places) + r")\b", re.I)
    france = re.compile(r"\b(" + "|".join(["france", "paris"] + places) + r")\b", re.I)
    ranked: list[tuple[int, Job]] = []
    seen: set[str] = set()
    for comment in story.get("children") or []:
        text = html_to_text(comment.get("text"))
        if not (where.search(text) and ctx.prefilter.any_signal(text)):
            continue
        job = _comment_to_job(comment, france)
        if job is None or job.uid in seen:
            continue
        age = age_days(job.published_at)
        if age is not None and age > ctx.max_age_days:
            continue
        seen.add(job.uid)
        ranked.append((_relevance(ctx, text, france), job))
    ranked.sort(key=lambda x: (x[0], x[1].published_at), reverse=True)
    for _, job in ranked[:ctx.per_query]:
        yield job
