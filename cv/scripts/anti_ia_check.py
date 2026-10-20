#!/usr/bin/env python3
"""Compte les marqueurs de texte genere par IA dans un CV ou une lettre (.md).

Usage:
    python3 anti_ia_check.py <fichier.md> [<fichier2.md> ...]
    python3 anti_ia_check.py societe/cv.md societe/lettre.md   # detecte les doublons

Ne juge pas le contenu, uniquement ce qui se compte. Le reste releve du
jugement, avec references/anti-ia.md.

Code de sortie: 0 si aucun signal bloquant, 1 sinon.
"""

import re
import sys
import unicodedata
from pathlib import Path

# --- signaux bloquants ------------------------------------------------------

PONCTUATION = {
    "\u2014": "tiret cadratin",
    ";": "point-virgule",
}

LEXIQUE = [
    # ouvertures
    r"c'est avec un grand int",
    r"a retenu mon attention",
    r"fort de mes? \w+ ann",
    r"riche de mon parcours",
    r"dot[ée] d'une solide",
    r"reconnue pour son",
    r"en tant que \w+ passionn",
    # auto-description
    r"passionn[ée] par l'innovation",
    r"force de proposition",
    r"esprit d'[ée]quipe et autonomie",
    r"v[ée]ritable atout",
    r"r[ée]elle valeur ajout",
    r"relever de nouveaux d[ée]fis",
    r"environnement stimulant",
    r"mettre mes comp[ée]tences au service",
    r"\ballie\b.{0,30}\bet\b",
    r"\bconjugue\b",
    r"[àa] la crois[ée]e de",
    # vocabulaire
    r"\b[ée]cosyst[èe]me",
    r"\blevier",
    r"\bsynergie",
    r"\bholistique",
    r"\btransversal",
    r"s'inscri\w+ pleinement",
    r"en parfaite ad[ée]quation",
    r"au c[oœ]ur de ma d[ée]marche",
    r"faire [ée]cho [àa]",
    r"\bincarn(e|er)\b",
    r"\bcatalys",
    r"\borchestr",
    r"de bout en bout",
    r"\benjeux\b",
    r"\bprobl[ée]matiques\b",
    r"terrain que je connais",
    r"conditions r[ée]elles",
    r"la rigueur que",
    # clotures
    r"[àa] votre enti[èe]re disposition",
    r"complément d'information",
    r"ravi d'[ée]changer",
    r"heureux d'[ée]changer",
    r"de vive voix",
    r"\ben somme\b",
    # structures
    r"je ne me contente pas",
    r"n'est pas (une formule|un simple|qu'un)",
    r"plus qu'un simple",
    r"non pas .{1,40} mais",
    r"tant sur le plan",
    r"ce qui me motive, c'est",
    r"ce qui m'a marqu[ée], c'est",
    r"(?:^|[.!?]\s+)concernant .{1,40}:",
    r"(?:^|[.!?]\s+)s'agissant de",
    r"devrait se faire sans",
    # titres de rubrique
    r"^#*\s*mes atouts",
    r"^#*\s*mon parcours en bref",
    r"^#*\s*ce que je peux vous apporter",
]

ADVERBES = [
    "précisément", "réellement", "concrètement", "pleinement", "proprement",
    "parfaitement", "véritablement", "notamment", "particulièrement",
    "efficacement", "durablement", "naturellement",
]
ADVERBES_MAX = 2

INFLATION = [
    "scalable", "scalables", "haute performance", "faible latence", "avancé",
    "avancée", "avancées", "complet", "complète", "robuste", "robustesse",
    "optimisé", "optimisée", "entièrement", "performant", "performante",
    "innovant", "innovante", "moderne", "sur-mesure", "de pointe",
]

NOMINAUX = [
    "Conception", "Architecture", "Intégration", "Développement", "Mise",
    "Réalisation", "Création", "Gestion", "Optimisation", "Déploiement",
    "Maintenance", "Refonte", "Automatisation", "Amélioration", "Collaboration",
    "Participation", "Rédaction", "Analyse", "Système", "Recherche",
    "Migration", "Implémentation", "Supervision", "Coordination",
]

