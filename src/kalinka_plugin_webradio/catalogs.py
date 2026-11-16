import logging
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from kalinka_plugin_sdk.datamodel import (
    BrowseItem,
    CardSize,
    Catalog,
    CatalogRole,
    Preview,
    PreviewContentType,
    PreviewType,
)
from kalinka_plugin_sdk.filters import (
    TEXT_FIELD,
    FilterKind,
    FilterOp,
    FilterQuery,
    FilterSpec,
    FilterValue,
    TextSelector,
    UnsupportedFilter,
)

from .directory import DirectoryUnavailable
from .genres import BY_SLUG, BY_TAG, GENRES
from .ids import COUNTRY_PREFIX, GENRE_PREFIX, LANGUAGE_PREFIX, catalog_id
from .paging import Searches, StationSearch
from .vocabularies import Term, Vocabularies

logger = logging.getLogger(__name__)

GENRE_FIELD = "genre"

STATION_FILTERS = [
    FilterSpec(id=TEXT_FIELD, kind=FilterKind.TEXT, label="Search station names"),
    # radio-browser requires every tag it is given, so genres intersect.
    FilterSpec(id=GENRE_FIELD, kind=FilterKind.VALUES, label="Genre", ops=[FilterOp.ALL]),
]

STATION_PREVIEW = Preview(
    type=PreviewType.IMAGE_TEXT,
    content_type=PreviewContentType.TRACK,
    items_count=20,
    rows_count=2,
    aspect_ratio=1.0,
    card_size=CardSize.SMALL,
)

# Clients open a listing previewed as image cards as a grid of cards.
CATALOG_CARDS = Preview(
    type=PreviewType.IMAGE_TEXT,
    content_type=PreviewContentType.CATALOG,
    items_count=20,
    rows_count=2,
    card_size=CardSize.SMALL,
)

_BY_CLICKS = {"order": "clickcount", "reverse": "true"}


@dataclass(frozen=True)
class _Shelf:
    """A station listing on the root, filled by its searches in turn."""

    slug: str
    title: str
    description: str
    searches: Tuple[Mapping[str, str], ...]
    role: CatalogRole


SHELVES = (
    _Shelf(
        "popular",
        "Popular",
        "Most played in the last day",
        (_BY_CLICKS,),
        CatalogRole.DISCOVERY,
    ),
    _Shelf(
        "trending",
        "Trending",
        "Gaining listeners fastest",
        ({"order": "clicktrend", "reverse": "true"},),
        # Kept off home: radio-browser's trend has matched its play count since
        # at least 2026-11-15, which would repeat Popular there.
        CatalogRole.HIDE_ON_HOME,
    ),
    _Shelf(
        "top-voted",
        "Top Voted",
        "Most voted for by listeners",
        ({"order": "votes", "reverse": "true"},),
        CatalogRole.HIDE_ON_HOME,
    ),
    _Shelf(
        "high-quality",
        "High Quality",
        "Lossless FLAC first, then 256 kbps and up",
        # FLAC stations report no bitrate, so bitrateMin alone would miss them.
        ({"codec": "FLAC", **_BY_CLICKS}, {"bitrateMin": "256", **_BY_CLICKS}),
        CatalogRole.DISCOVERY,
    ),
)

_SHELF_BY_SLUG = {shelf.slug: shelf for shelf in SHELVES}


@dataclass(frozen=True)
class _Index:
    """A catalog of catalogs: one station listing per genre, country or language."""

    slug: str
    title: str
    description: str
    role: CatalogRole

    @property
    def filters(self) -> List[FilterSpec]:
        return [
            FilterSpec(
                id=TEXT_FIELD, kind=FilterKind.TEXT, label=f"Search {self.title.lower()}"
            )
        ]


GENRES_INDEX = _Index("genres", "Genres", "Stations by genre", CatalogRole.DISCOVERY)
COUNTRIES_INDEX = _Index(
    "countries", "Countries", "Stations by country", CatalogRole.HIDE_ON_HOME
)
LANGUAGES_INDEX = _Index(
    "languages", "Languages", "Stations by spoken language", CatalogRole.HIDE_ON_HOME
)

_INDEX_BY_SLUG = {
    index.slug: index for index in (GENRES_INDEX, COUNTRIES_INDEX, LANGUAGES_INDEX)
}


