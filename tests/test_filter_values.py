import pytest

from kalinka_plugin_sdk.datamodel import EntityId
from kalinka_plugin_sdk.filters import UnsupportedFilter

from conftest import FakeDirectory
from kalinka_plugin_webradio.genres import GENRES
from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import (
    WebRadioInputModule,
)

POPULAR = EntityId.from_string("kalinka:webradio:catalog:popular")

TAGS = [
    {"name": "jazz", "stationcount": 1064},
    {"name": "smooth jazz", "stationcount": 237},
    {"name": "acid jazz", "stationcount": 40},
]


async def test_genre_values_are_the_curated_genres_with_their_counts():
    module = WebRadioInputModule(FakeDirectory(tags=TAGS))

    values = await module.list_filter_values(POPULAR, "genre", 0, 100)

    assert [value.name for value in values.items] == [genre.label for genre in GENRES]
    assert values.total == len(GENRES)
    jazz = next(value for value in values.items if value.id == "jazz")
    assert (jazz.name, jazz.count) == ("Jazz", 1064)


async def test_typing_also_offers_other_tags_containing_the_text():
    directory = FakeDirectory(tags=TAGS)
    module = WebRadioInputModule(directory)

    values = await module.list_filter_values(POPULAR, "genre", q=" jazz ")

    assert [(value.id, value.name, value.count) for value in values.items] == [
        ("jazz", "Jazz", 1064),
        ("smooth jazz", "Smooth Jazz", 237),
        ("acid jazz", "Acid jazz", 40),
    ]
    assert directory.calls_to("tags")[-1]["name_contains"] == "jazz"


async def test_genre_values_are_paged():
    module = WebRadioInputModule(FakeDirectory())

    values = await module.list_filter_values(POPULAR, "genre", 2, 3)

    assert [value.id for value in values.items] == ["rock", "talk", "dance"]
    assert values.total == len(GENRES)


async def test_typing_offers_curated_genres_while_the_directory_is_down():
    directory = FakeDirectory(tags=TAGS)
    directory.unavailable = True
    module = WebRadioInputModule(directory)

    values = await module.list_filter_values(POPULAR, "genre", q="jazz")

    assert [(value.id, value.count) for value in values.items] == [
        ("jazz", None),
        ("smooth jazz", None),
    ]


@pytest.mark.parametrize(
    "catalog, field",
    [("popular", "q"), ("popular", "country"), ("genres", "genre"), ("root", "genre")],
)
async def test_only_station_listings_have_a_genre_vocabulary(catalog, field):
    module = WebRadioInputModule(FakeDirectory())
    catalog_id = EntityId.from_string(f"kalinka:webradio:catalog:{catalog}")

    with pytest.raises(UnsupportedFilter):
        await module.list_filter_values(catalog_id, field)
