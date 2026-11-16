import pytest

from kalinka_plugin_sdk.datamodel import CatalogRole, EntityId
from kalinka_plugin_sdk.filters import (
    FilterQuery,
    RangeSelector,
    TextSelector,
    UnsupportedFilter,
    ValuesSelector,
)
from kalinka_plugin_sdk.inputmodule import ModuleCapability, SearchType

from conftest import FakeDirectory, record
from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import (
    WebRadioInputModule,
)


def catalog(slug):
    return EntityId.from_string(f"kalinka:webradio:catalog:{slug}")


def query(text=None, genres=None, **selectors):
    fields = dict(selectors)
    if text is not None:
        fields["q"] = TextSelector(contains=text)
    if genres is not None:
        fields["genre"] = ValuesSelector(all=genres)
    return FilterQuery(fields)


def names(listing):
    return [item.name for item in listing.items]


def ids(listing):
    return [item.id.id for item in listing.items]


async def test_the_root_lists_charts_then_indexes():
    module = WebRadioInputModule(FakeDirectory())

    root = await module.browse(catalog("root"))

    assert names(root) == [
        "Popular",
        "Trending",
        "Top Voted",
        "High Quality",
        "Genres",
        "Countries",
        "Languages",
    ]
    assert root.total == 7
    roles = {item.name: item.catalog.role for item in root.items}
    assert {name for name, role in roles.items() if role == CatalogRole.HIDE_ON_HOME} == {
        "Trending",
        "Top Voted",
        "Countries",
        "Languages",
    }


async def test_station_listings_offer_name_search_and_genres_indexes_text_alone():
    module = WebRadioInputModule(FakeDirectory())

    root = await module.browse(catalog("root"))

    filters = {item.name: [spec.id for spec in item.catalog.filters] for item in root.items}
    assert filters["Popular"] == ["q", "genre"]
    assert filters["High Quality"] == ["q", "genre"]
    assert filters["Countries"] == ["q"]
    genre = root.items[0].catalog.filters[1]
    assert [op.value for op in genre.ops] == ["all"]


@pytest.mark.parametrize(
    "slug, order",
    [("popular", "clickcount"), ("trending", "clicktrend"), ("top-voted", "votes")],
)
async def test_a_chart_lists_stations_in_its_order(slug, order):
    directory = FakeDirectory([record("u1"), record("u2")])
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog(slug), 0, 10)

    assert ids(listing) == ["u1", "u2"]
    assert listing.total == 2
    assert directory.calls_to("search") == [
        {"order": order, "reverse": "true", "hidebroken": "true", "offset": 0, "limit": 100}
    ]


async def test_streams_the_renderer_cannot_play_are_left_out():
    directory = FakeDirectory(
        [record("hls", hls=1), record("ogg", codec="OGG"), record("ok")]
    )
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("popular"))

    assert ids(listing) == ["ok"]


async def test_high_quality_lists_lossless_stations_before_high_bitrates():
    directory = FakeDirectory(
        [
            record("mp3-320", bitrate=320),
            record("flac", codec="FLAC", bitrate=0),
            record("mp3-128", bitrate=128),
            record("aac-256", codec="AAC", bitrate=256),
        ]
    )
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("high-quality"))

    assert ids(listing) == ["flac", "mp3-320", "aac-256"]


async def test_text_and_one_genre_are_matched_by_the_directory():
    directory = FakeDirectory(
        [
            record("a", name="Jazz Lounge", tags="acid jazz"),
            record("b", name="Lounge FM", tags="jazz"),
            record("c", name="Jazz Radio", tags="jazz"),
        ]
    )
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("popular"), filter=query("jazz", ["Jazz"]))

    assert ids(listing) == ["c"]
    params = directory.calls_to("search")[0]
    assert params["name"] == "jazz"
    assert (params["tag"], params["tagExact"]) == ("jazz", "true")
    assert "tagList" not in params


async def test_further_genres_must_all_be_carried_exactly():
    directory = FakeDirectory(
        [
            record("a", tags="jazz,acid lounge"),
            record("b", tags="jazz,lounge"),
            record("c", tags="jazz"),
        ]
    )
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("popular"), filter=query(genres=["jazz", "lounge"]))

    assert ids(listing) == ["b"]
    assert directory.calls_to("search")[0]["tagList"] == "lounge"


@pytest.mark.parametrize(
    "filter",
    [
        FilterQuery({"genre": ValuesSelector(any=["jazz", "rock"])}),
        FilterQuery({"genre": ValuesSelector(none=["news"])}),
        FilterQuery({"genre": ValuesSelector(all=["rock,pop"])}),
        FilterQuery({"genre": ValuesSelector(all=[" "])}),
        FilterQuery({"genre": TextSelector(contains="jazz")}),
        FilterQuery({"year": RangeSelector(gte=1990)}),
    ],
)
async def test_a_filter_the_listing_cannot_honour_is_refused(filter):
    directory = FakeDirectory([record("u1")])
    module = WebRadioInputModule(directory)

    with pytest.raises(UnsupportedFilter):
        await module.browse(catalog("popular"), filter=filter)
    assert directory.calls_to("search") == []


async def test_a_genre_lists_stations_carrying_its_tag():
    directory = FakeDirectory(
        [record("a", tags="classic rock"), record("b", tags="rock,pop"), record("c", tags="pop")]
    )
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("genre-rock"))
    narrowed = await module.browse(catalog("genre-rock"), filter=query(genres=["pop"]))

    assert ids(listing) == ["b"]
    assert ids(narrowed) == ["b"]
    params = directory.calls_to("search")[1]
    assert (params["tag"], params["tagExact"], params["tagList"]) == ("rock", "true", "pop")


