"""Unified ticker resolver — the single safety boundary every public service
routes user-provided tickers through.

This module never imports mootdx (or any data vendor) at module top level. The
mootdx-backed name map is built lazily ONLY on the ``name_map=None`` branch, so
unit tests that inject a fake ``name_map`` stay fully offline.

Public symbols:
    - :func:`normalize_ticker`: pure/string code normalizer + validator.
    - :func:`resolve_ticker`: accepts raw user input (6-digit code, prefixed/
      suffixed code, or Chinese stock name) and returns a :class:`Ticker`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from astock_data.errors import (
    AmbiguousTickerError,
    InvalidTickerError,
    TickerResolutionError,
)
from astock_data.models.base import Ticker

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from collections.abc import Mapping, Sequence

# 6-digit A-share ticker: SH (6/9), BJ (8), SZ (0/3).
_CODE_RE = re.compile(r"^[0368]\d{5}$")

# Recognized exchange decorations to strip before validation.
_SUFFIXES = (".SH", ".SZ", ".BJ")
_PREFIXES = ("SH", "SZ", "BJ")

# CJK detection — covers CJK Unified + extensions + compat ideographs + radicals
# plus full-width forms. Anything matching means the input is a Chinese name.
_CJK_RE = re.compile(
    r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u2F00-\u2FDF\u3000-\u303F"
    r"\uFF00-\uFFEF]"
)


def _market_for_code(code: str) -> str:
    """Derive the exchange from the first digit: 6/9→sh, 8→bj, else→sz."""
    head = code[0]
    if head in ("6", "9"):
        return "sh"
    if head == "8":
        return "bj"
    return "sz"


def normalize_ticker(value: str) -> str:
    """Normalize a raw ticker-like string to a canonical 6-digit code.

    The output is the bare 6-digit code (a ``str``) so it compares equal to a
    plain code literal — this is the canonical form all services serialize and
    cache. Strips whitespace, uppercases, removes ``.SH``/``.SZ``/``.BJ``
    suffixes and ``SH``/``SZ``/``BJ`` prefixes, then validates against
    ``^[0368]\\d{5}$`` (SH/BJ/SZ including Beijing Exchange ``8xxxxx``).

    Raises:
        InvalidTickerError: for empty input, path-like input, or any value that
            does not reduce to a conforming 6-digit A-share code.
    """
    if not isinstance(value, str):
        raise InvalidTickerError(
            f"ticker must be a string, got {type(value).__name__}"
        )

    cleaned = value.strip().upper()

    # Reject path-traversal / separator-bearing input outright.
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise InvalidTickerError(f"invalid ticker: {value!r}")

    # Strip a trailing exchange suffix first (e.g. 688017.SH).
    for suf in _SUFFIXES:
        if cleaned.endswith(suf):
            cleaned = cleaned[: -len(suf)]
            break

    # Strip a leading exchange prefix (e.g. SH688017, sz000001, BJ835185).
    for pre in _PREFIXES:
        if cleaned.startswith(pre):
            cleaned = cleaned[len(pre):]
            break

    cleaned = cleaned.strip().upper()

    if not _CODE_RE.fullmatch(cleaned):
        raise InvalidTickerError(f"invalid ticker: {value!r}")

    return cleaned


def _resolve_code_to_ticker(code: str) -> Ticker:
    """Build a :class:`Ticker` from a validated code (market derived)."""
    return Ticker(code=code, market=_market_for_code(code))


def resolve_ticker(
    user_input: str,
    *,
    name_map: "Mapping[str, Sequence[Ticker]] | None" = None,
) -> Ticker:
    """Resolve arbitrary user input to a :class:`Ticker`.

    Behavior:
        * Non-CJK input (a code, with or without exchange decorations) is
          passed through :func:`normalize_ticker` and returned as a
          :class:`Ticker` with the market derived from the code's first digit.
        * CJK input is treated as a Chinese stock name and resolved via the
          injected ``name_map``. If ``name_map`` is ``None`` the name map is
          built lazily from ``TdxClient().build_name_map()`` (mootdx is
          imported only inside this branch). Exact name match wins; otherwise a
          unique substring match resolves; multiple substring matches raise
          :class:`AmbiguousTickerError`; no match raises
          :class:`TickerResolutionError`.

    Args:
        user_input: raw user/LLM input — a code form or a Chinese stock name.
        name_map: ``{chinese_name: [Ticker, ...]}``. Tests inject fakes so they
            never touch mootdx. ``None`` triggers a lazy live build.

    Raises:
        InvalidTickerError: malformed/path-like/empty code input, or an
            unknown Chinese name (a name that cannot be normalized as a code
            either).
        AmbiguousTickerError: a Chinese substring matches multiple candidates.
        TickerResolutionError: a name lookup fails for any other reason.
    """
    if not isinstance(user_input, str):
        raise InvalidTickerError(
            f"ticker must be a string, got {type(user_input).__name__}"
        )

    cleaned = user_input.strip()
    if not cleaned:
        raise InvalidTickerError("empty ticker input")

    has_cjk = bool(_CJK_RE.search(cleaned))

    # Path-traversal guard applies to all inputs.
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise InvalidTickerError(f"invalid ticker: {user_input!r}")

    if not has_cjk:
        # Pure code (possibly decorated) — normalize + derive market.
        return _resolve_code_to_ticker(normalize_ticker(cleaned))

    # --- Chinese name resolution path --------------------------------------
    if name_map is None:
        name_map = _build_name_map_from_tdx()

    # Exact name match first.
    if cleaned in name_map:
        candidates = list(name_map[cleaned])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise AmbiguousTickerError(
                f"name {cleaned!r} matches multiple tickers: "
                f"{[t.code for t in candidates]}"
            )

    # Substring match across all keys.
    substring_hits: list[Ticker] = []
    seen_codes: set[str] = set()
    for name, tickers in name_map.items():
        if cleaned in name:
            for t in tickers:
                if t.code not in seen_codes:
                    seen_codes.add(t.code)
                    substring_hits.append(t)

    if len(substring_hits) == 1:
        return substring_hits[0]
    if len(substring_hits) > 1:
        raise AmbiguousTickerError(
            f"substring {cleaned!r} is ambiguous: "
            f"{[t.code for t in substring_hits]}"
        )

    # No match at all. If the cleaned text also cannot be normalized to a code
    # (e.g. pure Chinese with no code form), it's an invalid ticker; otherwise
    # a resolution failure.
    try:
        normalize_ticker(cleaned)
    except InvalidTickerError:
        raise InvalidTickerError(f"unknown Chinese stock name: {cleaned!r}")
    raise TickerResolutionError(f"could not resolve ticker: {cleaned!r}")


def _build_name_map_from_tdx() -> "dict[str, list[Ticker]]":
    """Lazily build a ``{name: [Ticker]}`` map from :class:`TdxClient`.

    mootdx is imported here and ONLY here, so injected-map callers never pay the
    import cost or touch the network.
    """
    from astock_data.clients.tdx import TdxClient  # lazy: keeps module import clean

    name_to_code, _code_to_name = TdxClient().build_name_map()
    resolved: dict[str, list[Ticker]] = {}
    for name, code in name_to_code.items():
        try:
            ticker = Ticker(code=code, market=_market_for_code(code), name=name)
        except Exception:  # noqa: BLE001 - skip codes that fail Ticker validation
            continue
        resolved.setdefault(name, []).append(ticker)
    return resolved


__all__ = ["normalize_ticker", "resolve_ticker"]
