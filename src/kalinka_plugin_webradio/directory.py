import asyncio
import logging
import random
from typing import Any, Callable, List, Mapping, MutableSequence, Optional, Protocol, Sequence
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

DISCOVERY_HOST = "all.api.radio-browser.info"

Params = Mapping[str, str | int]

BY_STATION_COUNT = {"order": "stationcount", "reverse": "true", "hidebroken": "true"}


class DirectoryUnavailable(RuntimeError):
    """No radio-browser server answered."""


class StationDirectory(Protocol):
    """The station directory this plugin reads, as radio-browser.info's JSON
    API shapes it. Every call raises :class:`DirectoryUnavailable` when the
    directory cannot be reached."""

    async def search_stations(self, params: Params) -> List[dict]: ...

    async def stations_by_uuid(self, uuids: Sequence[str]) -> List[dict]: ...

    async def tags(self, params: Params, name_contains: str = "") -> List[dict]: ...

    async def countries(self) -> List[dict]: ...

    async def languages(self) -> List[dict]: ...

    async def count_click(self, station_uuid: str) -> None: ...


class Mirrors:
    """The radio-browser servers to ask, the one to try first at the front.

    radio-browser asks clients to spread their load over its servers at
    random and to move on to the next one when a server fails.
    """

    def __init__(
        self,
        hosts: Sequence[str] = (DISCOVERY_HOST,),
        shuffle: Callable[[MutableSequence[str]], None] = random.shuffle,
    ):
        self._hosts = list(hosts)
        self._shuffle = shuffle

    @property
    def hosts(self) -> List[str]:
        return list(self._hosts)

    def replace(self, hosts: Sequence[str]) -> None:
        """Ask ``hosts`` from now on, in random order. An empty list keeps the
        servers known so far."""
        unique = list(dict.fromkeys(host for host in hosts if host))
        if unique:
            self._shuffle(unique)
            self._hosts = unique

    def demote(self, host: str) -> None:
        if host in self._hosts:
            self._hosts.remove(host)
            self._hosts.append(host)


class RadioBrowserClient(StationDirectory):
    """The :class:`StationDirectory` the plugin ships, over radio-browser.info.

    Owns the HTTP client it is given and closes it in :meth:`aclose`. A call
    that cannot reach any server raises :class:`DirectoryUnavailable`; a
    request the directory rejects raises ``httpx.HTTPStatusError``.
    """

    # A failing server costs one retry on the next, never a third request.
    ATTEMPTS = 2
    # A whole request, inside the server's 3 s budget; httpx times only each read.
    DEADLINE_S = 2.0

    def __init__(self, http: httpx.AsyncClient, mirrors: Optional[Mirrors] = None):
        self._http = http
        self._mirrors = mirrors or Mirrors()

    @classmethod
    def create(cls, user_agent: str) -> "RadioBrowserClient":
        return cls(
            httpx.AsyncClient(
                timeout=httpx.Timeout(cls.DEADLINE_S, connect=1.0),
                headers={"User-Agent": user_agent},
                follow_redirects=True,
            )
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def discover(self) -> None:
        """Learn which servers are up. Until this succeeds, requests go to the
        discovery name, which resolves to all of them."""
        try:
            servers = await self._get(DISCOVERY_HOST, "/json/servers", {})
        except (httpx.HTTPError, TimeoutError, ValueError) as e:
            logger.warning("Could not list the radio-browser servers: %s", e)
            return
        self._mirrors.replace(
            [str(server.get("name") or "") for server in servers if isinstance(server, dict)]
        )
        logger.info("radio-browser servers: %s", ", ".join(self._mirrors.hosts))

    async def search_stations(self, params: Params) -> List[dict]:
        return await self._request("/json/stations/search", params)

    async def stations_by_uuid(self, uuids: Sequence[str]) -> List[dict]:
        return await self._request("/json/stations/byuuid", {"uuids": ",".join(uuids)})

    async def tags(self, params: Params, name_contains: str = "") -> List[dict]:
        path = "/json/tags"
        if name_contains:
            path += "/" + quote(name_contains, safe="")
        return await self._request(path, params)

    async def countries(self) -> List[dict]:
        return await self._request("/json/countries", BY_STATION_COUNT)

    async def languages(self) -> List[dict]:
        return await self._request("/json/languages", BY_STATION_COUNT)

    async def count_click(self, station_uuid: str) -> None:
        """Tell the directory a station was played, which is what its
        popularity charts count."""
        await self._request(f"/json/url/{quote(station_uuid, safe='')}", {})

    async def _request(self, path: str, params: Params) -> Any:
        failure: Optional[Exception] = None
        for host in self._mirrors.hosts[: self.ATTEMPTS]:
            try:
                return await self._get(host, path, params)
            except (httpx.TimeoutException, TimeoutError) as e:
                # The call's budget is spent; asking another server would overrun it.
                self._mirrors.demote(host)
                raise DirectoryUnavailable("radio-browser.info did not answer in time") from e
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                failure = e
            except (httpx.TransportError, ValueError) as e:
                failure = e
            logger.info("radio-browser server %s failed: %s", host, failure)
            self._mirrors.demote(host)
        raise DirectoryUnavailable("radio-browser.info cannot be reached") from failure

    async def _get(self, host: str, path: str, params: Params) -> Any:
        async with asyncio.timeout(self.DEADLINE_S):
            response = await self._http.get(f"https://{host}{path}", params=params)
        response.raise_for_status()
        return response.json()
