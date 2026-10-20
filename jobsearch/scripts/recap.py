#!/usr/bin/env python3
"""Récap des candidatures : une fiche par offre, à relire quand un recruteur appelle.

    python3 recap.py                  # régénère DATA_DIR/candidatures.html
    python3 recap.py --find "acme"    # fiches correspondantes dans le terminal (nom, client, contact, numéro)
    python3 recap.py --check          # vérifie les fiches : champs requis, uid connus, fichiers présents

Une fiche = DATA_DIR/candidatures/<dossier>.json, écrite par Claude (format dans
references/recap.md). Tant que `envoye_le` est vide, la candidature est « prête ».
Les infos de l'offre (titre, lieu, salaire, lien, revue) sont lues dans jobs.db : la
fiche n'ajoute que ce qui s'est passé à l'envoi et ce qu'il faut savoir quand on rappelle.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA_DIR  # noqa: E402
from config import CV_MASTER, warn_if_blank  # noqa: E402
from db import DB  # noqa: E402
from filters import norm  # noqa: E402
from jobs import salary_label  # noqa: E402

FICHES_DIR = DATA_DIR / "candidatures"
CV_DIR = CV_MASTER.parent  # dossiers de candidature du skill cv : <workspace cv>/<dossier>/build
REQUIRED = ("uid", "dossier", "canal")


def digits(text: str) -> str:
    d = re.sub(r"\D", "", text or "")
    return "0" + d[2:] if d.startswith("33") and len(d) == 11 else d


def load_fiches() -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(FICHES_DIR.glob("*.json")):
        try:
            out.append((p, json.loads(p.read_text())))
        except json.JSONDecodeError as exc:
            print(f"fiche illisible, ignorée : {p.name} ({exc})", file=sys.stderr)
    return out


def enrich(db: DB, fiche: dict) -> dict:
    """Fusionne la fiche avec l'offre en base et les fichiers du dossier CV."""
    row = db.get_row(fiche.get("uid", ""))
    d = json.loads(row["data"]) if row else {}
    review = json.loads(row["llm"]) if row and row["llm"] else {}
    build = CV_DIR / fiche.get("dossier", "") / "build"
    files = {name: (build / f"{name}.pdf").as_uri() for name in ("cv", "lettre") if (build / f"{name}.pdf").exists()}
    capture = fiche.get("capture")
    if capture:
        cap = Path(capture) if Path(capture).is_absolute() else FICHES_DIR / capture
        capture = cap.as_uri() if cap.exists() else None
    return {
        **fiche,
        "found": bool(row),
        "title": d.get("title", fiche.get("poste", "")),
        "company": d.get("company", fiche.get("entreprise", "")),
        "url": d.get("url", ""),
        "location": d.get("location", ""),
        "remote": row["remote"] if row else "",
        "contract": row["contract"] if row else "",
        "salary": salary_label(d) if d else "",
        "status": row["status"] if row else "",
        "score": (row["llm_score"] or row["pre_score"]) if row else None,
        "verdict": review.get("verdict", ""),
        "forces": review.get("forces", []),
        "manques": review.get("manques", []),
        "files": files,
        "capture_uri": capture,
    }


def haystack(f: dict) -> tuple[str, str]:
    contacts = f.get("contacts") or []
    parts = [f.get("company"), f.get("intermediaire"), f.get("client_final"), f.get("title"), f.get("dossier"), f.get("canal")]
    parts += f.get("aussi_appele") or []
    parts += [c.get(k) for c in contacts for k in ("nom", "role", "email")]
    parts += [e.get("qui") for e in f.get("suivi") or []]
    phones = " ".join(digits(c.get("tel", "")) for c in contacts)
    return norm(" ".join(p for p in parts if p)), phones


def matches(f: dict, query: str) -> bool:
    text, phones = haystack(f)
    q_digits = digits(query)
    if len(q_digits) >= 4 and q_digits in phones:
        return True
    return all(w in text for w in norm(query).split())


