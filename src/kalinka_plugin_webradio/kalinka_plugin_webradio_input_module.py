import asyncio
import logging
from collections import OrderedDict
from functools import partial
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set

from kalinka_plugin_sdk.datamodel import (
    BrowseItem,
    BrowseItemList,
    EmptyList,
    EntityId,
    EntityType,
    FavoriteIds,
    Playlist,
    Preview,
)
from kalinka_plugin_sdk.filters import (
    FilterQuery,
    FilterValueList,
    UnsupportedFilter,
    or_unfiltered,
)
from kalinka_plugin_sdk.inputmodule import (
    InputModule,
    ModuleCapability,
    SearchType,
    SourceUnavailableError,
    TrackInfo,
    TrackSource,
)

from .catalogs import CATALOG_CARDS, GENRE_FIELD, CatalogTree, name_search, narrowed
from .directory import DirectoryUnavailable, StationDirectory
from .ids import DISPLAY_NAME, ROOT, SOURCE, track_id
from .paging import Searches, StationPages
from .stations import Station, station_item, station_source, station_track
from .vocabularies import Vocabularies

logger = logging.getLogger(__name__)


class WebRadioInputModule(InputModule):
    """Internet radio stations from the radio-browser.info directory, each a
    track of unknown length.

    Stations are listed by chart, genre, country and language, searched by
    name, and played straight from the station's stream. Lists hold only
    streams the renderer can decode.

    Borrows ``client``: whoever made it closes it, after :meth:`aclose`.
    """

    BATCH_LOOKUP = 100
    REMEMBERED_STATIONS = 2000

    def __init__(
        self,
        client: StationDirectory,
        *,
        pages: Optional[StationPages] = None,
        vocabularies: Optional[Vocabularies] = None,
    ):
        self._client = client
        self._pages = pages or StationPages(self._fetch_stations)
        self._catalogs = CatalogTree(vocabularies or Vocabularies(client))
        # Stations seen in lists: their metadata without a lookup, and their
        # stream while the directory cannot be reached.
        self._stations: "OrderedDict[str, Station]" = OrderedDict()
        self._clicks: Set[asyncio.Task] = set()

    async def aclose(self) -> None:
        """Stop reporting plays that are still being sent."""
        for task in self._clicks:
            task.cancel()
        await asyncio.gather(*self._clicks, return_exceptions=True)

    def module_name(self) -> str:
        return SOURCE

    def display_name(self) -> str:
        return DISPLAY_NAME

    def capabilities(self) -> FrozenSet[ModuleCapability]:
        # Search lists the most played matches first, which is the order to keep.
        return frozenset({ModuleCapability.CATALOGS, ModuleCapability.RANKED_SEARCH})

    def root_preview(self) -> Optional[Preview]:
        return CATALOG_CARDS

    async def search(
        self, type: SearchType, query: str, offset=0, limit=50
    ) -> BrowseItemList:
        if type != SearchType.track or not query.strip():
            return EmptyList(offset, limit)
        return await self._station_list(name_search(query.strip()), offset, limit)

    async def browse(
        self,
        entity_id: EntityId,
        offset: int = 0,
        limit: int = 50,
        filter: Optional[FilterQuery] = None,
    ) -> BrowseItemList:
        filter = or_unfiltered(filter)
        if entity_id.type != EntityType.CATALOG:
            filter.reject_undeclared(())
            return EmptyList(offset, limit)
        slug = entity_id.id
        filter.reject_undeclared(spec.id for spec in self._catalogs.filters(slug))
        if slug == ROOT:
            return _paged(self._catalogs.root(), offset, limit)
        index = await self._catalogs.index(slug, filter.text())
        if index is not None:
            return _paged(index, offset, limit)
        searches = await self._catalogs.station_searches(slug)
        if searches is None:
            return EmptyList(offset, limit)
        return await self._station_list(narrowed(searches, filter), offset, limit)

    async def get_track_info(self, track_ids: List[str]) -> List[TrackInfo]:
        stations = await self._stations_by_uuid(track_ids)
        return [
            TrackInfo(
                id=track_id(uuid),
                source_retriever=partial(self.get_track_source, uuid),
                metadata=station_track(stations[uuid]),
            )
            for uuid in track_ids
            if uuid in stations
        ]

    async def get_track_source(self, track_id: str) -> TrackSource:
        """The station's current stream, looked up afresh so a moved stream
        plays from where it went; the last one seen while the directory is
        unreachable."""
        try:
            records = await self._client.stations_by_uuid([track_id])
        except DirectoryUnavailable as e:
            station = self._stations.get(track_id)
            if station is None:
                raise SourceUnavailableError(
                    "The radio directory cannot be reached"
                ) from e
            logger.info("Playing %s from its last known stream: %s", track_id, e)
        else:
            station = next(
                (s for s in map(Station.from_record, records) if s.uuid == track_id),
                None,
            )
            if station is None:
                raise LookupError(f"No station {track_id} in the radio directory")
            self._remember([station])
        reason = station.unplayable_reason
        if reason is not None:
            raise SourceUnavailableError(reason)
        self._report_play(station.uuid)
        return station_source(station)

    async def get(self, entity_id: EntityId) -> BrowseItem:
        if entity_id.type == EntityType.TRACK:
            stations = await self._stations_by_uuid([entity_id.id])
            if entity_id.id in stations:
                return station_item(stations[entity_id.id])
        elif entity_id.type == EntityType.CATALOG:
            card = await self._catalogs.card(entity_id.id)
            if card is not None:
                return card
        raise LookupError(f"No {entity_id.to_string} in {DISPLAY_NAME}")

    async def get_all(self, entity_ids: List[EntityId]) -> List[BrowseItem]:
        """Stations in one directory request, anything else one by one, concurrently."""
        uuids = [entity.id for entity in entity_ids if entity.type == EntityType.TRACK]
        stations, others = await asyncio.gather(
            self._stations_or_remembered(uuids),
            super().get_all(
                [entity for entity in entity_ids if entity.type != EntityType.TRACK]
            ),
        )
        others_by_id = {item.id: item for item in others}
        items = []
        for entity in entity_ids:
            if entity.type == EntityType.TRACK:
                if entity.id in stations:
                    items.append(station_item(stations[entity.id]))
            elif entity in others_by_id:
                items.append(others_by_id[entity])
        return items

    async def list_filter_values(
        self,
        catalog_id: EntityId,
        field: str,
        offset: int = 0,
        limit: int = 50,
        q: str = "",
    ) -> FilterValueList:
        if field != GENRE_FIELD or not self._catalogs.is_station_listing(catalog_id.id):
            raise UnsupportedFilter(field, "no such vocabulary here")
        values = await self._catalogs.genre_values(q)
        return FilterValueList(
            offset=offset,
            limit=limit,
            total=len(values),
            items=values[offset : offset + limit],
        )

    async def list_favorite(
        self, type: SearchType, filter: str, offset: int = 0, limit: int = 50
    ) -> BrowseItemList:
        return EmptyList(offset, limit)

    async def get_favorite_ids(self) -> FavoriteIds:
        return FavoriteIds()

    async def add_to_favorite(self, id: str):
        raise NotImplementedError(_NO_FAVORITES)

    async def remove_from_favorite(self, id: str):
        raise NotImplementedError(_NO_FAVORITES)

    async def playlist_user_list(self, offset: int = 0, limit: int = 25) -> BrowseItemList:
        return EmptyList(offset, limit)

    async def playlist_create(self, name: str, description: str) -> Playlist:
        raise NotImplementedError(_NO_PLAYLISTS)

    async def playlist_update(
        self, id: str, name: str | None, description: str | None
    ) -> Playlist:
        raise NotImplementedError(_NO_PLAYLISTS)

    async def playlist_delete(self, id: str):
        raise NotImplementedError(_NO_PLAYLISTS)

    async def playlist_add_tracks(
        self, id: str, track_ids: List[str], allow_duplicates: bool
    ) -> Playlist:
        raise NotImplementedError(_NO_PLAYLISTS)

    async def playlist_remove_tracks(
        self, id: str, playlist_track_ids: List[str]
    ) -> Playlist:
        raise NotImplementedError(_NO_PLAYLISTS)

    async def get_resource_path(self, id: str) -> str | None:
        return None

    async def _fetch_stations(
        self, params: Mapping[str, str], offset: int, limit: int
    ) -> List[Station]:
        records = await self._client.search_stations(
            {**params, "offset": offset, "limit": limit}
        )
        return [Station.from_record(record) for record in records]

    async def _station_list(
        self, searches: Searches, offset: int, limit: int
    ) -> BrowseItemList:
        stations, total = await self._pages.page(searches, offset, limit)
        self._remember(stations)
        return BrowseItemList(
            offset=offset,
            limit=limit,
            total=total,
            items=[station_item(station) for station in stations],
        )

    async def _stations_by_uuid(self, uuids: Sequence[str]) -> Dict[str, Station]:
        """The stations among ``uuids`` that exist, from memory where seen,
        the rest looked up."""
        found = self._remembered(uuids)
        missing = [uuid for uuid in dict.fromkeys(uuids) if uuid not in found]
        for start in range(0, len(missing), self.BATCH_LOOKUP):
            chunk = missing[start : start + self.BATCH_LOOKUP]
            records = await self._client.stations_by_uuid(chunk)
            stations = [Station.from_record(record) for record in records]
            self._remember(stations)
            found.update((station.uuid, station) for station in stations if station.uuid in chunk)
        return found

    async def _stations_or_remembered(self, uuids: Sequence[str]) -> Dict[str, Station]:
        try:
            return await self._stations_by_uuid(uuids)
        except DirectoryUnavailable as e:
            logger.info("Resolving remembered stations only: %s", e)
            return self._remembered(uuids)

    def _remembered(self, uuids: Iterable[str]) -> Dict[str, Station]:
        return {uuid: self._stations[uuid] for uuid in uuids if uuid in self._stations}

    def _remember(self, stations: Iterable[Station]) -> None:
        for station in stations:
            self._stations[station.uuid] = station
            self._stations.move_to_end(station.uuid)
        while len(self._stations) > self.REMEMBERED_STATIONS:
            self._stations.popitem(last=False)

    def _report_play(self, station_uuid: str) -> None:
        # radio-browser asks to be told of every play; playback does not wait for it.
        task = asyncio.create_task(self._send_play(station_uuid))
        self._clicks.add(task)
        task.add_done_callback(self._clicks.discard)

    async def _send_play(self, station_uuid: str) -> None:
        try:
            await self._client.count_click(station_uuid)
        except Exception as e:
            logger.debug("Play of %s not reported to radio-browser: %s", station_uuid, e)


_NO_FAVORITES = f"{DISPLAY_NAME} keeps no favorites; add stations to a collection instead"
_NO_PLAYLISTS = f"{DISPLAY_NAME} has no playlists; add stations to a collection instead"


def _paged(items: List[BrowseItem], offset: int, limit: int) -> BrowseItemList:
    return BrowseItemList(
        offset=offset, limit=limit, total=len(items), items=items[offset : offset + limit]
    )
