"""Historique SQLite : offres, doublons, statuts de candidature, cache géo, suivi des collectes.

Une offre vue sur plusieurs plateformes n'existe qu'une fois : la première vue
devient canonique, les suivantes sont enregistrées comme alias et complètent ses
champs manquants (remote, coordonnées, salaire…).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import DATA_DIR, Job
from config import norm
from filters import Verdict

STATUSES = ("nouveau", "vu", "favori", "postule", "entretien", "refuse", "ecarte")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  uid TEXT PRIMARY KEY,
  dedup_key TEXT,
  sources TEXT NOT NULL,          -- JSON : ["wttj", "francetravail"]
  aliases TEXT NOT NULL,          -- JSON : uids des doublons fusionnés
  data TEXT NOT NULL,             -- JSON : Job canonique fusionné
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  level TEXT, reason TEXT, zone TEXT, remote TEXT, remote_evidence TEXT, contract TEXT,
  pre_score INTEGER, breakdown TEXT,
  llm_score INTEGER, llm TEXT, reviewed_at TEXT,
  status TEXT NOT NULL DEFAULT 'nouveau', status_at TEXT, notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS jobs_dedup ON jobs(dedup_key);
CREATE TABLE IF NOT EXISTS aliases (uid TEXT PRIMARY KEY, canonical TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS geocache (key TEXT PRIMARY KEY, lat REAL, lon REAL, postcode TEXT);
CREATE TABLE IF NOT EXISTS source_runs (
  source TEXT PRIMARY KEY, last_run TEXT, last_count INTEGER, last_error TEXT
);
"""

_GENDER = re.compile(r"\b[hfmwx]\s*/\s*[hfmwx](\s*/\s*[a-z])?\b")
_TITLE_NOISE = re.compile(r"\(.*?\)|\b(cdi|cdd|freelance|full remote|remote|teletravail|hybride)\b|[^a-z0-9 ]")
_COMPANY_NOISE = re.compile(r"\b(sas|sasu|sa|sarl|group|groupe|france|inc|ltd|gmbh|io|ai)\b|[^a-z0-9]")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dedup_key(job: Job) -> str | None:
    company = _COMPANY_NOISE.sub("", norm(job.company))
    if not company:
        return None  # sans entreprise, impossible de rapprocher sans risque
    title = _TITLE_NOISE.sub(" ", _GENDER.sub(" ", norm(job.title)))
    return f"{company}|{' '.join(title.split())}"


def job_from_dict(d: dict[str, Any]) -> Job:
    names = {f.name for f in fields(Job)}
    return Job(**{k: v for k, v in d.items() if k in names})


def merge_jobs(base: Job, other: Job) -> Job:
    """Complète `base` avec ce que `other` sait de plus ; ne remplace jamais une info existante."""
    for f in fields(Job):
        if f.name in ("source", "source_id", "url"):
            continue
        mine, theirs = getattr(base, f.name), getattr(other, f.name)
        if f.name == "description":
            if len(theirs or "") > len(mine or ""):
                base.description = theirs
        elif f.name == "tags":
            base.tags = sorted(set(mine) | set(theirs))
        elif mine in (None, "", "unknown") and theirs not in (None, "", "unknown"):
            setattr(base, f.name, theirs)
    return base