def narrowed(searches: Sequence[Mapping[str, str]], filter: FilterQuery) -> Searches:
    """A station listing's searches under ``filter``, which may hold only the
    station filters."""
    filter.reject_undeclared(spec.id for spec in STATION_FILTERS)
    name = filter.text().strip()
    genres = filter.values(GENRE_FIELD)
    if genres is not None and (genres.any or genres.none):
        raise UnsupportedFilter(
            GENRE_FIELD, "this source can only require every genre at once"
        )
    tags = list(
        dict.fromkeys(tag.strip().casefold() for tag in (genres.all if genres else ()))
    )
    if "" in tags or any("," in tag for tag in tags):
        raise UnsupportedFilter(GENRE_FIELD, "a genre must be one non-empty tag")
    return tuple(_narrowed(search, name, tags) for search in searches)


def name_search(query: str) -> Searches:
    """Stations whose names contain ``query``, most played first."""
    return narrowed((_BY_CLICKS,), FilterQuery({TEXT_FIELD: TextSelector(contains=query)}))


def _narrowed(search: Mapping[str, str], name: str, tags: List[str]) -> StationSearch:
    params = {**search, "hidebroken": "true"}
    if name:
        params["name"] = name
    loose = tags
    # One tag the directory can match exactly; the rest only by substring.
    if tags and "tag" not in params:
        params["tag"], params["tagExact"] = tags[0], "true"
        loose = tags[1:]
    if loose:
        params["tagList"] = ",".join(loose)
    return StationSearch.of(params, loose)


class CatalogTree:
    """This source's catalogs and what each lists.

    The root holds four station shelves and three indexes, and each index
    holds a station listing per genre, country or language. Station listings
    take the station filters; indexes take text alone.
    """

    TYPE_AHEAD_LIMIT = 50

    def __init__(self, vocabularies: Vocabularies):
        self._vocabularies = vocabularies

    @staticmethod
    def is_station_listing(slug: str) -> bool:
        return slug in _SHELF_BY_SLUG or slug.startswith(
            (GENRE_PREFIX, COUNTRY_PREFIX, LANGUAGE_PREFIX)
        )

    def filters(self, slug: str) -> List[FilterSpec]:
        index = _INDEX_BY_SLUG.get(slug)
        if index is not None:
            return index.filters
        return STATION_FILTERS if self.is_station_listing(slug) else []

    def root(self) -> List[BrowseItem]:
        return [_shelf_card(shelf) for shelf in SHELVES] + [
            _index_card(index) for index in _INDEX_BY_SLUG.values()
        ]

    async def station_searches(
        self, slug: str
    ) -> Optional[Tuple[Mapping[str, str], ...]]:
        """The searches that fill a station listing, before filtering; None
        for a slug that names no station listing."""
        shelf = _SHELF_BY_SLUG.get(slug)
        if shelf is not None:
            return shelf.searches
        if slug.startswith(GENRE_PREFIX):
            genre = BY_SLUG.get(slug.removeprefix(GENRE_PREFIX))
            if genre is None:
                return None
            return ({"tag": genre.tag, "tagExact": "true", **_BY_CLICKS},)
        if slug.startswith(COUNTRY_PREFIX):
            code = slug.removeprefix(COUNTRY_PREFIX)
            if not (len(code) == 2 and code.isascii() and code.isalpha() and code.isupper()):
                return None
            return ({"countrycode": code, **_BY_CLICKS},)
        if slug.startswith(LANGUAGE_PREFIX):
            language = await self._language(slug.removeprefix(LANGUAGE_PREFIX))
            if language is None:
                return None
            return ({"language": language.name, "languageExact": "true", **_BY_CLICKS},)
        return None

    async def index(self, slug: str, text: str) -> Optional[List[BrowseItem]]:
        """The catalogs an index lists, those matching ``text`` where given,
        most stations first; None for a slug that names no index."""
        if slug == GENRES_INDEX.slug:
            counts = await self._tag_counts()
            return [
                _listing_card(GENRE_PREFIX + genre.slug, genre.label, counts.get(genre.tag))
                for genre in GENRES
                if _matches(text, genre.label, genre.tag)
            ]
        if slug == COUNTRIES_INDEX.slug:
            terms = (await self._vocabularies.countries()).ordered
            return _term_cards(COUNTRY_PREFIX, terms, text)
        if slug == LANGUAGES_INDEX.slug:
            terms = (await self._vocabularies.languages()).ordered
            return _term_cards(LANGUAGE_PREFIX, terms, text)
        return None

    async def card(self, slug: str) -> Optional[BrowseItem]:
        """The card that leads to a catalog, or None for a slug naming none."""
        if slug in _SHELF_BY_SLUG:
            return _shelf_card(_SHELF_BY_SLUG[slug])
        if slug in _INDEX_BY_SLUG:
            return _index_card(_INDEX_BY_SLUG[slug])
        if slug.startswith(GENRE_PREFIX):
            genre = BY_SLUG.get(slug.removeprefix(GENRE_PREFIX))
            if genre is None:
                return None
            return _listing_card(slug, genre.label, (await self._tag_counts()).get(genre.tag))
        if slug.startswith(COUNTRY_PREFIX):
            terms = await self._vocabularies.countries()
            term = terms.by_code.get(slug.removeprefix(COUNTRY_PREFIX))
        elif slug.startswith(LANGUAGE_PREFIX):
            term = await self._language(slug.removeprefix(LANGUAGE_PREFIX))
        else:
            return None
        return None if term is None else _listing_card(slug, term.label, term.station_count)

    async def genre_values(self, text: str) -> List[FilterValue]:
        """The genre filter's vocabulary: the curated genres, then, while
        ``text`` is being typed, any other tag containing it."""
        text = text.strip()
        counts = await self._tag_counts()
        values = [
            FilterValue(id=genre.tag, name=genre.label, count=counts.get(genre.tag))
            for genre in GENRES
            if _matches(text, genre.label, genre.tag)
        ]
        if text:
            try:
                others = await self._vocabularies.tags_containing(text, self.TYPE_AHEAD_LIMIT)
            except DirectoryUnavailable as e:
                logger.info("Genre type-ahead offers curated genres only: %s", e)
                others = []
            values += [
                FilterValue(id=tag, name=tag[:1].upper() + tag[1:], count=count)
                for tag, count in others
                if tag not in BY_TAG
            ]
        return values

    async def _language(self, code: str) -> Optional[Term]:
        return (await self._vocabularies.languages()).by_code.get(code)

    async def _tag_counts(self) -> Mapping[str, int]:
        try:
            return await self._vocabularies.tag_counts()
        except DirectoryUnavailable as e:
            logger.info("Genres are listed without station counts: %s", e)
            return {}