def payload(db: DB) -> dict:
    items = [enrich(db, f) for _, f in load_fiches()]
    items.sort(key=lambda f: f.get("envoye_le") or "", reverse=True)
    for f in items:
        f["search"], f["phones"] = haystack(f)
    return {"generated": datetime.now().strftime("%d/%m/%Y %H:%M"), "items": items}


def render(db: DB) -> str:
    data = json.dumps(payload(db), ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)


def build(db: DB) -> Path:
    out = DATA_DIR / "candidatures.html"
    out.write_text(render(db))
    return out


def print_fiche(f: dict) -> None:
    inter = f.get("intermediaire")
    who = f["company"] + (f" (via {inter})" if inter and norm(inter) != norm(f["company"]) else "")
    if f.get("client_final"):
        who += f", client final : {f['client_final']}"
    sent = f.get("envoye_le") or "pas encore envoyée"
    print(f"## {who}\n{f['title']}\nEnvoyée : {sent} · {f.get('canal', '')} · statut {f.get('status', '?')}")
    remote = {"full": "full remote", "partial": "hybride", "none": "présentiel"}.get(f.get("remote"))
    where = [x for x in (f.get("location"), remote, f.get("contract"), f.get("salary")) if x]
    if where:
        print("Lieu : " + " · ".join(where))
    fiche = f.get("fiche") or {}
    if fiche.get("en_bref"):
        print(f"\nEn bref : {fiche['en_bref']}")
    for label, key in (("Ce que tu as dit", "ce_que_jai_dit"), ("Points faibles", "points_faibles"),
                       ("À leur demander", "a_leur_demander")):
        if fiche.get(key):
            print(f"\n{label} :")
            for x in fiche[key]:
                print(f"  - {x}")
    for qa in fiche.get("questions_probables") or []:
        print(f"\nQ : {qa.get('q')}\nR : {qa.get('r')}")
    for c in f.get("contacts") or []:
        print(f"\nContact : {c.get('nom', '')} {c.get('role', '')} {c.get('tel', '')} {c.get('email', '')}".rstrip())
    if f.get("reponses_formulaire"):
        print("\nRéponses données : " + ", ".join(f"{k} = {v}" for k, v in f["reponses_formulaire"].items()))
    print(f"\nDossier : {CV_DIR / f.get('dossier', '')}\n")


def check(db: DB) -> int:
    problems = 0
    for path, f in load_fiches():
        issues = [f"champ manquant : {k}" for k in REQUIRED if not f.get(k)]
        if f.get("uid") and not db.get_row(f["uid"]):
            issues.append(f"uid inconnu en base : {f['uid']}")
        if f.get("dossier") and not (CV_DIR / f["dossier"] / "build" / "cv.pdf").exists():
            issues.append(f"CV absent : {CV_DIR / f['dossier'] / 'build' / 'cv.pdf'}")
        if f.get("envoye_le") and not (f.get("fiche") or {}).get("en_bref"):
            issues.append("envoyée mais fiche « en_bref » vide")
        for msg in issues:
            print(f"{path.name} : {msg}")
        problems += len(issues)
    print(f"{len(load_fiches())} fiches, {problems} problème(s)")
    return problems


