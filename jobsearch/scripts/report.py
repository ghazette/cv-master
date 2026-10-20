#!/usr/bin/env python3
"""Rapport HTML autonome + mini-serveur local pour enregistrer les statuts.

    python3 report.py                  # régénère DATA_DIR/rapport.html
    python3 report.py --serve          # http://127.0.0.1:8765 : statuts et notes écrits dans jobs.db

Ouvert en file://, la page fonctionne en lecture ; les statuts restent alors dans le
navigateur (localStorage) tant qu'on ne passe pas par --serve.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA_DIR  # noqa: E402
from config import warn_if_blank  # noqa: E402
from db import DB, STATUSES  # noqa: E402

DESC_LIMIT = 4000


def payload(db: DB) -> dict:
    items = []
    for r in db.report_rows():
        d = json.loads(r["data"])
        full = r["level"] != "exclu"
        items.append({
            "uid": r["uid"], "title": d["title"], "company": d["company"], "url": d["url"],
            "location": d["location"], "zone": r["zone"], "remote": r["remote"], "remote_evidence": r["remote_evidence"],
            "contract": r["contract"], "level": r["level"], "reason": r["reason"],
            "pre": r["pre_score"], "llm": r["llm_score"], "review": json.loads(r["llm"]) if r["llm"] else None,
            "breakdown": json.loads(r["breakdown"] or "[]") if full else [],
            "salary": [d.get("salary_min"), d.get("salary_max"), d.get("salary_period")],
            "published": (d.get("published_at") or "")[:10], "first_seen": r["first_seen"][:10],
            "last_seen": r["last_seen"][:10], "sources": json.loads(r["sources"]),
            "status": r["status"], "notes": r["notes"],
            "description": (d.get("description") or "")[:DESC_LIMIT] if full else "",
        })
    return {"generated": datetime.now().strftime("%d/%m/%Y %H:%M"), "statuses": STATUSES, "jobs": items}


def render(db: DB) -> str:
    data = json.dumps(payload(db), ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)


def build(db: DB) -> Path:
    out = DATA_DIR / "rapport.html"
    out.write_text(render(db))
    return out


def serve(port: int, host: str = "127.0.0.1") -> None:
    db = DB()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, render(db).encode(), "text/html; charset=utf-8")
            elif self.path in ("/candidatures", "/candidatures.html"):
                import recap
                self._send(200, recap.render(db).encode(), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path != "/api/status":
                return self._send(404, b"not found", "text/plain")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                ok = db.set_status(body["uid"], body["status"], body.get("notes"))
                self._send(200 if ok else 404, json.dumps({"ok": ok}).encode(), "application/json")
            except (ValueError, KeyError) as exc:
                self._send(400, json.dumps({"ok": False, "error": str(exc)}).encode(), "application/json")

        def log_message(self, *args):  # silencieux
            pass

    shown = host if host not in ("0.0.0.0", "") else "<ip-de-la-machine>"
    print(f"Rapport : http://{shown}:{port}  ·  candidatures : http://{shown}:{port}/candidatures  (Ctrl+C pour arrêter)")
    if host != "127.0.0.1":
        print("Attention : accessible depuis le réseau, sans authentification.")
    HTTPServer((host, port), Handler).serve_forever()


TEMPLATE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offres</title>
<style>
:root{--bg:#f6f5f2;--panel:#fff;--ink:#1d1d1b;--muted:#6b6a66;--line:#e4e2dc;--accent:#2b59c3;--good:#1f8a4c;--mid:#b7791f;--bad:#b83b3b;--chip:#efede7}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1d1d1b;--ink:#ecebe6;--muted:#9c9a93;--line:#2f2e2b;--accent:#7ea2ff;--good:#4cc27f;--mid:#e0a84a;--bad:#e07070;--chip:#2a2926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:20px;margin:0}header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 20px;margin-bottom:14px}
.kpis{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted)}.kpis b{color:var(--ink);font-variant-numeric:tabular-nums}
.banner{background:var(--chip);border:1px solid var(--line);padding:8px 12px;border-radius:8px;margin-bottom:12px;color:var(--muted)}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:10px}
.tab{background:none;border:0;padding:8px 12px;cursor:pointer;color:var(--muted);font:inherit;border-bottom:2px solid transparent}
.tab.on{color:var(--ink);border-color:var(--accent);font-weight:600}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.filters input[type=search]{flex:1 1 220px;min-width:0}
input,select,textarea{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 8px}
.tbl{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:900px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);cursor:pointer;user-select:none;white-space:nowrap;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
tr.row{cursor:pointer}tr.row:hover{background:var(--chip)}
.score{font-variant-numeric:tabular-nums;font-weight:700;display:inline-flex;align-items:center;gap:6px}
.score i{display:inline-block;width:8px;height:8px;border-radius:50%}
.auto{color:var(--muted);font-weight:500}
.t{font-weight:600}.c{color:var(--muted)}.new{font-size:11px;background:var(--accent);color:#fff;border-radius:4px;padding:0 5px;margin-left:6px}
.chip{display:inline-block;background:var(--chip);border-radius:4px;padding:0 6px;margin:1px 2px 1px 0;font-size:12px;white-space:nowrap}
.detail td{background:var(--bg)}.detail .grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr);gap:18px}
@media (max-width:760px){.detail .grid{grid-template-columns:1fr}}
.detail h4{margin:0 0 6px;font-size:13px}.detail ul{margin:0 0 10px;padding-left:18px}
.desc{white-space:pre-wrap;max-height:340px;overflow:auto;font-size:13px;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.btn{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer;color:var(--ink);text-decoration:none;font:inherit}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.muted{color:var(--muted)}.empty{padding:30px;text-align:center;color:var(--muted)}
</style></head><body><div class="wrap">
<header><h1>Offres d'emploi</h1><div class="kpis" id="kpis"></div></header>
<div class="banner" id="banner" hidden></div>
<div class="tabs" id="tabs"></div>
<div class="filters">
  <input type="search" id="q" placeholder="Rechercher poste, entreprise, techno…">
  <select id="fStatus"></select>
  <select id="fRemote"><option value="">Tout mode</option><option value="full">Full remote</option><option value="site">Présentiel / hybride zone</option></select>
  <select id="fContract"><option value="">Tout contrat</option></select>
  <select id="fSource"><option value="">Toutes sources</option></select>
  <label class="muted">Score ≥ <input type="number" id="fMin" value="35" min="0" max="100" style="width:64px"></label>
</div>
<div class="tbl"><table><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const LIVE = location.protocol.startsWith('http');
const LS = 'jobsearch-status';
let local = {}; try { local = JSON.parse(localStorage.getItem(LS) || '{}'); } catch (e) {}
if (!LIVE) for (const j of DATA.jobs) if (local[j.uid]) j.status = local[j.uid];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const score = j => j.llm ?? j.pre ?? 0;
const today = new Date().toISOString().slice(0, 10);
const LABEL = {nouveau:'Nouveau', vu:'Vu', favori:'Favori', postule:'Postulé', entretien:'Entretien', refuse:'Refusé', ecarte:'Écarté'};
const REMOTE = {full:'Full remote', partial:'Hybride', none:'Présentiel', unclear:'À confirmer', unknown:'—'};
const TABS = [['ok','Éligibles'], ['douteux','À confirmer'], ['exclu','Exclues']];
let tab = 'ok', sortKey = 'score', sortDir = -1, open = null;

if (!LIVE) { const b = document.getElementById('banner'); b.hidden = false;
  b.textContent = "Lecture seule : les statuts restent dans ce navigateur. Pour les enregistrer dans l'historique, lance « python3 ~/.claude/skills/jobsearch/scripts/report.py --serve »."; }

const sources = [...new Set(DATA.jobs.flatMap(j => j.sources))].sort();
document.getElementById('fSource').innerHTML += sources.map(s => `<option>${esc(s)}</option>`).join('');
document.getElementById('fContract').innerHTML += [...new Set(DATA.jobs.map(j => j.contract).filter(Boolean))].sort().map(c => `<option>${esc(c)}</option>`).join('');
document.getElementById('fStatus').innerHTML = `<option value="actifs">Actives (sans écartées/refusées)</option><option value="">Tous statuts</option>` +
  DATA.statuses.map(s => `<option value="${s}">${LABEL[s]}</option>`).join('');

function kpis() {
  const ok = DATA.jobs.filter(j => j.level === 'ok');
  const k = [['éligibles', ok.length], ['nouvelles', ok.filter(j => j.status === 'nouveau').length],
    ['à confirmer', DATA.jobs.filter(j => j.level === 'douteux').length],
    ['postulées', DATA.jobs.filter(j => ['postule','entretien'].includes(j.status)).length]];
  document.getElementById('kpis').innerHTML = k.map(([l, n]) => `<span><b>${n}</b> ${l}</span>`).join('') + `<span>maj ${esc(DATA.generated)}</span>`;
  document.getElementById('tabs').innerHTML = TABS.map(([id, l]) =>
    `<button class="tab ${id === tab ? 'on' : ''}" data-tab="${id}">${l} (${DATA.jobs.filter(j => j.level === id).length})</button>`).join('');
}

function salary(j) {
  const [lo, hi, per] = j.salary; if (!lo && !hi) return '';
  const k = v => per === 'year' || !per ? Math.round(v / 1000) + 'k' : Math.round(v);
  const unit = {year:'€/an', month:'€/mois', day:'€/j', hour:'€/h'}[per] || '€';
  return (lo && hi && lo !== hi ? `${k(lo)}–${k(hi)}` : k(hi || lo)) + ' ' + unit;
}

function rows() {
  const q = document.getElementById('q').value.toLowerCase(), st = document.getElementById('fStatus').value,
    rm = document.getElementById('fRemote').value, ct = document.getElementById('fContract').value,
    src = document.getElementById('fSource').value, min = +document.getElementById('fMin').value || 0;
  return DATA.jobs.filter(j => j.level === tab
    && (!q || (j.title + ' ' + j.company + ' ' + j.location + ' ' + j.description).toLowerCase().includes(q))
    && (st === '' || (st === 'actifs' ? !['ecarte', 'refuse'].includes(j.status) : j.status === st))
    && (!rm || (rm === 'full' ? j.remote === 'full' : !!j.zone))
    && (!ct || j.contract === ct) && (!src || j.sources.includes(src)) && score(j) >= min)
  .sort((a, b) => {
    const v = {score: j => score(j), title: j => j.title.toLowerCase(), company: j => j.company.toLowerCase(),
      published: j => j.published || j.first_seen, status: j => DATA.statuses.indexOf(j.status)}[sortKey];
    return (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0) * sortDir;
  });
}

const COLS = [['score','Score'], ['title','Poste'], ['company','Lieu'], [null,'Mode'], [null,'Contrat'], [null,'Salaire'], [null,'Sources'], ['published','Publiée'], ['status','Statut']];

function draw() {
  kpis();
  document.getElementById('head').innerHTML = COLS.map(([k, l]) =>
    `<th ${k ? `data-sort="${k}"` : ''}>${l}${k === sortKey ? (sortDir < 0 ? ' ↓' : ' ↑') : ''}</th>`).join('');
  const list = rows();
  if (!list.length) { document.getElementById('body').innerHTML = `<tr><td colspan="9" class="empty">Aucune offre avec ces filtres.</td></tr>`; return; }
  document.getElementById('body').innerHTML = list.map(j => {
    const s = score(j), color = s >= 70 ? 'var(--good)' : s >= 50 ? 'var(--mid)' : 'var(--bad)';
    const isNew = j.first_seen === today;
    const main = `<tr class="row" data-uid="${esc(j.uid)}">
      <td><span class="score ${j.llm == null ? 'auto' : ''}" title="${j.llm == null ? 'pré-score automatique' : 'revu par Claude (auto : ' + j.pre + ')'}"><i style="background:${color}"></i>${s}</span></td>
      <td><div class="t">${esc(j.title)}${isNew ? '<span class="new">nouveau</span>' : ''}</div><div class="c">${esc(j.company)}</div>${j.level === 'exclu' ? `<div class="muted">${esc(j.reason)}</div>` : ''}</td>
      <td>${esc(j.zone || j.location || '—')}</td><td>${REMOTE[j.remote] || esc(j.remote)}</td><td>${esc(j.contract)}</td>
      <td>${esc(salary(j))}</td><td>${j.sources.map(x => `<span class="chip">${esc(x)}</span>`).join('')}</td>
      <td class="muted">${esc(j.published || j.first_seen)}</td>
      <td><select data-status="${esc(j.uid)}">${DATA.statuses.map(x => `<option value="${x}" ${x === j.status ? 'selected' : ''}>${LABEL[x]}</option>`).join('')}</select></td></tr>`;
    return main + (open === j.uid ? detail(j) : '');
  }).join('');
}

function detail(j) {
  const r = j.review;
  const review = r ? `<h4>Revue Claude : ${j.llm}/100</h4><p>${esc(r.verdict)}</p>
    ${r.forces?.length ? `<ul>${r.forces.map(x => `<li>✔ ${esc(x)}</li>`).join('')}</ul>` : ''}
    ${r.manques?.length ? `<ul>${r.manques.map(x => `<li>✘ ${esc(x)}</li>`).join('')}</ul>` : ''}` : '<p class="muted">Pas encore revue par Claude.</p>';
  return `<tr class="detail"><td colspan="9"><div class="grid"><div>
    ${review}
    <h4>Pourquoi ce lieu passe</h4><p>${esc(j.reason)}${j.remote_evidence ? ` <span class="muted">« ${esc(j.remote_evidence)} »</span>` : ''}</p>
    <h4>Pré-score ${j.pre}</h4><ul>${j.breakdown.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
    <div class="actions"><a class="btn primary" href="${esc(j.url)}" target="_blank" rel="noopener">Ouvrir l'offre</a>
    <button class="btn" data-copy="Adapte mon CV à l'offre jobsearch ${esc(j.uid)}">Copier la demande CV</button></div>
    <label class="muted">Notes<br><textarea data-notes="${esc(j.uid)}" rows="3" style="width:100%">${esc(j.notes)}</textarea></label>
  </div><div><h4>${esc(j.location)}</h4><div class="desc">${esc(j.description) || '<span class="muted">Description non fournie par la source.</span>'}</div></div></div></td></tr>`;
}

async function saveStatus(uid, status, notes) {
  const j = DATA.jobs.find(x => x.uid === uid); if (status) j.status = status; if (notes != null) j.notes = notes;
  if (LIVE) {
    const res = await fetch('/api/status', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({uid, status: j.status, notes: j.notes})});
    if (!res.ok) alert("Échec de l'enregistrement du statut");
  } else { local[uid] = j.status; try { localStorage.setItem(LS, JSON.stringify(local)); } catch (e) {} }
}

document.addEventListener('click', e => {
  const t = e.target;
  if (t.dataset.tab) { tab = t.dataset.tab; open = null; return draw(); }
  if (t.dataset.sort) { sortDir = sortKey === t.dataset.sort ? -sortDir : -1; sortKey = t.dataset.sort; return draw(); }
  if (t.dataset.copy) { navigator.clipboard?.writeText(t.dataset.copy); t.textContent = 'Copié ✓'; return; }
  if (t.closest('select, a, button, textarea, input')) return;
  const row = t.closest('tr.row'); if (!row) return;
  const uid = row.dataset.uid; open = open === uid ? null : uid;
  const j = DATA.jobs.find(x => x.uid === uid);
  if (open && j.status === 'nouveau') saveStatus(uid, 'vu');
  draw();
});
document.addEventListener('change', e => {
  if (e.target.dataset.status) { saveStatus(e.target.dataset.status, e.target.value); kpis(); }
  else if (e.target.dataset.notes) saveStatus(e.target.dataset.notes, null, e.target.value);
  else draw();
});
document.getElementById('q').addEventListener('input', draw);
draw();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 pour y accéder depuis un autre appareil du réseau local")
    args = ap.parse_args()
    warn_if_blank()
    if args.serve:
        serve(args.port, args.host)
    else:
        print(build(DB()))


if __name__ == "__main__":
    main()
