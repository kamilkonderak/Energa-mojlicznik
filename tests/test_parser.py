"""Parser tests (no Home Assistant needed)."""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.energa_mojlicznik.parser import (
    KNOWN_WEB_VERSION,
    ParseError,
    is_login_page,
    parse_antixsrf,
    parse_meter_page,
    parse_registers,
)

SINGLE_ZONE = """<table><tr title="całodobowa">
<td class="first"><div>A+</div><div>2026-10-21 00:00</div></td>
<td class="last"><span>1</span><span>2</span><span>3</span><span class="koma">,</span><span>4</span></td>
</tr></table>"""


def test_registers(meter_data):
    regs = meter_data.registers
    assert set(regs) == {"pobor_strefa_1", "pobor_strefa_2", "oddanie_strefa_1", "oddanie_strefa_2"}
    z1 = regs["pobor_strefa_1"]
    assert z1.value == pytest.approx(43753.514)
    assert z1.direction == "+" and z1.zone == 1
    assert z1.zone_name == "dzienna"
    assert z1.read_at == datetime(2026, 5, 18, 0, 0)
    assert regs["pobor_strefa_2"].zone_name == "nocna"
    assert regs["oddanie_strefa_1"].direction == "-"


def test_supplier_and_version(meter_data):
    assert meter_data.supplier["tariff"] == "G12W"
    assert meter_data.supplier["supplier"] == "ENERGA-Obrót SA"
    assert meter_data.supplier["ppe"] == "000000000000000000"
    assert meter_data.supplier["contract_period_from"] == "2026-05-12"
    assert meter_data.web_version == KNOWN_WEB_VERSION


def test_not_login_page(meter_html):
    assert not is_login_page(meter_html)


def test_login_page_detected():
    html = '<form id="loginForm"><input name="_antixsrf" value="tok123"></form>'
    assert is_login_page(html)
    assert parse_antixsrf(html) == "tok123"
    with pytest.raises(ParseError):
        parse_meter_page(html)


def test_missing_antixsrf():
    with pytest.raises(ParseError):
        parse_antixsrf("<html>przerwa techniczna</html>")


def test_single_zone_tariff():
    regs = parse_registers(SINGLE_ZONE)
    assert set(regs) == {"pobor"}
    assert regs["pobor"].value == pytest.approx(123.4)
    assert regs["pobor"].zone is None


def test_empty_page_raises():
    with pytest.raises(ParseError):
        parse_meter_page("<html><body>nic</body></html>")
