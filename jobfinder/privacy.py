"""Minimise what leaves the machine when the optional Claude path is used.

The local-first promise has exactly one egress: with an ``ANTHROPIC_API_KEY`` set, the
Claude draft/tailor path sends the candidate's CV text (and any style examples) plus the
job description to Anthropic. :func:`redact_pii` masks the obvious contact details — email,
phone, postal-ish numbers and URLs — *before* that send, so a cover letter can still be
written (the name is kept, since it signs the letter) while the raw contact info doesn't
leave. It is deliberately conservative: it must not eat dates ("2018-2021"), amounts
("1,200,000 DKK") or metrics ("40%").
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
# Scheme-less profile/portfolio links are the common CV form and highly identifying.
# Known social hosts (with or without a path)…
_PROFILE_HOST = re.compile(
    r"\b(?:linkedin|github|gitlab|bitbucket|behance|dribbble|medium|stackoverflow|"
    r"kaggle|codepen|polywork|gumroad)\.[a-z]{2,}(?:/\S*)?",
    re.I,
)
# …and any bare domain that carries a /path (a link, not a tech term — "socket.io",
# "ASP.NET" and "Node.js" have no path, so they survive).
_URL_WITH_PATH = re.compile(r"\b[\w-]+(?:\.[\w-]+)+/\S+")
# Phone-ish: international +NN; 8+ contiguous digits; 4+4 split by space/dot (NOT hyphen,
# so "2018-2021" survives); or 3+ groups of exactly two digits. Group sizes are kept tight
# so space-thousands amounts ("25 000 000", "1 200 000") and "1,200,000" are left alone.
_PHONE = re.compile(
    r"(?<!\w)(?:"
    r"\+\d[\d\s().-]{6,}\d"
    r"|\d{8,}"
    r"|\d{4}[\s.]\d{4}"
    r"|\d{2}(?:[\s.\-]\d{2}){2,}"
    r")(?!\w)"
)


def redact_pii(text: str) -> str:
    """Mask email addresses, links and phone-like numbers; leave names/everything else intact."""
    if not text:
        return text
    text = _EMAIL.sub("[email redacted]", text)
    text = _URL.sub("[link redacted]", text)
    text = _PROFILE_HOST.sub("[link redacted]", text)
    text = _URL_WITH_PATH.sub("[link redacted]", text)
    text = _PHONE.sub("[contact redacted]", text)
    return text
