import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Generic, List, Mapping, Optional, Tuple, TypeVar

from .directory import BY_STATION_COUNT, DirectoryUnavailable, StationDirectory
from .stations import country_label

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class Term:
    """A country or language the directory files stations under.

    Attributes:
        code: ISO 3166-1 alpha-2 for a country, ISO 639 for a language.
        name: As the directory spells it, which is what it is searched by.
        label: As it is shown.
        station_count: Stations the directory files under it, playable or not.
    """

    code: str
    name: str
    label: str
    station_count: int


@dataclass(frozen=True)
class Terms:
    """Terms by station count, most first, and by code."""

    ordered: Tuple[Term, ...]
    by_code: Mapping[str, Term]

    @classmethod
    def of(cls, terms: List[Term]) -> "Terms":
        ordered = tuple(sorted(terms, key=lambda term: -term.station_count))
        return cls(ordered, {term.code: term for term in ordered})


class _Expiring(Generic[T]):
    """A value loaded when first asked for and reloaded once older than ``ttl_s``.

    While a reload fails the stale value is served; with none to serve, the
    failure is raised.
    """

    def __init__(
        self, load: Callable[[], Awaitable[T]], ttl_s: float, clock: Callable[[], float]
    ):
        self._load = load
        self._ttl_s = ttl_s
        self._clock = clock
        self._value: Optional[T] = None
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> T:
        async with self._lock:
            if self._value is not None and self._clock() - self._loaded_at < self._ttl_s:
                return self._value
            try:
                self._value = await self._load()
                self._loaded_at = self._clock()
            except DirectoryUnavailable as e:
                if self._value is None:
                    raise
                logger.info("Serving a stale radio-browser vocabulary: %s", e)
            return self._value


class Vocabularies:
    """The directory's countries, languages and tag counts, kept for an hour.

    Only countries and languages with an ISO code are offered: the directory
    also lists free-text languages such as stream URLs and numbers.
    """

    TAG_COUNTS_LIMIT = 1000

    def __init__(
        self,
        client: StationDirectory,
        *,
        ttl_s: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client = client
        self._countries = _Expiring(self._load_countries, ttl_s, clock)
        self._languages = _Expiring(self._load_languages, ttl_s, clock)
        self._tag_counts = _Expiring(self._load_tag_counts, ttl_s, clock)

    async def countries(self) -> Terms:
        return await self._countries.get()

    async def languages(self) -> Terms:
        return await self._languages.get()

    async def tag_counts(self) -> Mapping[str, int]:
        """Stations per tag, for the most used tags."""
        return await self._tag_counts.get()

    async def tags_containing(self, text: str, limit: int) -> List[Tuple[str, int]]:
        """Tags containing ``text`` with their station counts, most used first.
        Asked afresh each time: it answers type-ahead."""
        rows = await self._client.tags({**BY_STATION_COUNT, "limit": limit}, name_contains=text)
        return [
            (str(row["name"]).strip().casefold(), int(row.get("stationcount") or 0))
            for row in rows
            if str(row.get("name") or "").strip()
        ]

    async def _load_countries(self) -> Terms:
        return Terms.of(
            [
                Term(
                    code=str(row["iso_3166_1"]).upper(),
                    name=str(row.get("name") or ""),
                    label=country_label(str(row.get("name") or row["iso_3166_1"])),
                    station_count=int(row.get("stationcount") or 0),
                )
                for row in await self._client.countries()
                if row.get("iso_3166_1")
            ]
        )

    async def _load_languages(self) -> Terms:
        return Terms.of(
            [
                Term(
                    code=str(row["iso_639"]).lower(),
                    name=str(row["name"]),
                    label=str(row["name"])[:1].upper() + str(row["name"])[1:],
                    station_count=int(row.get("stationcount") or 0),
                )
                for row in await self._client.languages()
                if row.get("iso_639") and row.get("name")
            ]
        )

    async def _load_tag_counts(self) -> Dict[str, int]:
        rows = await self._client.tags({**BY_STATION_COUNT, "limit": self.TAG_COUNTS_LIMIT})
        return {
            str(row["name"]).strip().casefold(): int(row.get("stationcount") or 0)
            for row in rows
            if row.get("name")
        }