async def test_a_country_lists_its_stations():
    directory = FakeDirectory([record("de"), record("fr", countrycode="FR", country="France")])
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("country-FR"))

    assert ids(listing) == ["fr"]
    assert directory.calls_to("search")[0]["countrycode"] == "FR"


async def test_a_language_lists_stations_by_the_directory_s_name_for_it():
    directory = FakeDirectory(
        [record("de"), record("en", language="english")],
        languages=[{"name": "english", "iso_639": "en", "stationcount": 11296}],
    )
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog("language-en"))

    assert ids(listing) == ["en"]
    params = directory.calls_to("search")[0]
    assert (params["language"], params["languageExact"]) == ("english", "true")


@pytest.mark.parametrize(
    "slug", ["genre-polka", "country-de", "country-DEU", "language-xx", "nothing"]
)
async def test_a_catalog_that_does_not_exist_lists_nothing(slug):
    directory = FakeDirectory([record("u1")], languages=[])
    module = WebRadioInputModule(directory)

    listing = await module.browse(catalog(slug))

    assert listing.items == []
    assert directory.calls_to("search") == []


async def test_genres_are_listed_in_curated_order_with_their_station_counts():
    directory = FakeDirectory(
        tags=[{"name": "rock", "stationcount": 2614}, {"name": "pop", "stationcount": 1}]
    )
    module = WebRadioInputModule(directory)

    genres = await module.browse(catalog("genres"), 0, 3)

    assert names(genres) == ["Pop", "News", "Rock"]
    assert [item.subname for item in genres.items] == ["1 station", None, "2,614 stations"]
    assert genres.items[2].id.id == "genre-rock"
    assert [spec.id for spec in genres.items[2].catalog.filters] == ["q", "genre"]


async def test_genres_are_listed_without_counts_while_the_directory_is_down():
    directory = FakeDirectory()
    directory.unavailable = True
    module = WebRadioInputModule(directory)

    genres = await module.browse(catalog("genres"), 0, 2)

    assert names(genres) == ["Pop", "News"]
    assert genres.total > 40


async def test_an_index_narrows_to_names_containing_the_text():
    module = WebRadioInputModule(FakeDirectory())

    genres = await module.browse(catalog("genres"), filter=query("rock"))

    assert names(genres) == ["Rock", "Classic Rock", "Hard Rock"]


async def test_countries_are_listed_most_stations_first():
    directory = FakeDirectory(
        countries=[
            {"name": "Germany", "iso_3166_1": "DE", "stationcount": 5599},
            {"name": "The United States Of America", "iso_3166_1": "US", "stationcount": 6957},
        ]
    )
    module = WebRadioInputModule(directory)

    countries = await module.browse(catalog("countries"))
    by_code = await module.browse(catalog("countries"), filter=query("de"))

    assert names(countries) == ["United States Of America", "Germany"]
    assert ids(countries) == ["country-US", "country-DE"]
    assert countries.items[0].subname == "6,957 stations"
    assert names(by_code) == ["Germany"]


async def test_an_index_refuses_the_genre_filter():
    module = WebRadioInputModule(FakeDirectory())

    with pytest.raises(UnsupportedFilter):
        await module.browse(catalog("genres"), filter=query(genres=["rock"]))


async def test_a_station_has_nothing_to_browse():
    module = WebRadioInputModule(FakeDirectory([record("u1")]))
    station = EntityId.from_string("kalinka:webradio:track:u1")

    assert (await module.browse(station)).items == []
    with pytest.raises(UnsupportedFilter):
        await module.browse(station, filter=query("x"))


async def test_search_finds_stations_by_name_most_played_first():
    directory = FakeDirectory([record("a", name="Jazz FM"), record("b", name="Rock FM")])
    module = WebRadioInputModule(directory)

    found = await module.search(SearchType.track, " jazz ")

    assert ids(found) == ["a"]
    assert directory.calls_to("search")[0] == {
        "name": "jazz",
        "order": "clickcount",
        "reverse": "true",
        "hidebroken": "true",
        "offset": 0,
        "limit": 100,
    }


@pytest.mark.parametrize(
    "kind, text",
    [(SearchType.album, "jazz"), (SearchType.artist, "jazz"), (SearchType.track, "  ")],
)
async def test_search_finds_only_stations_and_only_for_some_text(kind, text):
    directory = FakeDirectory([record("a", name="Jazz FM")])
    module = WebRadioInputModule(directory)

    assert (await module.search(kind, text)).items == []
    assert directory.calls == []


def test_the_module_offers_catalogs_and_keeps_its_search_order():
    module = WebRadioInputModule(FakeDirectory())

    assert module.capabilities() == {
        ModuleCapability.CATALOGS,
        ModuleCapability.RANKED_SEARCH,
    }
    assert module.module_name() == "webradio"
    assert module.display_name() == "Web Radio"


async def test_station_cards_play_individually_in_browse_and_metadata():
    module = WebRadioInputModule(
        FakeDirectory(
            countries=[{"name": "Germany", "iso_3166_1": "DE", "stationcount": 12}],
            languages=[{"name": "english", "iso_639": "en", "stationcount": 12}],
        )
    )
    root = await module.browse(catalog("root"))
    assert [item.catalog.play_individually for item in root.items] == [
        True, True, True, True, False, False, False,
    ]
    for slug in (
        "popular", "trending", "top-voted", "high-quality",
        "genre-rock", "country-DE", "language-en",
    ):
        item = await module.get(catalog(slug))
        assert item.catalog.play_individually, slug
    for slug in ("genres", "countries", "languages"):
        assert not (await module.get(catalog(slug))).catalog.play_individually
        listing = await module.browse(catalog(slug))
        assert listing.items
        assert all(item.catalog.play_individually for item in listing.items)