def _matches(text: str, *names: str) -> bool:
    needle = text.strip().casefold()
    return not needle or any(needle in name.casefold() for name in names)


def _term_cards(prefix: str, terms: Iterable[Term], text: str) -> List[BrowseItem]:
    return [
        _listing_card(prefix + term.code, term.label, term.station_count)
        for term in terms
        if _matches(text, term.label, term.code)
    ]


def _card(
    slug: str,
    title: str,
    *,
    description: str,
    filters: List[FilterSpec],
    preview: Preview,
    role: CatalogRole,
) -> BrowseItem:
    id = catalog_id(slug)
    return BrowseItem(
        id=id,
        name=title,
        subname=description or None,
        can_browse=True,
        can_add=False,
        catalog=Catalog(
            id=id,
            title=title,
            description=description,
            filters=filters,
            preview_config=preview,
            role=role,
        ),
    )


def _shelf_card(shelf: _Shelf) -> BrowseItem:
    return _card(
        shelf.slug,
        shelf.title,
        description=shelf.description,
        filters=STATION_FILTERS,
        preview=STATION_PREVIEW,
        role=shelf.role,
    )


def _index_card(index: _Index) -> BrowseItem:
    return _card(
        index.slug,
        index.title,
        description=index.description,
        filters=index.filters,
        preview=CATALOG_CARDS,
        role=index.role,
    )


def _listing_card(slug: str, title: str, station_count: Optional[int]) -> BrowseItem:
    return _card(
        slug,
        title,
        description=_station_count(station_count),
        filters=STATION_FILTERS,
        preview=STATION_PREVIEW,
        role=CatalogRole.DISCOVERY,
    )


def _station_count(count: Optional[int]) -> str:
    if not count:
        return ""
    return "1 station" if count == 1 else f"{count:,} stations"
