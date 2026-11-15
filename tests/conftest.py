import asyncio
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import httpx
import pytest

from kalinka_plugin_webradio.directory import DirectoryUnavailable


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach radio-browser.info; one that tries fails here."""

    async def refuse(self, request):
        raise AssertionError(f"test tried to reach {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def record(uuid: str, **fields: Any) -> Dict[str, Any]:
    """A station as radio-browser returns it, playable unless told otherwise."""
    station = {
        "stationuuid": uuid,
        "name": f"Station {uuid}",
        "url_resolved": f"https://stream.example/{uuid}",
        "codec": "MP3",
        "bitrate": 128,
        "hls": 0,
        "ssl_error": 0,
        "lastcheckok": 1,
        "favicon": "",
        "country": "Germany",
        "countrycode": "DE",
        "language": "german",
        "tags": "",
    }
    station.update(fields)
    return station


class FakeDirectory:
    """Answers as RadioBrowserClient does, from records held in memory.

    Station searches honour the parameters the plugin sends, matching as the
    directory does: ``tagList`` and ``name`` by substring, ``tag`` exactly
    only with ``tagExact``.
    """

    def __init__(
        self,
        records: Iterable[Mapping[str, Any]] = (),
        *,
        countries: Sequence[Mapping[str, Any]] = (),
        languages: Sequence[Mapping[str, Any]] = (),
        tags: Sequence[Mapping[str, Any]] = (),
    ):
        self.records = list(records)
        self.country_rows = list(countries)
        self.language_rows = list(languages)
        self.tag_rows = list(tags)
        self.calls: List[tuple] = []
        self.unavailable = False
        self.clicks: List[str] = []
        self.click_gate: Optional[asyncio.Event] = None
        self.closed = False

    def calls_to(self, endpoint: str) -> List[Dict[str, Any]]:
        return [params for name, params in self.calls if name == endpoint]

    def _answer(self, endpoint: str, params: Mapping[str, Any]) -> None:
        self.calls.append((endpoint, dict(params)))
        if self.unavailable:
            raise DirectoryUnavailable("radio-browser.info cannot be reached")

    async def search_stations(self, params):
        self._answer("search", params)
        rows = [row for row in self.records if _matches(row, params)]
        offset = int(params.get("offset", 0))
        return rows[offset : offset + int(params.get("limit", len(rows)))]

    async def stations_by_uuid(self, uuids):
        self._answer("byuuid", {"uuids": ",".join(uuids)})
        return [row for row in self.records if row["stationuuid"] in uuids]

    async def tags(self, params, name_contains=""):
        self._answer("tags", {**params, "name_contains": name_contains})
        rows = [row for row in self.tag_rows if name_contains in row["name"]]
        return rows[: int(params.get("limit", len(rows)))]

    async def countries(self):
        self._answer("countries", {})
        return self.country_rows

    async def languages(self):
        self._answer("languages", {})
        return self.language_rows

    async def count_click(self, station_uuid):
        self._answer("click", {"uuid": station_uuid})
        if self.click_gate is not None:
            await self.click_gate.wait()
        self.clicks.append(station_uuid)

    async def discover(self):
        self._answer("servers", {})

    async def aclose(self):
        self.closed = True


def _tags(row: Mapping[str, Any]) -> List[str]:
    return [tag.strip().casefold() for tag in str(row.get("tags", "")).split(",") if tag.strip()]


def _matches(row: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
    tags = _tags(row)
    if "name" in params and params["name"].casefold() not in row["name"].casefold():
        return False
    if "tag" in params:
        wanted = params["tag"].casefold()
        exact = params.get("tagExact") == "true"
        if not any(tag == wanted if exact else wanted in tag for tag in tags):
            return False
    for wanted in filter(None, params.get("tagList", "").split(",")):
        if not any(wanted in tag for tag in tags):
            return False
    if "countrycode" in params and row["countrycode"] != params["countrycode"]:
        return False
    if "codec" in params and row["codec"] != params["codec"]:
        return False
    if "bitrateMin" in params and int(row["bitrate"]) < int(params["bitrateMin"]):
        return False
    if "language" in params and row["language"] != params["language"]:
        return False
    return True


@pytest.fixture
def directory():
    return FakeDirectory()
