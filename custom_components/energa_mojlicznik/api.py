"""Async client for mojlicznik.energa-operator.pl."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import aiohttp

from .parser import MeterData, ParseError, is_login_page, parse_antixsrf, parse_meter_page

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mojlicznik.energa-operator.pl/dp"
LOGIN_URL = f"{BASE_URL}/UserLogin.do"
DATA_URL = f"{BASE_URL}/UserData.do"
LOGOUT_URL = f"{BASE_URL}/MainLogout.go"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"}
TIMEOUT = aiohttp.ClientTimeout(total=60)

T = TypeVar("T")


class EnergaError(Exception):
    """Base error."""


class EnergaAuthError(EnergaError):
    """Wrong username or password."""


class EnergaConnectionError(EnergaError):
    """The site could not be reached or returned an HTTP error."""


class EnergaParseError(EnergaError):
    """The site answered but the page could not be understood."""


# Runs blocking HTML parsing outside the event loop (hass.async_add_executor_job).
Executor = Callable[..., Awaitable[Any]]


class EnergaClient:
    """Logs in, downloads the meter page and logs out again.

    The session must have its own cookie jar; it is cleared before every login.
    The password is never logged.
    """

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str, executor: Executor) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._executor = executor

    async def _get(self, url: str) -> str:
        async with self._session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                raise EnergaConnectionError(f"GET {url} returned HTTP {resp.status}")
            return await resp.text()

    async def _parse(self, func: Callable[[str], T], html: str) -> T:
        try:
            return await self._executor(func, html)
        except ParseError as err:
            raise EnergaParseError(str(err)) from err

    async def async_fetch(self) -> MeterData:
        """Return the current meter data."""
        self._session.cookie_jar.clear()
        try:
            token = await self._parse(parse_antixsrf, await self._get(LOGIN_URL))
            payload = {
                "j_username": self._username,
                "j_password": self._password,
                "selectedForm": "1",
                "save": "save",
                "clientOS": "web",
                "loginNow": "zaloguj+się",
                "_antixsrf": token,
            }
            async with self._session.post(LOGIN_URL, data=payload, headers=HEADERS, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    raise EnergaConnectionError(f"Login returned HTTP {resp.status}")
                await resp.read()

            html = await self._get(DATA_URL)
            if await self._executor(is_login_page, html):
                raise EnergaAuthError("Energa rejected the username or password")
            data = await self._parse(parse_meter_page, html)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise EnergaConnectionError(f"Cannot reach Energa: {err}") from err
        finally:
            await self._logout()
        return data

    async def _logout(self) -> None:
        try:
            async with self._session.get(LOGOUT_URL, headers=HEADERS, timeout=TIMEOUT) as resp:
                await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Logout failed (ignored): %s", err)
        self._session.cookie_jar.clear()
