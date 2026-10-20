#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-jobspy"]
# ///
"""Collecte → filtre → score → historique → file de revue → rapport HTML.

    uv run ~/.claude/skills/jobsearch/scripts/run.py                    # collecte complète
    uv run ~/.claude/skills/jobsearch/scripts/run.py --sources wttj,apec --force
    uv run ~/.claude/skills/jobsearch/scripts/run.py --no-scrape        # sans LinkedIn/Indeed/Glassdoor
    python3 ~/.claude/skills/jobsearch/scripts/run.py --rescore         # recalcule filtres + scores, sans réseau de collecte
    python3 ~/.claude/skills/jobsearch/scripts/run.py --list            # état des sources

`uv run` installe python-jobspy à la volée ; `python3` suffit si on n'utilise pas les sources scrape.
Premier lancement : `python3 ~/.claude/skills/jobsearch/scripts/init.py` puis l'onboarding (SKILL.md).
"""
from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources  # noqa: E402
from common import Context, Job, load_config, load_env, make_session  # noqa: E402
from config import complete_places  # noqa: E402
from db import DB, merge_jobs  # noqa: E402
from filters import Geocoder, evaluate  # noqa: E402
from score import Scorer, load_profile  # noqa: E402


def discover() -> list:
    mods = []
    for info in pkgutil.iter_modules(sources.__path__):
        try:
            mod = importlib.import_module(f"sources.{info.name}")
        except Exception as exc:  # un module cassé ne doit pas bloquer les autres
            print(f"  ! import sources.{info.name} impossible : {exc}", file=sys.stderr)
            continue
        if hasattr(mod, "fetch") and hasattr(mod, "NAME"):
            mods.append(mod)
    return sorted(mods, key=lambda m: m.NAME)


def select(mods, args, cfg, env, db) -> tuple[list, list[tuple[str, str]]]:
    chosen, skipped = [], []
    wanted = set(args.sources.split(",")) if args.sources else None
    for mod in mods:
        if wanted and mod.NAME not in wanted:
            continue
        reason = None
        missing = [k for k in getattr(mod, "REQUIRES", []) if k not in env]
        if mod.NAME in cfg.get("sources_disabled", []):
            reason = "désactivée dans config.json"
        elif getattr(mod, "KIND", "api") == "scrape" and (args.no_scrape or not cfg.get("scrape")):
            reason = "scraping désactivé"
        elif missing:
            reason = f"clé manquante : {', '.join(missing)}"
        elif not args.force:
            last, interval = db.last_run(mod.NAME), getattr(mod, "MIN_INTERVAL_H", 0)
            if last and datetime.now(timezone.utc) - last < timedelta(hours=interval):
                hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
                reason = f"collectée il y a {hours:.1f} h (délai mini {interval} h, --force pour ignorer)"
        if reason:
            skipped.append((mod.NAME, reason))
        else:
            chosen.append(mod)
    return chosen, skipped


def collect(mod, cfg, env) -> tuple[list[Job], str | None, float]:
    """Exécuté dans un thread : chaque source a sa propre session HTTP."""
    t0 = time.monotonic()
    logs: list[str] = []
    ctx = Context(cfg, env, make_session(), lambda msg: logs.append(f"[{mod.NAME}] {msg}"))
    try:
        jobs = [j for j in mod.fetch(ctx) if j.title and j.url]
        err = None
    except Exception as exc:
        jobs, err = [], f"{type(exc).__name__}: {exc}"
    for line in logs[-5:]:
        print("   ", line, file=sys.stderr)
    return jobs, err, time.monotonic() - t0


def ingest(db: DB, jobs: list[Job], cfg, geo: Geocoder, scorer: Scorer) -> dict[str, int]:
    stats = {"new": 0, "new_ok": 0, "merged": 0}
    for job in jobs:
        canon = db.canonical_uid(job)
        if canon is None:
            uid, merged = job.uid, job
        elif canon == job.uid:
            # même offre revue : les données fraîches priment, l'ancien exemplaire comble les trous
            uid, merged = canon, merge_jobs(job, db.get_job(canon))
        else:
            uid, merged = canon, merge_jobs(db.get_job(canon), job)
            stats["merged"] += 1
        verdict = evaluate(merged, cfg, geo)
        score, breakdown = scorer.score(merged)
        if db.save(uid, merged, verdict, score, breakdown, seen_as=job):
            stats["new"] += 1
            stats["new_ok"] += verdict.level == "ok"
    return stats