TEMPLATE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mes candidatures</title>
<style>
:root{--bg:#f6f5f2;--panel:#fff;--ink:#1d1d1b;--muted:#6b6a66;--line:#e4e2dc;--accent:#2b59c3;--good:#1f8a4c;--mid:#b7791f;--bad:#b83b3b;--chip:#efede7}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1d1d1b;--ink:#ecebe6;--muted:#9c9a93;--line:#2f2e2b;--accent:#7ea2ff;--good:#4cc27f;--mid:#e0a84a;--bad:#e07070;--chip:#2a2926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:20px 16px 60px}
header{position:sticky;top:0;background:var(--bg);padding:12px 0 10px;z-index:2;border-bottom:1px solid var(--line);margin-bottom:14px}
h1{font-size:21px;margin:0 0 2px}.gen{color:var(--muted);font-size:13px}
#q{width:100%;font:inherit;font-size:17px;padding:11px 14px;border:2px solid var(--line);border-radius:10px;background:var(--panel);color:var(--ink);margin-top:10px}
#q:focus{outline:none;border-color:var(--accent)}
h2{font-size:15px;color:var(--muted);font-weight:600;margin:22px 0 8px}
details{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-bottom:8px}
summary{list-style:none;cursor:pointer;padding:12px 14px;display:grid;grid-template-columns:1fr auto;gap:2px 12px}
summary::-webkit-details-marker{display:none}
summary:focus-visible{outline:3px solid var(--accent);outline-offset:2px;border-radius:10px}
.who{font-weight:650;font-size:16px}.via{color:var(--muted);font-weight:400}
.job{color:var(--muted);font-size:14px;grid-column:1}
.when{text-align:right;font-size:13px;color:var(--muted);grid-row:1 / span 2;grid-column:2;align-self:center}
.st{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:99px;background:var(--chip);margin-top:3px}
.st.postule{color:var(--accent)}.st.entretien{color:var(--good)}.st.refuse,.st.ecarte{color:var(--bad)}
.body{padding:2px 16px 16px;border-top:1px solid var(--line)}
.body h3{font-size:13px;color:var(--muted);font-weight:600;margin:16px 0 4px}
.body p{margin:0}.body ul{margin:0;padding-left:20px}.body li{margin:2px 0}
.brief{font-size:16px;margin-top:12px!important}
.facts{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:14px;color:var(--muted);margin-top:8px}
.qa{border-left:3px solid var(--line);padding:4px 0 4px 10px;margin:8px 0}
.qa b{display:block;font-weight:600}
.links{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.links a{font-size:14px;padding:6px 11px;border:1px solid var(--line);border-radius:8px;color:var(--accent);text-decoration:none}
.links a:hover{border-color:var(--accent)}
.contact{font-size:15px}.contact a{color:var(--accent)}
.empty{color:var(--muted);padding:12px 2px}
.log{font-size:14px}.log time{color:var(--muted);font-variant-numeric:tabular-nums;margin-right:6px}
mark{background:#ffe58a;color:#1d1d1b;border-radius:2px}
</style></head><body><div class="wrap">
<header>
  <h1>Mes candidatures</h1>
  <div class="gen" id="gen"></div>
  <input id="q" type="search" placeholder="Qui appelle ? Entreprise, cabinet, client, nom ou numéro" autocomplete="off" aria-label="Rechercher une candidature">
</header>
<main id="out"></main>
</div>
<script>
const DATA = __DATA__;
const REMOTE = {full:'full remote',partial:'hybride',none:'présentiel'};
const STATUS = {nouveau:'nouveau',vu:'vu',favori:'prête',postule:'postulé',entretien:'entretien',refuse:'refusé',ecarte:'écarté'};
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const digits = s => { let d = String(s || '').replace(/\D/g, ''); return d.startsWith('33') && d.length === 11 ? '0' + d.slice(2) : d; };
const fmt = iso => iso ? new Date(iso).toLocaleDateString('fr-FR', {day:'numeric', month:'short'}) : '';
const list = (xs) => xs && xs.length ? '<ul>' + xs.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>' : '';
const sec = (title, html) => html ? '<h3>' + title + '</h3>' + html : '';

function card(f, open) {
  const fi = f.fiche || {};
  const via = [f.intermediaire && norm(f.intermediaire) !== norm(f.company) && 'via ' + f.intermediaire, f.client_final && 'pour ' + f.client_final].filter(Boolean).join(', ');
  const facts = [f.location, REMOTE[f.remote] || '', f.contract, f.salary, f.canal].filter(Boolean)
    .map(x => '<span>' + esc(x) + '</span>').join('');
  const contacts = (f.contacts || []).map(c => '<p class="contact"><b>' + esc(c.nom) + '</b>' + (c.role ? ', ' + esc(c.role) : '') +
    (c.tel ? ' · <a href="tel:' + esc(digits(c.tel)) + '">' + esc(c.tel) + '</a>' : '') + (c.email ? ' · <a href="mailto:' + esc(c.email) + '">' + esc(c.email) + '</a>' : '') + '</p>').join('');
  const qa = (fi.questions_probables || []).map(x => '<div class="qa"><b>' + esc(x.q) + '</b>' + esc(x.r) + '</div>').join('');
  const reps = f.reponses_formulaire ? '<ul>' + Object.entries(f.reponses_formulaire).map(([k, v]) => '<li>' + esc(k) + ' : <b>' + esc(v) + '</b></li>').join('') + '</ul>' : '';
  const log = (f.suivi || []).map(e => '<p class="log"><time>' + esc(fmt(e.date)) + '</time>' + esc(e.evenement) + (e.qui ? ' (' + esc(e.qui) + ')' : '') + (e.notes ? ' : ' + esc(e.notes) : '') + '</p>').join('');
  const links = [f.files.cv && ['CV envoyé', f.files.cv], f.files.lettre && ['Lettre envoyée', f.files.lettre], f.url && ['Annonce', f.url], f.capture_uri && ['Capture de l\'envoi', f.capture_uri]]
    .filter(Boolean).map(([t, u]) => '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + t + '</a>').join('');
  const brief = fi.en_bref || f.verdict;
  return '<details' + (open ? ' open' : '') + '><summary>' +
    '<span class="who">' + esc(f.company) + (via ? ' <span class="via">' + esc(via) + '</span>' : '') + '</span>' +
    '<span class="when">' + (f.envoye_le ? 'envoyée le ' + esc(fmt(f.envoye_le)) : 'pas envoyée') + '<br><span class="st ' + esc(f.status) + '">' + esc(STATUS[f.status] || f.status) + '</span></span>' +
    '<span class="job">' + esc(f.title) + '</span></summary><div class="body">' +
    (brief ? '<p class="brief">' + esc(brief) + '</p>' : '') + (facts ? '<div class="facts">' + facts + '</div>' : '') +
    sec('Contact', contacts) +
    sec('Ce que tu leur as dit', list(fi.ce_que_jai_dit)) +
    sec('Pourquoi toi', list(fi.pourquoi_moi || f.forces)) +
    sec('Points faibles, et ta réponse', list(fi.points_faibles || f.manques)) +
    sec('Questions probables', qa) +
    sec('À leur demander', list(fi.a_leur_demander)) +
    sec('Réponses données dans le formulaire', reps) +
    sec('Suivi', log) +
    (links ? '<div class="links">' + links + '</div>' : '') +
    '</div></details>';
}

function draw() {
  const q = document.getElementById('q').value.trim();
  const qd = digits(q), words = norm(q).split(/\s+/).filter(Boolean);
  const hit = f => !q || (qd.length >= 4 && f.phones.includes(qd)) || words.every(w => f.search.includes(w));
  const items = DATA.items.filter(hit);
  const sent = items.filter(f => f.envoye_le), ready = items.filter(f => !f.envoye_le);
  const one = items.length === 1;
  let html = '';
  if (!items.length) html = '<p class="empty">Aucune candidature ne correspond à « ' + esc(q) + ' ». Essaie le nom du cabinet ou de l\'ESN : c\'est souvent l\'intermédiaire qui appelle.</p>';
  if (sent.length) html += '<h2>Envoyées (' + sent.length + ')</h2>' + sent.map(f => card(f, one)).join('');
  if (ready.length) html += '<h2>Prêtes, pas encore envoyées (' + ready.length + ')</h2>' + ready.map(f => card(f, one)).join('');
  document.getElementById('out').innerHTML = html;
}
document.getElementById('gen').textContent = DATA.items.filter(f => f.envoye_le).length + ' envoyées · mis à jour le ' + DATA.generated;
document.getElementById('q').addEventListener('input', draw);
draw();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--find", metavar="TEXTE", help="nom d'entreprise, de cabinet, de client, de contact, ou numéro")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    warn_if_blank()
    db = DB()
    if args.check:
        sys.exit(1 if check(db) else 0)
    if args.find:
        found = [enrich(db, f) for _, f in load_fiches()]
        found = [f for f in found if matches(f, args.find)]
        if not found:
            sys.exit(f"aucune candidature ne correspond à « {args.find} »")
        for f in found:
            print_fiche(f)
        return
    print(build(db))


if __name__ == "__main__":
    main()
