"""Data-access helpers. Every query is parameterised; no SQL is built from user input."""
import re
from datetime import datetime, timezone

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value):
    """Strip control characters and surrounding whitespace. None becomes ''."""
    if value is None:
        return ""
    return _CONTROL_CHARS.sub("", str(value)).strip()


def like_pattern(term):
    """Escape LIKE wildcards so user text is matched literally (use with ESCAPE '\\')."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def parse_page(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def page_meta(total, page, per_page):
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    return {"total": total, "page": page, "pages": pages, "per_page": per_page,
            "offset": (page - 1) * per_page}