class DB:
    def __init__(self, path: Path | None = None):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = path or DATA_DIR / "jobs.db"
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # base créée avant l'ajout du code postal au cache géo
        if "postcode" not in {r["name"] for r in self.conn.execute("PRAGMA table_info(geocache)")}:
            self.conn.execute("ALTER TABLE geocache ADD COLUMN postcode TEXT")
            self.conn.commit()

    # --- offres ---------------------------------------------------------------

    def canonical_uid(self, job: Job) -> str | None:
        row = self.conn.execute("SELECT uid FROM jobs WHERE uid = ?", (job.uid,)).fetchone()
        if row:
            return row["uid"]
        row = self.conn.execute("SELECT canonical FROM aliases WHERE uid = ?", (job.uid,)).fetchone()
        if row:
            return row["canonical"]
        key = dedup_key(job)
        if key:
            since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
            row = self.conn.execute(
                "SELECT uid FROM jobs WHERE dedup_key = ? AND last_seen >= ? ORDER BY first_seen LIMIT 1",
                (key, since)).fetchone()
            if row:
                return row["uid"]
        return None

    def get_job(self, uid: str) -> Job | None:
        row = self.conn.execute("SELECT data FROM jobs WHERE uid = ?", (uid,)).fetchone()
        return job_from_dict(json.loads(row["data"])) if row else None

    def get_row(self, uid: str) -> sqlite3.Row | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE uid = ?", (uid,)).fetchone()
        if row:
            return row
        alias = self.conn.execute("SELECT canonical FROM aliases WHERE uid = ?", (uid,)).fetchone()
        return self.conn.execute("SELECT * FROM jobs WHERE uid = ?", (alias["canonical"],)).fetchone() if alias else None

    def save(self, uid: str, job: Job, verdict: Verdict, score: int, breakdown: list[str],
             seen_as: Job | None = None, touch: bool = True) -> bool:
        """Insère ou met à jour l'offre canonique `uid`. `seen_as` = exemplaire qui vient d'être collecté
        (doublon éventuel). `touch=False` pour un simple recalcul : last_seen ne bouge pas.
        Renvoie True si l'offre est nouvelle."""
        ts = now()
        row = self.conn.execute("SELECT sources, aliases FROM jobs WHERE uid = ?", (uid,)).fetchone()
        verdict_cols = (verdict.level, verdict.reason, verdict.zone, verdict.remote,
                        verdict.remote_evidence, verdict.contract, score, json.dumps(breakdown, ensure_ascii=False))
        if row is None:
            self.conn.execute(
                """INSERT INTO jobs (uid, dedup_key, sources, aliases, data, first_seen, last_seen,
                   level, reason, zone, remote, remote_evidence, contract, pre_score, breakdown)
                   VALUES (?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, dedup_key(job), json.dumps([job.source]), json.dumps(job.to_dict(), ensure_ascii=False),
                 ts, ts, *verdict_cols))
            self.conn.commit()
            return True
        sources, aliases = set(json.loads(row["sources"])), set(json.loads(row["aliases"]))
        if seen_as is not None:
            sources.add(seen_as.source)
            if seen_as.uid != uid:
                aliases.add(seen_as.uid)
                self.conn.execute("INSERT OR IGNORE INTO aliases (uid, canonical) VALUES (?, ?)", (seen_as.uid, uid))
        self.conn.execute(
            """UPDATE jobs SET sources = ?, aliases = ?, data = ?,
               last_seen = CASE WHEN ? THEN ? ELSE last_seen END,
               level = ?, reason = ?, zone = ?, remote = ?, remote_evidence = ?, contract = ?,
               pre_score = ?, breakdown = ? WHERE uid = ?""",
            (json.dumps(sorted(sources)), json.dumps(sorted(aliases)), json.dumps(job.to_dict(), ensure_ascii=False),
             touch, ts, *verdict_cols, uid))
        # la revue de Claude a lu l'offre en entier : elle prime sur le filtre automatique
        self.conn.execute(
            "UPDATE jobs SET level = 'exclu', reason = 'revue : ' || COALESCE(json_extract(llm, '$.reason'), '') "
            "WHERE uid = ? AND json_extract(llm, '$.exclude') = 1", (uid,))
        self.conn.execute(
            "UPDATE jobs SET level = 'douteux', reason = 'revue : ' || COALESCE(json_extract(llm, '$.reason'), '') "
            "WHERE uid = ? AND level = 'ok' AND json_extract(llm, '$.remote_doubt') = 1", (uid,))
        self.conn.execute(
            "UPDATE jobs SET level = 'ok', reason = 'revue : ' || COALESCE(json_extract(llm, '$.reason'), '') "
            "WHERE uid = ? AND level = 'douteux' AND json_extract(llm, '$.remote_confirmed') = 1", (uid,))
        self.conn.commit()
        return False

    def all_uids(self) -> list[str]:
        return [r["uid"] for r in self.conn.execute("SELECT uid FROM jobs")]

    # --- statut et revue --------------------------------------------------------

    def set_status(self, uid: str, status: str, notes: str | None = None) -> bool:
        if status not in STATUSES:
            raise ValueError(f"statut inconnu : {status} (attendu : {', '.join(STATUSES)})")
        row = self.get_row(uid)
        if not row:
            return False
        self.conn.execute("UPDATE jobs SET status = ?, status_at = ? WHERE uid = ?", (status, now(), row["uid"]))
        if notes is not None:
            self.conn.execute("UPDATE jobs SET notes = ? WHERE uid = ?", (notes, row["uid"]))
        self.conn.commit()
        return True

    def set_review(self, uid: str, review: dict[str, Any]) -> bool:
        row = self.get_row(uid)
        if not row:
            return False
        score = review.get("score")
        self.conn.execute("UPDATE jobs SET llm_score = ?, llm = ?, reviewed_at = ? WHERE uid = ?",
                          (int(score) if score is not None else None, json.dumps(review, ensure_ascii=False),
                           now(), row["uid"]))
        if review.get("exclude"):
            self.conn.execute("UPDATE jobs SET level = 'exclu', reason = ? WHERE uid = ?",
                              (f"revue : {review.get('reason', 'incompatible')}", row["uid"]))
        elif review.get("remote_doubt"):
            self.conn.execute("UPDATE jobs SET level = 'douteux', reason = ? WHERE uid = ?",
                              (f"revue : {review.get('reason', 'remote à confirmer')}", row["uid"]))
        elif review.get("remote_confirmed") and row["level"] == "douteux":
            self.conn.execute("UPDATE jobs SET level = 'ok', reason = ? WHERE uid = ?",
                              (f"revue : {review.get('reason', 'remote confirmé')}", row["uid"]))
        self.conn.commit()
        return True

    def review_queue(self, limit: int) -> list[sqlite3.Row]:
        """Offres éligibles jamais relues, meilleures d'abord ; les douteuses passent aussi, pour trancher."""
        return self.conn.execute(
            """SELECT * FROM jobs WHERE level IN ('ok', 'douteux') AND llm_score IS NULL
               AND status NOT IN ('ecarte', 'refuse') ORDER BY pre_score DESC LIMIT ?""", (limit,)).fetchall()

    def report_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs ORDER BY COALESCE(llm_score, pre_score) DESC, last_seen DESC").fetchall()

    # --- géocodage et collectes -------------------------------------------------

    def geo_get(self, key: str) -> tuple | None:
        row = self.conn.execute("SELECT lat, lon, postcode FROM geocache WHERE key = ?", (key,)).fetchone()
        return (row["lat"], row["lon"], row["postcode"] or "") if row else None

    def geo_put(self, key: str, found: tuple) -> None:
        lat, lon, *rest = found
        self.conn.execute("INSERT OR REPLACE INTO geocache (key, lat, lon, postcode) VALUES (?, ?, ?, ?)",
                          (key, lat, lon, rest[0] if rest else ""))
        self.conn.commit()

    def last_run(self, source: str) -> datetime | None:
        row = self.conn.execute("SELECT last_run FROM source_runs WHERE source = ? AND last_error IS NULL",
                                (source,)).fetchone()
        return datetime.fromisoformat(row["last_run"]) if row and row["last_run"] else None

    def mark_run(self, source: str, count: int, error: str | None) -> None:
        self.conn.execute("INSERT OR REPLACE INTO source_runs (source, last_run, last_count, last_error) "
                          "VALUES (?, ?, ?, ?)", (source, now(), count, error))
        self.conn.commit()

    def runs(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM source_runs ORDER BY source").fetchall()