CHIFFRES_MIN = 3
CHIFFRES_MAX = 8


def lignes_utiles(texte):
    """Renvoie (numero, contenu) en ignorant le YAML frontmatter, les blocs de code
    et les commentaires HTML (consignes d'edition, jamais rendues)."""
    out, dans_yaml, dans_code, dans_comm = [], False, False, False
    debut = True
    for i, ligne in enumerate(texte.splitlines(), 1):
        s = ligne.strip()
        if dans_comm:
            dans_comm = "-->" not in s
            continue
        if s.startswith("<!--"):
            dans_comm = "-->" not in s
            continue
        if debut and s == "---":
            debut = False
            dans_yaml = True
            continue
        if s:
            debut = False
        if dans_yaml:
            if s == "---":
                dans_yaml = False
            continue
        if s.startswith("```"):
            dans_code = not dans_code
            continue
        if dans_code:
            continue
        out.append((i, ligne))
    return out


def est_ligne_de_liste_technique(ligne):
    """Ligne ou le point median est une convention de mise en page, pas de la prose.

    Couvre la syntaxe de references/cv-markdown.md: titres de section et lignes
    d'employeur (###), lignes de stack (> Stack : ...), lignes de competence
    (**Backend** : ...), et toute enumeration d'au moins deux termes separes.
    """
    nu = ligne.lstrip()
    s = nu.lstrip("*_->#+ ")
    return bool(re.match(r"(?i)^(stack|langues?|contact|comp[ée]tences)\s*:", s)) \
        or nu.startswith(("#", ">")) \
        or re.match(r"^\*\*[^*]+\*\*\s*:", ligne.strip()) is not None \
        or ligne.count("\u00b7") >= 2


def paragraphes(lignes):
    blocs, courant = [], []
    for _, ligne in lignes:
        if ligne.strip():
            courant.append(ligne.strip())
        elif courant:
            blocs.append(" ".join(courant))
            courant = []
    if courant:
        blocs.append(" ".join(courant))
    return [b for b in blocs if len(b.split()) > 25]


