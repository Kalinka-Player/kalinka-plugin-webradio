import pytest

from conftest import FakeDirectory
from kalinka_plugin_webradio.directory import DirectoryUnavailable
from kalinka_plugin_webradio.vocabularies import Term, Vocabularies

COUNTRIES = [
    {"name": "Germany", "iso_3166_1": "DE", "stationcount": 5599},
    {"name": "The Russian Federation", "iso_3166_1": "ru", "stationcount": 2487},
    {"name": "Nowhere", "iso_3166_1": None, "stationcount": 3},
    {"name": "The United States Of America", "iso_3166_1": "US", "stationcount": 6957},
]

LANGUAGES = [
    {"name": "german", "iso_639": "de", "stationcount": 3975},
    {"name": "http://stream.example/aac-32", "iso_639": None, "stationcount": 1},
    {"name": "english", "iso_639": "EN", "stationcount": 11296},
]


def vocabularies(directory, now=None):
    clock = (lambda: now[0]) if now is not None else (lambda: 0.0)
    return Vocabularies(directory, ttl_s=60, clock=clock)


async def test_countries_are_those_with_a_code_most_stations_first():
    terms = await vocabularies(FakeDirectory(countries=COUNTRIES)).countries()

    assert terms.ordered == (
        Term("US", "The United States Of America", "United States Of America", 6957),
        Term("DE", "Germany", "Germany", 5599),
        Term("RU", "The Russian Federation", "Russian Federation", 2487),
    )
    assert terms.by_code["RU"].label == "Russian Federation"


async def test_languages_are_those_with_a_code_searched_by_their_own_name():
    terms = await vocabularies(FakeDirectory(languages=LANGUAGES)).languages()

    assert terms.ordered == (
        Term("en", "english", "English", 11296),
        Term("de", "german", "German", 3975),
    )


async def test_tag_counts_cover_the_most_used_tags():
    directory = FakeDirectory(tags=[{"name": "Jazz", "stationcount": 1064}])

    counts = await vocabularies(directory).tag_counts()

    assert counts == {"jazz": 1064}
    assert directory.calls_to("tags")[0]["limit"] == Vocabularies.TAG_COUNTS_LIMIT


async def test_a_vocabulary_is_reused_until_it_expires():
    now = [0.0]
    directory = FakeDirectory(countries=COUNTRIES)
    vocab = vocabularies(directory, now)

    await vocab.countries()
    now[0] = 59
    await vocab.countries()
    assert len(directory.calls_to("countries")) == 1

    now[0] = 61
    await vocab.countries()
    assert len(directory.calls_to("countries")) == 2


async def test_a_stale_vocabulary_is_served_while_the_directory_is_down():
    now = [0.0]
    directory = FakeDirectory(countries=COUNTRIES)
    vocab = vocabularies(directory, now)
    fresh = await vocab.countries()

    now[0] = 61
    directory.unavailable = True

    assert await vocab.countries() == fresh


async def test_without_a_vocabulary_to_serve_the_failure_is_raised():
    directory = FakeDirectory(countries=COUNTRIES)
    directory.unavailable = True

    with pytest.raises(DirectoryUnavailable):
        await vocabularies(directory).countries()


async def test_tags_containing_text_are_asked_for_each_time():
    directory = FakeDirectory(
        tags=[{"name": "Acid Jazz", "stationcount": 40}, {"name": "Jazz Funk", "stationcount": 12}]
    )
    vocab = vocabularies(directory)

    first = await vocab.tags_containing("Jazz", 10)
    await vocab.tags_containing("Jazz", 10)

    assert first == [("acid jazz", 40), ("jazz funk", 12)]
    assert len(directory.calls_to("tags")) == 2
    assert directory.calls_to("tags")[0]["name_contains"] == "Jazz"
