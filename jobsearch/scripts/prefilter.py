"""Pré-filtre métier des sources qui ramènent un flux entier (remote boards, pages carrières, HN).

Ces sources ne savent pas chercher par mot-clé (ou mal) : sans tri, elles rempliraient
l'historique d'offres hors métier. Le tri se règle dans config.json, clé `prefilter`
(motifs regex appliqués au texte en minuscules SANS accents) :

    title          le titre doit contenir l'un de ces motifs (le métier) ;
    title_exclude  faux positifs à écarter (« business developer » pour un dev…) ;
    stack          signal de spécialité cherché dans le titre ou les tags ;
    stack_text     mots très discriminants cherchés dans la description.

Listes vides → motifs déduits des requêtes (queries.fr + queries.en) : un titre qui
contient un mot d'une requête passe. Large mais jamais vide, quel que soit le métier.
"""
from __future__ import annotations

import re
from typing import Any

from config import norm

# mots trop courts ou trop vagues pour servir de motif déduit des requêtes
_STOP = {
    "de", "du", "des", "la", "le", "les", "et", "en", "a", "au", "aux", "pour", "sur", "un", "une",
    "the", "and", "of", "for", "in", "to", "with", "h", "f", "hf", "fh", "x", "senior", "junior",
    "confirme", "lead", "remote", "teletravail", "cdi", "freelance", "stage",
}
MAX_TAGS = 12  # au-delà, une liste de tags est un fourre-tout et ne prouve rien


def _compile(patterns: list[str] | None) -> re.Pattern | None:
    pats = [p for p in (patterns or []) if p and not p.startswith("_")]
    return re.compile("|".join(f"(?:{p})" for p in pats)) if pats else None


def words_from_queries(cfg: dict[str, Any]) -> list[str]:
    q = cfg.get("queries") or {}
    words: list[str] = []
    for query in (q.get("fr") or []) + (q.get("en") or []):
        for w in re.split(r"[^a-z0-9+#.]+", norm(query)):
            w = w.strip(".")
            if len(w) >= 2 and w not in _STOP and w not in words:
                words.append(w)
    return words


class Prefilter:
    def __init__(self, cfg: dict[str, Any]):
        p = cfg.get("prefilter") or {}
        derived = [rf"\b{re.escape(w)}\b" for w in words_from_queries(cfg)]
        self.title = _compile(p.get("title")) or _compile(derived)
        self.exclude = _compile(p.get("title_exclude"))
        self.stack = _compile(p.get("stack"))
        self.stack_text = _compile(p.get("stack_text")) or self.stack

    # --- briques ------------------------------------------------------------------

    def role(self, title: str) -> bool:
        """Le titre ressemble au métier visé (et n'est pas un faux positif connu)."""
        t = norm(title)
        if self.title is None:
            return True
        if not self.title.search(t):
            return False
        # un signal de spécialité dans le titre l'emporte sur l'exclusion (« Fullstack Engineer - Payroll »)
        return not (self.exclude and self.exclude.search(t) and not (self.stack and self.stack.search(t)))

    def stack_hit(self, title: str, tags: list[str] | None = None, description: str = "",
                  max_tags: int | None = MAX_TAGS) -> bool:
        """Signal de spécialité dans le titre, un tag ou la description. Toujours vrai si aucun motif."""
        if self.stack is None and self.stack_text is None:
            return True
        tags = tags or []
        specific = max_tags is None or len(tags) <= max_tags
        if self.stack and self.stack.search(norm(title)):
            return True
        if specific and self.stack and any(self.stack.fullmatch(norm(t).strip()) for t in tags):
            return True
        return bool(specific and self.stack_text and description and self.stack_text.search(norm(description)))

    # --- usages -------------------------------------------------------------------

    def pertinent(self, title: str, tags: list[str] | None = None, description: str = "",
                  max_tags: int | None = MAX_TAGS) -> bool:
        """Métier visé ET spécialité (titre, tags ou description) : remote boards."""
        return self.role(title) and self.stack_hit(title, tags, description, max_tags)

    def any_signal(self, text: str) -> bool:
        """Un texte libre (commentaire HN, catégories Codeur) parle-t-il du métier ou de la spécialité ?"""
        t = norm(text)
        return any(rx is not None and rx.search(t) for rx in (self.title, self.stack, self.stack_text))
