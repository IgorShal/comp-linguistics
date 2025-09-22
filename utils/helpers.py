import re
from typing import Dict, Any

from utils.repository_error import RepositoryError

_LABEL_RE = re.compile(r'^[A-Za-z0-9_]+$')  # safe label chars


def _safe_label(label: str) -> str:
    if not _LABEL_RE.match(label):
        raise RepositoryError(f"Invalid label '{label}' - allowed: A-Z a-z 0-9 _")
    return f"`{label}`"


def _safe_property_key(key: str) -> str:
    if not isinstance(key, str) or key == "":
        raise RepositoryError("Property key must be non-empty string")
    return f"`{key}`"


TNode = Dict[str, Any]
TArc = Dict[str, Any]
