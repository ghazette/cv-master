#!/usr/bin/env python3
"""Commandes du quotidien sur l'historique.

    python3 jobs.py top [--n 20]                      # classement des éligibles dans le terminal
    python3 jobs.py queue [--limit 30]                # (ré)exporte la file de revue pour Claude
    python3 jobs.py import-review <fichier.json>      # enregistre les notes de Claude
    python3 jobs.py show <uid>                        # fiche complète d'une offre
    python3 jobs.py find <texte>                      # retrouve un uid par entreprise ou intitulé
    python3 jobs.py status <uid> <statut> [--notes …] # nouveau|vu|favori|postule|entretien|refuse|ecarte
    python3 jobs.py offer <uid>                       # écrit l'offre en markdown pour le skill cv
    python3 jobs.py stats                             # compteurs et état des collectes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA_DIR, load_config  # noqa: E402
from config import warn_if_blank  # noqa: E402
from db import DB, STATUSES  # noqa: E402
from filters import norm  # noqa: E402

DESC_LIMIT = 6000  # assez pour juger une offre, sans noyer la revue


def salary_label(d: dict) -> str:
    lo, hi, per = d.get("salary_min"), d.get("salary_max"), d.get("salary_period")
    if not (lo or hi):
        return ""
    unit = {"year": "€/an", "month": "€/mois", "day": "€/j", "hour": "€/h"}.get(per, "€")
    return f"{int(lo):,}–{int(hi):,} {unit}".replace(",", " ") if lo and hi else f"{int(lo or hi):,} {unit}".replace(",", " ")


def export_queue(db: DB, cfg: dict, limit: int | None = None) -> tuple[Path, int]:
    rows = db.review_queue(limit or cfg.get("llm_review_top", 30))
    items = []
    for r in rows:
        d = json.loads(r["data"])
        items.append({
            "uid": r["uid"], "title": d["title"], "company": d["company"], "url": d["url"],
            "location": d["location"], "zone": r["zone"], "remote": r["remote"],
            "remote_evidence": r["remote_evidence"], "remote_scope": d.get("remote_scope", ""),
            "contract": r["contract"], "level": r["level"], "filter_reason": r["reason"],
            "pre_score": r["pre_score"], "breakdown": json.loads(r["breakdown"] or "[]"),
            "salary": salary_label(d), "published_at": d.get("published_at", ""),
            "sources": json.loads(r["sources"]), "description": (d.get("description") or "")[:DESC_LIMIT],
        })
    out = DATA_DIR / "review" / "queue.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    return out, len(items)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")[:60]


def cmd_top(db: DB, n: int) -> None:
    rows = [r for r in db.report_rows() if r["level"] == "ok" and r["status"] not in ("ecarte", "refuse")][:n]
    print("| score | poste | entreprise | lieu | remote | contrat | statut | uid |\n|---|---|---|---|---|---|---|---|")
    for r in rows:
        d = json.loads(r["data"])
        score = f"**{r['llm_score']}**" if r["llm_score"] is not None else f"{r['pre_score']}*"
        print(f"| {score} | [{d['title'][:60]}]({d['url']}) | {d['company'][:30]} | {r['zone'] or d['location'][:25]} "
              f"| {r['remote']} | {r['contract']} | {r['status']} | `{r['uid']}` |")
    if not rows:
        print("| — | aucune offre éligible pour l'instant (lance `run.py`) | | | | | | |")
    print("\n(score en gras = revu par Claude ; * = pré-score automatique)")


def cmd_show(db: DB, uid: str) -> None:
    r = db.get_row(uid)
    if not r:
        sys.exit(f"offre introuvable : {uid}")
    d = json.loads(r["data"])
    print(f"# {d['title']} · {d['company']}\n")
    print(f"- uid : `{r['uid']}` · sources : {', '.join(json.loads(r['sources']))}")
    print(f"- lien : {d['url']}")
    print(f"- lieu : {d['location']} · zone : {r['zone'] or '—'} · remote : {r['remote']} ({r['remote_evidence']})")
    print(f"- contrat : {r['contract']} · salaire : {salary_label(d) or 'non affiché'} · publiée : {d.get('published_at', '')[:10]}")
    print(f"- filtre : {r['level']} ({r['reason']}) · statut : {r['status']}")
    print(f"- pré-score {r['pre_score']} : {' · '.join(json.loads(r['breakdown'] or '[]'))}")
    if r["llm"]:
        rev = json.loads(r["llm"])
        print(f"- revue Claude {r['llm_score']} : {rev.get('verdict', '')}")
        for k in ("forces", "manques"):
            for item in rev.get(k, []):
                print(f"  - {k[:-1]} : {item}")
    print(f"\n## Description\n\n{d.get('description', '')}")


def cmd_find(db: DB, text: str) -> None:
    words = norm(text).split()
    print("| uid | poste | entreprise | lieu | filtre | statut |\n|---|---|---|---|---|---|")
    n = 0
    for r in db.report_rows():
        d = json.loads(r["data"])
        hay = norm(f"{d['title']} {d['company']} {d['location']}")
        if all(w in hay for w in words):
            n += 1
            print(f"| `{r['uid']}` | {d['title'][:60]} | {d['company'][:30]} | {d['location'][:25]} "
                  f"| {r['level']} | {r['status']} |")
    if not n:
        print(f"| — | aucune offre ne correspond à « {text} » | | | | |")


def cmd_offer(db: DB, uid: str) -> None:
    r = db.get_row(uid)
    if not r:
        sys.exit(f"offre introuvable : {uid}")
    d = json.loads(r["data"])
    out = DATA_DIR / "offres" / f"{slug(d['company'])}-{slug(d['title'])}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {d['title']}", "", f"Entreprise : {d['company']}", f"Lieu : {d['location']}",
             f"Contrat : {r['contract']}", f"Télétravail : {r['remote']}", f"Lien : {d['url']}",
             f"Salaire : {salary_label(d) or 'non affiché'}", ""]
    if r["llm"]:
        rev = json.loads(r["llm"])
        lines += ["## Analyse de matching (jobsearch)", "", rev.get("verdict", ""), ""]
        lines += [f"- Force : {x}" for x in rev.get("forces", [])] + [f"- Manque : {x}" for x in rev.get("manques", [])] + [""]
    lines += ["## Annonce", "", d.get("description", "")]
    out.write_text("\n".join(lines))
    print(out)


def cmd_import(db: DB, path: str) -> None:
    reviews = json.loads(Path(path).read_text())
    ok, missing = 0, []
    for rev in reviews:
        if db.set_review(rev["uid"], rev):
            ok += 1
        else:
            missing.append(rev["uid"])
    print(f"{ok} revues enregistrées" + (f", introuvables : {', '.join(missing)}" if missing else ""))


def cmd_stats(db: DB) -> None:
    q = db.conn.execute
    print("Par verdict :", dict(q("SELECT level, COUNT(*) FROM jobs GROUP BY level").fetchall()))
    print("Par statut :", dict(q("SELECT status, COUNT(*) FROM jobs WHERE level != 'exclu' GROUP BY status").fetchall()))
    print("Revues :", q("SELECT COUNT(*) FROM jobs WHERE llm_score IS NOT NULL").fetchone()[0])
    print("Top raisons d'exclusion :")
    for reason, n in q("SELECT substr(reason, 1, 40) r, COUNT(*) c FROM jobs WHERE level = 'exclu' "
                       "GROUP BY r ORDER BY c DESC LIMIT 8"):
        print(f"  {n:4}  {reason}")
    print("Collectes :")
    for r in db.runs():
        print(f"  {r['source']:16} {r['last_run'][:16]}  {r['last_count']:4} offres  {r['last_error'] or ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("top").add_argument("--n", type=int, default=20)
    sub.add_parser("queue").add_argument("--limit", type=int)
    sub.add_parser("import-review").add_argument("file")
    sub.add_parser("show").add_argument("uid")
    sub.add_parser("find").add_argument("text")
    st = sub.add_parser("status")
    st.add_argument("uid")
    st.add_argument("status", choices=STATUSES)
    st.add_argument("--notes")
    sub.add_parser("offer").add_argument("uid")
    sub.add_parser("stats")
    args = ap.parse_args()

    warn_if_blank()
    db = DB()
    if args.cmd == "top":
        cmd_top(db, args.n)
    elif args.cmd == "queue":
        path, n = export_queue(db, load_config(), args.limit)
        print(f"{n} offres → {path}")
    elif args.cmd == "import-review":
        cmd_import(db, args.file)
    elif args.cmd == "show":
        cmd_show(db, args.uid)
    elif args.cmd == "find":
        cmd_find(db, args.text)
    elif args.cmd == "status":
        print("ok" if db.set_status(args.uid, args.status, args.notes) else f"offre introuvable : {args.uid}")
    elif args.cmd == "offer":
        cmd_offer(db, args.uid)
    elif args.cmd == "stats":
        cmd_stats(db)
    if args.cmd in ("import-review", "status"):
        import recap
        import report
        report.build(db)
        recap.build(db)


if __name__ == "__main__":
    main()