def rescore(db: DB, cfg, geo: Geocoder, scorer: Scorer) -> None:
    uids = db.all_uids()
    for uid in uids:
        job = db.get_job(uid)
        verdict = evaluate(job, cfg, geo)
        score, breakdown = scorer.score(job)
        db.save(uid, job, verdict, score, breakdown, touch=False)
    print(f"{len(uids)} offres recalculées.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", help="liste de NAME séparés par des virgules")
    ap.add_argument("--force", action="store_true", help="ignore MIN_INTERVAL_H")
    ap.add_argument("--no-scrape", action="store_true")
    ap.add_argument("--rescore", action="store_true", help="recalcule sans collecter")
    ap.add_argument("--list", action="store_true", help="affiche l'état des sources")
    args = ap.parse_args()

    cfg, env = load_config(require_ready=not args.list), load_env()
    db = DB()
    mods = discover()

    if args.list:
        chosen, skipped = select(mods, argparse.Namespace(**{**vars(args), "force": False}), cfg, env, db)
        runs = {r["source"]: r for r in db.runs()}
        print("| source | type | état | dernière collecte |\n|---|---|---|---|")
        for mod in mods:
            state = next((r for n, r in skipped if n == mod.NAME), "prête")
            r = runs.get(mod.NAME)
            last = f"{r['last_run'][:16]} · {r['last_count']} offres" + (f" · ERREUR {r['last_error']}" if r and r["last_error"] else "") if r else "jamais"
            print(f"| {mod.NAME} | {getattr(mod, 'KIND', 'api')} | {state} | {last} |")
        return

    geo = Geocoder(db.geo_get, db.geo_put)
    scorer = Scorer(load_profile(require_ready=True), cfg.get("salary_target", {}))
    # lieux saisis par nom seulement : coordonnées complétées en mémoire (init.py --geocode les écrit)
    for line in complete_places(cfg):
        print(f"  · {line}", file=sys.stderr)

    if args.rescore:
        rescore(db, cfg, geo, scorer)
    else:
        chosen, skipped = select(mods, args, cfg, env, db)
        for name, reason in skipped:
            print(f"  – {name} : {reason}")
        print(f"Collecte sur {len(chosen)} sources…")
        results = {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(collect, mod, cfg, env): mod for mod in chosen}
            for fut in as_completed(futures):
                mod = futures[fut]
                results[mod.NAME] = fut.result()
                jobs, err, dt = results[mod.NAME]
                print(f"  ✓ {mod.NAME}: {len(jobs)} offres en {dt:.0f} s" + (f"  ⚠ {err}" if err else ""))

        # ingestion séquentielle : SQLite et le géocodeur ne sont pas partagés entre threads
        print("\n| source | ramenées | nouvelles | nouvelles éligibles | fusionnées | erreur |\n|---|---|---|---|---|---|")
        for name, (jobs, err, _) in sorted(results.items()):
            st = ingest(db, jobs, cfg, geo, scorer)
            db.mark_run(name, len(jobs), err)
            print(f"| {name} | {len(jobs)} | {st['new']} | {st['new_ok']} | {st['merged']} | {err or ''} |")

    import jobs as jobs_cli  # noqa: E402
    import report  # noqa: E402
    queue_path, n_queue = jobs_cli.export_queue(db, cfg)
    report_path = report.build(db)
    counts = {r[0]: r[1] for r in db.conn.execute("SELECT level, COUNT(*) FROM jobs GROUP BY level")}
    print(f"\nHistorique : {counts.get('ok', 0)} éligibles · {counts.get('douteux', 0)} à confirmer · "
          f"{counts.get('exclu', 0)} exclues")
    print(f"File de revue : {n_queue} offres → {queue_path}")
    print(f"Rapport : {report_path}")


if __name__ == "__main__":
    main()
