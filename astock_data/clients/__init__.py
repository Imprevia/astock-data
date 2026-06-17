"""Market data vendor clients.

Each client wraps a single upstream data source (mootdx / Tencent / Eastmoney /
Sina / etc.) and exposes plain ``dict`` / ``list[dict]`` results so the service
layer can map them into Pydantic models later. Clients must accept an injected
``client=`` object for testability and must never open live connections during
unit tests.
"""

from __future__ import annotations

__all__: list[str] = []
