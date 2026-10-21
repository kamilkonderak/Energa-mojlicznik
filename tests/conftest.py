"""Shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE = Path(__file__).parent / "licznik_g12w.html"


@pytest.fixture
def meter_html() -> str:
    """Sanitised meter page (G12W, 4 registers)."""
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def meter_data(meter_html):
    """Parsed meter page."""
    from custom_components.energa_mojlicznik.parser import parse_meter_page

    return parse_meter_page(meter_html)
