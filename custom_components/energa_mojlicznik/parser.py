"""Parse the Energa "Mój licznik" meter page.

Pure functions with no Home Assistant imports, so the tests and the legacy
energa2mqtt.py script can use them too. Everything depends on the page's HTML
structure; if Energa changes it, this is the only file to update.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from bs4 import BeautifulSoup

# Footer version the parser was last checked against.
KNOWN_WEB_VERSION = "2.5.5.eb1dde25"

_HEADER_RE = re.compile(r"A\s*([+-])(?:\s*strefa\s*(\d+))?", re.IGNORECASE)


class ParseError(Exception):
    """The page does not have the expected structure."""


@dataclass(frozen=True)
class Register:
    """One meter register, e.g. consumption in zone 1."""

    key: str  # pobor, pobor_strefa_1, oddanie_strefa_2, ...
    direction: str  # "+" consumption (A+), "-" production / export (A-)
    zone: int | None  # None for single-zone tariffs (G11)
    zone_name: str | None  # page tooltip: "dzienna", "nocna", ...
    value: float  # kWh
    read_at: datetime  # naive local time of the reading
    label: str  # as shown on the page, e.g. "A+ strefa 1"


@dataclass(frozen=True)
class MeterData:
    """Everything read from one meter page."""

    registers: dict[str, Register]
    supplier: dict[str, str]
    web_version: str | None


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def is_login_page(html: str) -> bool:
    """True when the page is the login form (not logged in / bad credentials)."""
    return _soup(html).find("form", id="loginForm") is not None


def parse_antixsrf(html: str) -> str:
    """Return the anti-XSRF token from the login form."""
    form = _soup(html).find("form", id="loginForm")
    if form is None:
        raise ParseError("Login form not found; the site may be in maintenance mode")
    tag = form.find("input", {"name": "_antixsrf"})
    if tag is None or not tag.has_attr("value"):
        raise ParseError("'_antixsrf' field not found in the login form")
    return str(tag["value"])


def parse_web_version(html: str) -> str | None:
    """Return the application version printed in the page footer."""
    footer = _soup(html).find("div", class_="footer", id="footer")
    div = footer.find("div") if footer is not None else None
    parts = div.text.split() if div is not None else []
    return parts[1].strip() if len(parts) > 1 else None


def _register_key(direction: str, zone: int | None) -> str:
    base = "pobor" if direction == "+" else "oddanie"
    return f"{base}_strefa_{zone}" if zone is not None else base


def parse_registers(html: str) -> dict[str, Register]:
    """Return the meter registers keyed by Register.key."""
    soup = _soup(html)
    result: dict[str, Register] = {}
    for first in soup.find_all("td", class_="first"):
        texts = [t.strip() for t in first.stripped_strings]
        if len(texts) < 2:
            continue
        match = _HEADER_RE.search(texts[0])
        if match is None:
            continue
        last = first.find_next_sibling("td", class_="last")
        if last is None:
            raise ParseError(f"No value cell for register '{texts[0]}'")
        digits = "".join(ch for ch in last.get_text() if ch in "0123456789.,").replace(",", ".")
        try:
            value = float(digits)
            read_at = datetime.strptime(texts[1], "%Y-%m-%d %H:%M")
        except ValueError as err:
            raise ParseError(f"Cannot parse register '{texts[0]}': {err}") from err
        direction = match.group(1)
        zone = int(match.group(2)) if match.group(2) else None
        row = first.find_parent("tr")
        zone_name = row.get("title") if row is not None else None
        key = _register_key(direction, zone)
        result[key] = Register(
            key=key,
            direction=direction,
            zone=zone,
            zone_name=str(zone_name) if zone_name else None,
            value=value,
            read_at=read_at,
            label=texts[0],
        )
    return result


def parse_supplier(html: str) -> dict[str, str]:
    """Return supplier details: supplier, contract_period_from, ppe, tariff, customer_type, ppe_address."""
    details: list[str] = []
    for block in _soup(html).find_all("div", class_="detailsInfo"):
        text = block.text.strip().replace("\n", "").replace("\xa0", " ")
        details.extend(item for item in re.sub(r" {2,}", ";", text).split(";") if item)

    result: dict[str, str] = {}
    for i, item in enumerate(details):
        nxt = details[i + 1] if i + 1 < len(details) else ""
        if "Sprzedawca " in item:
            result["supplier"] = item.replace("Sprzedawca ", "").strip()
        elif "Okres umowy" in item:
            result["contract_period_from"] = nxt.replace("Od ", "").strip()
        elif "Numer PPE " in item:
            result["ppe"] = item.replace("Numer PPE ", "").strip()
        elif "Taryfa" in item:
            result["tariff"] = nxt.strip()
        elif "Typ " in item:
            result["customer_type"] = item.replace("Typ ", "").strip()
        elif "Adres PPE " in item:
            result["ppe_address"] = item.replace("Adres PPE ", "").strip()
    return result


def parse_meter_page(html: str) -> MeterData:
    """Parse the whole meter page. Raises ParseError when no register is found."""
    if is_login_page(html):
        raise ParseError("Got the login page instead of the meter page")
    registers = parse_registers(html)
    if not registers:
        raise ParseError("No meter registers found on the page")
    return MeterData(registers=registers, supplier=parse_supplier(html), web_version=parse_web_version(html))
