"""Contrat commun à toutes les sources : modèle Job, contexte de collecte, helpers.

Chaque module de `sources/` expose :

    NAME = "wttj"                 # identifiant court, stable (sert de préfixe d'uid)
    LABEL = "Welcome to the Jungle"
    KIND = "api" | "scrape"       # "scrape" est ignoré si config["scrape"] est faux
    REQUIRES = ["ENV_VAR", ...]   # variables d'env nécessaires, source sautée sinon
    MIN_INTERVAL_H = 0            # délai minimal entre deux collectes (quotas, CGU)
    def fetch(ctx: Context) -> Iterable[Job]: ...

Une source ne filtre pas la zone ni le remote : elle ramène large et renseigne
honnêtement les champs qu'elle connaît. Le tri se fait après, au même endroit
pour toutes, dans `filters.py` et `score.py`.

Tout ce qui dépend de l'utilisateur (lieux de recherche, requêtes, pré-filtre métier)
se lit dans la config via `Context` : aucun lieu ni métier n'est codé en dur ici.
"""
from __future__ import annotations

import html
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from config import (DATA_DIR, ENV_FILE, SKILL_DIR, config_gaps, load_config,  # noqa: F401  (réexportés)
                    search_areas)

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Valeurs autorisées, pour que zone.py et score.py n'aient qu'un vocabulaire à connaître.
REMOTE = ("full", "partial", "none", "unknown")
CONTRACT = ("cdi", "freelance", "cdd", "interim", "stage", "alternance", "unknown")


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    url: str
    description: str = ""          # texte brut, sans HTML
    location: str = ""             # libellé tel que fourni par la source
    lat: float | None = None
    lon: float | None = None
    country: str = ""              # ISO2 si connu ("FR")
    remote: str = "unknown"        # valeur de REMOTE, uniquement si la source le dit
    remote_scope: str = ""         # restriction géographique du remote, texte brut ("France", "Europe", "Worldwide")
    contract: str = "unknown"      # valeur de CONTRACT
    salary_min: float | None = None
    salary_max: float | None = None
    salary_period: str = ""        # "year" | "month" | "day" | "hour" | ""
    salary_currency: str = ""      # ISO 4217 ("EUR", "USD") ; vide = euros supposés
    published_at: str = ""         # ISO 8601
    tags: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["uid"] = self.uid
        return d


@dataclass
class Context:
    config: dict[str, Any]
    env: dict[str, str]
    http: requests.Session
    log: Callable[[str], None]

    @property
    def queries_fr(self) -> list[str]:
        q = self.config.get("queries") or {}
        return q.get("fr") or q.get("en") or []

    @property
    def queries_en(self) -> list[str]:
        """Requêtes pour les plateformes internationales ; à défaut, les requêtes FR."""
        q = self.config.get("queries") or {}
        return q.get("en") or q.get("fr") or []

    def queries_for(self, source: str, default: str = "fr") -> list[str]:
        """Requêtes propres à une source si la config en définit (ex. mots courts pour Free-Work,
        dont la recherche fait un ET entre les mots), sinon la liste fr ou en."""
        own = (self.config.get("queries") or {}).get(source)
        return own or (self.queries_fr if default == "fr" else self.queries_en)

    @property
    def areas(self) -> list[dict[str, Any]]:
        """Lieux où chercher les offres sur site ou hybrides : [{name, city, lat, lon, radius_km,
        postcode, insee, department, region}] (voir config.search_areas)."""
        return search_areas(self.config)

    @property
    def remote_wanted(self) -> bool:
        return bool((self.config.get("remote") or {}).get("accepted", True))

    @property
    def place_names(self) -> list[str]:
        """Noms des lieux de l'utilisateur (domicile, zone, lieux de recherche), pour les sources
        qui ne savent filtrer que par texte (HN, pages carrières)."""
        names = [(self.config.get("home") or {}).get("city", "")]
        names += [a.get("city") or a.get("name") or "" for a in self.areas]
        names += [z.get("city") or z.get("name") or "" for z in (self.config.get("onsite") or {}).get("zone", [])]
        out: list[str] = []
        for n in names:
            n = re.split(r"[(/,]", n or "")[0].strip()
            if len(n) >= 3 and n.lower() not in (x.lower() for x in out):
                out.append(n)
        return out

    @property
    def prefilter(self):
        """Pré-filtre métier partagé par les sources qui ramènent tout un flux (remote boards, ATS, HN)."""
        if not hasattr(self, "_prefilter"):
            from prefilter import Prefilter
            self._prefilter = Prefilter(self.config)
        return self._prefilter

    @property
    def max_age_days(self) -> int:
        return int(self.config.get("max_age_days", 30))

    @property
    def per_query(self) -> int:
        """Plafond d'offres par requête, pour rester à faible volume."""
        return int(self.config.get("per_query", 50))


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    declared: set[str] = set()
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            declared.add(k)
            if v:
                env[k] = v
    # une variable déclarée dans le fichier peut être surchargée depuis le shell
    env.update({k: os.environ[k] for k in declared if os.environ.get(k)})
    return env


class _TimeoutSession(requests.Session):
    """Session avec timeout par défaut : une source qui pend ne doit pas bloquer toute la collecte."""

    def request(self, method, url, **kwargs):  # type: ignore[override]
        kwargs.setdefault("timeout", 30)
        return super().request(method, url, **kwargs)


def make_session() -> requests.Session:
    s = _TimeoutSession()
    s.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    # retries sur GET seulement : un POST peut coûter du quota (Jooble : 500 requêtes à vie)
    adapter = requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
        total=2, backoff_factor=1.5, status_forcelist=(429, 502, 503, 504),
        allowed_methods=("GET",)))
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h\d|tr)[^>]*>", re.I)
_WS = re.compile(r"[ \t ]+")


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = _BLOCK.sub("\n", value)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def iso_date(value: Any) -> str:
    """Accepte un epoch (s ou ms), une date ISO ou une chaîne RFC 2822 ; renvoie ISO UTC ou ""."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ts = float(value)
            if ts > 1e12:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        s = str(value).strip()
        # Python 3.10 n'accepte que 3 ou 6 décimales de secondes : on ramène tout à 6
        s = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d+)", lambda m: f"{m.group(1)}.{m.group(2)[:6].ljust(6, '0')}", s)
        s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)  # « +0000 » → « +00:00 »
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return ""


def age_days(iso: str) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def polite_sleep(seconds: float = 1.0) -> None:
    time.sleep(seconds)
