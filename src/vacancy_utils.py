from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata
from urllib.parse import urlparse


def normalise_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalise_domain(value: str | None) -> str:
    if not value:
        return ""
    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)
    domain = (parsed.netloc or parsed.path).lower().split(":")[0]
    return domain.removeprefix("www.").rstrip("/")


def stable_hash(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return sha256(value.encode("utf-8")).hexdigest()


def canonical_job_key(*, company_domain: str | None, company_name: str, title: str, location: str | None) -> str:
    domain_or_name = normalise_domain(company_domain) or normalise_text(company_name)
    parts = [domain_or_name, normalise_text(title), normalise_text(location)]
    return stable_hash("|".join(parts))[:24]
