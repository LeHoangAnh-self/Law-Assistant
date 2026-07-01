from collections.abc import Mapping
from typing import Any

ALLOWED_FILTER_KEYS = frozenset(
    {
        "document_id",
        "document_number",
        "document_type",
        "validity_status",
        "scope",
        "issuing_authority",
        "external_docid",
        "external_source",
        "source",
        "issued_date",
        "effective_date",
        "expired_date",
    }
)


def unsupported_filter_keys(filters: Mapping[str, Any]) -> list[str]:
    return sorted(key for key in filters if key not in ALLOWED_FILTER_KEYS)


def validate_filter_keys(filters: Mapping[str, Any]) -> dict[str, Any]:
    unsupported = unsupported_filter_keys(filters)
    if unsupported:
        allowed = ", ".join(sorted(ALLOWED_FILTER_KEYS))
        rejected = ", ".join(unsupported)
        msg = f"Unsupported filter(s): {rejected}. Allowed filters: {allowed}."
        raise ValueError(msg)
    return dict(filters)
