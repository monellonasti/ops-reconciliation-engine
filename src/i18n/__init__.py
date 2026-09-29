"""Text shown to operators, in the language configured in the rules file.

Every user-facing string (finding messages, explanations, notes, UI labels)
comes from a catalog keyed by a stable identifier. English is the reference
catalog; a key missing from another language falls back to English, so a
partial translation degrades gracefully instead of failing.

The active language is set once per run or per UI render (``set_language``).
It is context-local, not global: Streamlit serves every browser session from
its own thread, and one session switching language must not change the text
another session is producing at the same moment. Rule identifiers, column
names and CSV headers are never translated: they are data, not prose.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import ContextVar

from src.i18n import en, it

LANGUAGES: dict[str, Mapping[str, str | Sequence[str]]] = {"en": en.MESSAGES, "it": it.MESSAGES}
DEFAULT_LANGUAGE = "en"

_current: ContextVar[str] = ContextVar("ops_recon_language", default=DEFAULT_LANGUAGE)


def available_languages() -> list[str]:
    return list(LANGUAGES)


def set_language(code: str) -> str:
    """Select the catalog for subsequent ``t`` calls. Returns the previous language."""
    if code not in LANGUAGES:
        raise ValueError(f"Unsupported language '{code}'; available: {', '.join(LANGUAGES)}")
    previous = _current.get()
    _current.set(code)
    return previous


def get_language() -> str:
    return _current.get()


def t(message_key: str, /, **values: object) -> str:
    """The text for ``message_key`` in the active language, with ``values`` substituted.

    The key is positional-only so that placeholders may be called ``key`` too.
    """
    template = _lookup(message_key)
    if not isinstance(template, str):
        raise TypeError(f"Catalog key '{message_key}' is a list; use t_list()")
    return template.format(**values) if values else template


def t_list(message_key: str, /) -> list[str]:
    """A list-valued catalog entry (for example suggested checks)."""
    entry = _lookup(message_key)
    if isinstance(entry, str):
        return [entry]
    return list(entry)


def _lookup(message_key: str) -> str | Sequence[str]:
    catalog = LANGUAGES[_current.get()]
    if message_key in catalog:
        return catalog[message_key]
    try:
        return LANGUAGES[DEFAULT_LANGUAGE][message_key]
    except KeyError as exc:
        raise KeyError(f"Unknown text key '{message_key}'") from exc
