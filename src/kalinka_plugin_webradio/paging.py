import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import (
    Awaitable,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Set,
    Tuple,
)

from .stations import Station


@dataclass(frozen=True)
class StationSearch:
    """One directory station search, and the tags each station it lists must
    carry exactly.

    radio-browser matches ``tagList`` by substring, so ``tagList=jazz`` also
    lists "acid jazz" stations; ``required_tags`` holds them to the tag.
    """

    params: Tuple[Tuple[str, str], ...]
    required_tags: FrozenSet[str] = frozenset()

    @classmethod
    def of(
        cls, params: Mapping[str, str], required_tags: Iterable[str] = ()
    ) -> "StationSearch":
        return cls(tuple(sorted(params.items())), frozenset(required_tags))


Searches = Tuple[StationSearch, ...]

# (search parameters, offset, limit) -> the stations the directory lists there.
Fetch = Callable[[Mapping[str, str], int, int], Awaitable[List[Station]]]


@dataclass(eq=False)
class _Listing:
    searches: Searches
    created: float
    stations: List[Station] = field(default_factory=list)
    seen: Set[str] = field(default_factory=set)
    search_index: int = 0
    directory_offset: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def exhausted(self) -> bool:
        return self.search_index >= len(self.searches)


class StationPages:
    """Pages of a listing's playable stations, numbered over those alone.

    The directory lists streams the renderer cannot play, and a client asks
    for its next page at the count it has already been given, so dropping
    those from one page would shift every page after it. Each listing keeps
    the playable stations found so far and where its searches stopped, and
    later pages carry on from there until the listing expires. A listing of
    several searches lists each in turn, every station once.

    Safe for concurrent use from one event loop: pages of the same listing
    are read one at a time.
    """

    def __init__(
        self,
        fetch: Fetch,
        *,
        batch: int = 100,
        max_batches: int = 5,
        ttl_s: float = 900.0,
        max_listings: int = 64,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self._batch = batch
        self._max_batches = max_batches
        self._ttl_s = ttl_s
        self._max_listings = max_listings
        self._clock = clock
        self._listings: "OrderedDict[Searches, _Listing]" = OrderedDict()

    async def page(
        self, searches: Searches, offset: int, limit: int
    ) -> Tuple[List[Station], int]:
        """Up to ``limit`` playable stations from ``offset``, and how many the
        listing holds: exact once its searches are exhausted, otherwise the
        count found so far plus one more page.

        At most ``max_batches`` directory requests are made per page, which
        can leave a page short while the total still promises more.
        """
        listing = self._listing(searches)
        async with listing.lock:
            batches = 0
            while (
                len(listing.stations) < offset + limit
                and not listing.exhausted
                and batches < self._max_batches
            ):
                await self._extend(listing, max(self._batch, limit))
                batches += 1
        total = len(listing.stations) + (0 if listing.exhausted else limit)
        return listing.stations[offset : offset + limit], total

    def _listing(self, searches: Searches) -> _Listing:
        now = self._clock()
        listing = self._listings.pop(searches, None)
        if listing is None or now - listing.created > self._ttl_s:
            listing = _Listing(searches=searches, created=now)
        self._listings[searches] = listing
        while len(self._listings) > self._max_listings:
            self._listings.popitem(last=False)
        return listing

    async def _extend(self, listing: _Listing, size: int) -> None:
        search = listing.searches[listing.search_index]
        params: Dict[str, str] = dict(search.params)
        found = await self._fetch(params, listing.directory_offset, size)
        listing.directory_offset += len(found)
        for station in found:
            if (
                station.playable
                and station.has_tags(search.required_tags)
                and station.uuid not in listing.seen
            ):
                listing.seen.add(station.uuid)
                listing.stations.append(station)
        if len(found) < size:
            listing.search_index += 1
            listing.directory_offset = 0
