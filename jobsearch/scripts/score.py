"""Pré-score 0-100 d'une offre face au profil (DATA_DIR/profile.json).

Rapide, déterministe et explicable : il trie des centaines d'offres pour que la
lecture attentive (revue par Claude) porte sur le haut du panier. Il ne la
remplace pas : un mot-clé présent ne dit pas si c'est le cœur du poste.

Barème : rôle (0-40) + compétences (0-35) + séniorité (0-10) + salaire (0-6)
+ fraîcheur (0-4) + pénalités. Borné à 0-100.

Rôles, compétences, pénalités et années d'expérience sont lus dans profile.json ;
cible et minimum de salaire de config.json (`salary_target`).
"""
from __future__ import annotations

import re
from typing import Any

from common import Job, age_days
from config import load_profile, norm  # noqa: F401  (load_profile réexporté pour run.py)


_YEARS = [
    re.compile(r"(\d{1,2})\s*\+?\s*(?:ans|annees|years?)\s*(?:d'|de |of )?(?:experience|minimum|min\b)"),
    re.compile(r"(?:minimum|au moins|at least|plus de)\s*(\d{1,2})\s*(?:ans|annees|years?)"),
]
_SENIOR_TITLE = re.compile(r"\b(senior|confirme|experimente|lead|expert|staff|principal)\b")
_K_SALARY = re.compile(r"(\d{2,3})\s?(?:k|k€|keur|000\s?€|\s000\s?(?:€|eur))")
_DAY_RATE = [
    re.compile(r"(\d{3,4})\s?(?:€|eur|euros)?\s?(?:ht\s?)?(?:/\s?j(?:our)?\b|par jour|/day|per day)"),
    re.compile(r"tjm[^0-9]{0,25}(\d{3,4})"),
]


class Scorer:
    def __init__(self, profile: dict[str, Any], salary_target: dict[str, float]):
        self.roles = [{
            **r,
            "title_rx": [re.compile(p) for p in r["title"]],
            "needs_rx": re.compile(r["needs"]) if r.get("needs") else None,
        } for r in profile["roles"]]
        self.skills = [(re.compile(p), w, label) for p, w, label in profile["skills"]]
        self.skills_cap = profile.get("skills_cap", 35)
        # années d'expérience du CV : sert à juger « 5 ans minimum », « 10+ ans »… (6 si non renseigné)
        self.experience = int(profile.get("experience_years") or 6)
        self.penalties = [{
            **p,
            "rx": re.compile(p["pattern"]),
            "unless_rx": re.compile(p["unless"]) if p.get("unless") else None,
            "unless_title_rx": re.compile(p["unless_title"]) if p.get("unless_title") else None,
        } for p in profile["penalties"]]
        self.target = {k: v for k, v in (salary_target or {}).items() if not k.startswith("_")}

    def score(self, job: Job) -> tuple[int, list[str]]:
        title = norm(job.title)
        text = norm(f"{job.title}\n{job.description}")
        parts: list[str] = []

        # 1. rôle : le titre dit ce qu'on attend de toi au quotidien
        role_pts, role_name = 0, "hors cible"
        for role in self.roles:
            if any(rx.search(title) for rx in role["title_rx"]):
                pts = role["points"]
                if role["needs_rx"] and not role["needs_rx"].search(text):
                    pts = role.get("points_if_missing", 0)
                if pts > role_pts:
                    role_pts, role_name = pts, role["name"]
        parts.append(f"rôle {role_name} +{role_pts}")

        # 2. compétences du CV citées dans l'offre
        found = [(label, w) for rx, w, label in self.skills if rx.search(text)]
        skill_pts = min(self.skills_cap, sum(w for _, w in found))
        parts.append(f"compétences +{skill_pts}" + (f" ({', '.join(l for l, _ in found)})" if found else ""))

        # 3. pénalités : stack ou métier qui éloignent du profil
        penalty = 0
        for p in self.penalties:
            haystack = title if p.get("where") == "title" else text
            excused = (p["unless_rx"] and p["unless_rx"].search(text)) or \
                      (p["unless_title_rx"] and p["unless_title_rx"].search(title))
            if p["rx"].search(haystack) and not excused:
                penalty += p["points"]
                parts.append(f"{p['label']} {p['points']}")

        # 4. séniorité : années demandées face aux années du CV (experience_years)
        years = [int(m.group(1)) for rx in _YEARS for m in rx.finditer(text) if 1 <= int(m.group(1)) <= 20]
        if not years:
            sen_pts = 6
        else:
            need = max(years)
            sen_pts = 10 if need <= self.experience + 2 else 5 if need <= self.experience + 4 else 0
        if _SENIOR_TITLE.search(title) and self.experience >= 5:
            sen_pts = max(sen_pts, 8)
        parts.append(f"séniorité +{sen_pts}" + (f" ({max(years)} ans demandés)" if years else ""))

        # 5. salaire : bonus seulement, jamais de pénalité (beaucoup d'offres n'affichent rien)
        sal_pts, sal_note = self._salary_bonus(job, text)
        if sal_pts > 0:
            parts.append(f"salaire +{sal_pts} ({sal_note})")
        elif sal_pts < 0:
            parts.append(f"salaire sous le minimum {sal_pts} ({sal_note})")

        # 6. fraîcheur : une offre récente a plus de chances d'être encore ouverte
        age = age_days(job.published_at)
        fresh = 1 if age is None else 4 if age <= 3 else 3 if age <= 7 else 2 if age <= 14 else 1 if age <= 30 else 0
        parts.append(f"fraîcheur +{fresh}")

        total = max(0, min(100, role_pts + skill_pts + sen_pts + sal_pts + fresh + penalty))
        return total, parts

    def _salary_bonus(self, job: Job, text: str) -> tuple[int, str]:
        year = day = None
        if job.salary_currency not in ("", "EUR"):
            return 0, ""  # pas de conversion de devise : on ne compare pas des dollars à une cible en euros
        if job.salary_max or job.salary_min:
            v = job.salary_max or job.salary_min
            period = job.salary_period
            if period == "day":
                day = v
            elif period == "hour":
                year = v * 1607
            elif period == "month":
                year = v * 12
            else:
                year = v
        else:
            ks = [int(m.group(1)) * 1000 for m in _K_SALARY.finditer(text) if 25 <= int(m.group(1)) <= 250]
            days = [int(m.group(1)) for rx in _DAY_RATE for m in rx.finditer(text) if 200 <= int(m.group(1)) <= 1500]
            year = max(ks) if ks else None
            day = max(days) if days else None
        for value, target, unit in ((year, self.target.get("year"), "€/an"), (day, self.target.get("day"), "€/j")):
            if value and target:
                if value >= target:
                    return 6, f"{int(value)} {unit}"
                if value >= 0.9 * target:
                    return 3, f"{int(value)} {unit}"
        # minimum : seulement si le salaire affiché (fourchette haute) est franchement en dessous
        for value, floor, unit in ((year, self.target.get("min_year"), "€/an"), (day, self.target.get("min_day"), "€/j")):
            if value and floor and value < floor:
                return -10, f"{int(value)} {unit} < {int(floor)}"
        return 0, ""