def analyser(chemin):
    texte = Path(chemin).read_text(encoding="utf-8")
    lignes = lignes_utiles(texte)
    plat = " ".join(l for _, l in lignes)
    bas = plat.lower()

    bloquants, avertissements, infos = [], [], []

    # 1. ponctuation interdite (comparaison sur caracteres, pas sur octets)
    for car, nom in PONCTUATION.items():
        hits = [n for n, l in lignes if car in l]
        if hits:
            bloquants.append(
                f"{nom} x{sum(l.count(car) for _, l in lignes)} "
                f"lignes {', '.join(map(str, hits[:8]))}"
            )

    # 2. point median en pleine phrase
    hits = [n for n, l in lignes if "\u00b7" in l and not est_ligne_de_liste_technique(l)]
    if hits:
        avertissements.append(f"point median en prose lignes {', '.join(map(str, hits))}")

    # 3. lexique interdit
    vus = set()
    for motif in LEXIQUE:
        for n, l in lignes:
            m = re.search(motif, l.lower())
            if m:
                extrait = l[max(0, m.start() - 15):m.end() + 25].strip()
                cle = (n, m.start())
                if cle not in vus:
                    vus.add(cle)
                    bloquants.append(f"lexique ligne {n}: ...{extrait}...")
                break

    # 4. adverbes en -ment d'emphase
    trouves = [(a, bas.count(a)) for a in ADVERBES if a in bas]
    total_adv = sum(c for _, c in trouves)
    if total_adv > ADVERBES_MAX:
        detail = ", ".join(f"{a} x{c}" for a, c in trouves)
        avertissements.append(f"adverbes -ment: {total_adv} (max {ADVERBES_MAX}) - {detail}")

    # 5. adjectifs d'inflation sans chiffre a proximite
    for mot in INFLATION:
        for n, l in lignes:
            if mot in l.lower() and not re.search(r"\d", l):
                avertissements.append(f"adjectif non quantifie ligne {n}: {mot}")
                break

    # 6. enumerations ternaires
    ternaires = re.findall(
        r"\b[\wéèêàçîô-]+,\s+[\wéèêàçîô-]+\s+(?:et|ou)\s+[\wéèêàçîô-]+\b", plat
    )
    if len(ternaires) > 1:
        avertissements.append(
            f"enumerations ternaires: {len(ternaires)} (max 1) - "
            + " | ".join(t[:40] for t in ternaires[:4])
        )

    # 7. gloses d'acronyme
    gloses = []
    for n, l in lignes:
        for m in re.finditer(r"\b([A-Z]{2,6})\s*\(([^)]{4,60})\)", l):
            if not m.group(2).isupper():
                gloses.append(f"ligne {n}: {m.group(1)} ({m.group(2)[:40]})")
    if gloses:
        infos.append(
            "gloses a confronter au tableau de anti-ia.md: " + " | ".join(gloses)
        )

    # 8. puces au style nominal
    puces = [(n, l.strip()) for n, l in lignes if re.match(r"^\s*[-*+\u2013]\s+\S", l)]
    if puces:
        nominales = [
            n for n, l in puces
            if re.sub(r"^[-*+\u2013]\s+", "", l).split(" ")[0].strip(",:") in NOMINAUX
        ]
        part = len(nominales) / len(puces)
        if part > 0.66:
            avertissements.append(
                f"style nominal: {len(nominales)}/{len(puces)} puces "
                f"({part:.0%}, cible < 66%) lignes {', '.join(map(str, nominales[:8]))}"
            )

    # 9. densite de chiffres
    nombres = re.findall(r"(?<![\w/])\d+(?:[.,]\d+)?\s*(?:%|s\b|ms\b|min\b|k\b|Go\b|Mo\b)?", plat)
    hors_dates = [x for x in nombres if not re.fullmatch(r"(19|20)\d{2}", x.strip())]
    if len(hors_dates) < CHIFFRES_MIN:
        avertissements.append(
            f"metriques: {len(hors_dates)} chiffre(s) hors dates (cible {CHIFFRES_MIN}-{CHIFFRES_MAX})"
        )
    elif len(hors_dates) > CHIFFRES_MAX:
        infos.append(f"metriques: {len(hors_dates)} chiffres, verifier qu'aucun n'est invente")

    # 10. isometrie des paragraphes (lettres surtout)
    blocs = paragraphes(lignes)
    if len(blocs) >= 3:
        tailles = [len(b.split()) for b in blocs]
        moy = sum(tailles) / len(tailles)
        if all(abs(t - moy) / moy < 0.20 for t in tailles):
            avertissements.append(
                f"paragraphes isometriques: {tailles} mots, tous a moins de 20% de la moyenne"
            )

    return bloquants, avertissements, infos, plat


def doublons(textes):
    """Phrases identiques entre deux documents (CV et lettre)."""
    def phrases(t):
        return {
            p.strip().lower()
            for p in re.split(r"[.!?\n]", t)
            if len(p.split()) >= 6
        }
    noms = list(textes)
    res = []
    for i in range(len(noms)):
        for j in range(i + 1, len(noms)):
            for p in phrases(textes[noms[i]]) & phrases(textes[noms[j]]):
                res.append(f"{Path(noms[i]).name} / {Path(noms[j]).name}: {p[:70]}")
    return res


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    total_bloquants = 0
    textes = {}

    for chemin in sys.argv[1:]:
        if not Path(chemin).exists():
            print(f"introuvable: {chemin}")
            return 2
        bloq, avert, info, plat = analyser(chemin)
        textes[chemin] = plat
        total_bloquants += len(bloq)

        print(f"\n=== {chemin} ===")
        for titre, items in (("BLOQUANT", bloq), ("A CORRIGER", avert), ("A VERIFIER", info)):
            for it in items:
                print(f"  [{titre}] {it}")
        if not (bloq or avert or info):
            print("  rien a signaler")

    if len(textes) > 1:
        d = doublons(textes)
        if d:
            print("\n=== doublons entre documents ===")
            for x in d:
                print(f"  [A CORRIGER] {x}")

    print(f"\n{total_bloquants} signal(aux) bloquant(s).")
    return 1 if total_bloquants else 0


if __name__ == "__main__":
    sys.exit(main())
