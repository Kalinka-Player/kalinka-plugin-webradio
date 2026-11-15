import asyncio
import logging

import pytest

from kalinka_plugin_sdk.datamodel import EntityId
from kalinka_plugin_sdk.inputmodule import DirectUrl, SearchType, SourceUnavailableError

from conftest import FakeDirectory, record
from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import (
    WebRadioInputModule,
)


def entity(kind, id):
    return EntityId.from_string(f"kalinka:webradio:{kind}:{id}")


async def settle():
    for _ in range(3):
        await asyncio.sleep(0)


async def test_a_station_plays_from_its_current_stream():
    directory = FakeDirectory([record("u1", codec="AAC+")])
    module = WebRadioInputModule(directory)

    source = await module.get_track_source("u1")

    assert source.source == DirectUrl(url="https://stream.example/u1")
    assert (source.format, source.audio_codec) == ("audio/aacp", "aac")
    assert directory.calls_to("byuuid") == [{"uuids": "u1"}]


async def test_a_station_the_directory_no_longer_has_is_not_found():
    module = WebRadioInputModule(FakeDirectory())

    with pytest.raises(LookupError):
        await module.get_track_source("gone")


async def test_a_station_that_moved_to_an_unplayable_stream_says_why():
    directory = FakeDirectory([record("u1", name="Jazz FM")])
    module = WebRadioInputModule(directory)
    await module.browse(entity("catalog", "popular"))
    directory.records = [record("u1", name="Jazz FM", hls=1)]

    with pytest.raises(SourceUnavailableError, match="Jazz FM streams over HLS"):
        await module.get_track_source("u1")


async def test_a_listed_station_still_plays_while_the_directory_is_down():
    directory = FakeDirectory([record("u1")])
    module = WebRadioInputModule(directory)
    await module.browse(entity("catalog", "popular"))
    directory.unavailable = True

    source = await module.get_track_source("u1")

    assert source.source == DirectUrl(url="https://stream.example/u1")


async def test_an_unseen_station_cannot_play_while_the_directory_is_down():
    directory = FakeDirectory([record("u1")])
    directory.unavailable = True
    module = WebRadioInputModule(directory)

    with pytest.raises(SourceUnavailableError, match="cannot be reached"):
        await module.get_track_source("u1")


async def test_a_play_is_reported_without_holding_playback_up():
    directory = FakeDirectory([record("u1")])
    directory.click_gate = asyncio.Event()
    module = WebRadioInputModule(directory)

    await module.get_track_source("u1")
    await settle()
    assert directory.calls_to("click") == [{"uuid": "u1"}]
    assert directory.clicks == []

    directory.click_gate.set()
    await settle()
    assert directory.clicks == ["u1"]


async def test_a_play_that_cannot_be_reported_is_let_go(caplog):
    caplog.set_level(logging.DEBUG, logger=WebRadioInputModule.__module__)
    directory = FakeDirectory([record("u1")])
    module = WebRadioInputModule(directory)

    async def refuse(uuid):
        raise RuntimeError("no")

    directory.count_click = refuse
    source = await module.get_track_source("u1")
    await settle()

    assert source.source.url == "https://stream.example/u1"
    assert "Play of u1 not reported to radio-browser: no" in caplog.text


async def test_closing_the_module_stops_reports_in_flight():
    directory = FakeDirectory([record("u1")])
    directory.click_gate = asyncio.Event()
    module = WebRadioInputModule(directory)
    await module.get_track_source("u1")
    await settle()

    await asyncio.wait_for(module.aclose(), timeout=1)
    directory.click_gate.set()
    await settle()

    assert directory.clicks == []


async def test_track_info_reuses_listed_stations_and_looks_up_the_rest_at_once():
    directory = FakeDirectory([record("a"), record("b"), record("c")])
    module = WebRadioInputModule(directory)
    await module.search(SearchType.track, "station a")
    directory.calls.clear()

    infos = await module.get_track_info(["c", "gone", "a", "b"])

    assert [info.id.id for info in infos] == ["c", "a", "b"]
    assert [info.metadata.title for info in infos] == ["Station c", "Station a", "Station b"]
    assert directory.calls_to("byuuid") == [{"uuids": "c,gone,b"}]


async def test_each_track_info_plays_its_own_station():
    module = WebRadioInputModule(FakeDirectory([record("a"), record("b")]))

    infos = await module.get_track_info(["a", "b"])
    sources = [await info.source_retriever() for info in infos]

    assert [source.source.url for source in sources] == [
        "https://stream.example/a",
        "https://stream.example/b",
    ]


async def test_get_answers_for_stations_and_catalogs():
    module = WebRadioInputModule(FakeDirectory([record("u1")]))

    station = await module.get(entity("track", "u1"))
    shelf = await module.get(entity("catalog", "popular"))
    genre = await module.get(entity("catalog", "genre-smooth-jazz"))

    assert station.track.title == "Station u1"
    assert shelf.catalog.title == "Popular"
    assert genre.catalog.title == "Smooth Jazz"


@pytest.mark.parametrize(
    "kind, id", [("track", "gone"), ("catalog", "nothing"), ("album", "u1")]
)
async def test_get_refuses_what_does_not_exist(kind, id):
    module = WebRadioInputModule(FakeDirectory([record("u1")]))

    with pytest.raises(LookupError):
        await module.get(entity(kind, id))


async def test_get_all_keeps_the_order_asked_for_and_skips_the_unknown():
    directory = FakeDirectory(
        [record("a"), record("b")],
        countries=[{"name": "Germany", "iso_3166_1": "DE", "stationcount": 5599}],
    )
    module = WebRadioInputModule(directory)

    items = await module.get_all(
        [
            entity("track", "b"),
            entity("catalog", "country-DE"),
            entity("track", "gone"),
            entity("catalog", "nothing"),
            entity("track", "a"),
        ]
    )

    assert [item.id.id for item in items] == ["b", "country-DE", "a"]
    assert len(directory.calls_to("byuuid")) == 1


async def test_get_all_resolves_listed_stations_while_the_directory_is_down():
    directory = FakeDirectory([record("a"), record("b")])
    module = WebRadioInputModule(directory)
    await module.search(SearchType.track, "station a")
    directory.unavailable = True

    items = await module.get_all([entity("track", "a"), entity("track", "b")])

    assert [item.id.id for item in items] == ["a"]


async def test_favorites_and_playlists_are_not_kept():
    module = WebRadioInputModule(FakeDirectory())

    assert (await module.list_favorite(SearchType.track, "")).items == []
    assert (await module.get_favorite_ids()).tracks == []
    assert (await module.playlist_user_list()).items == []
    with pytest.raises(NotImplementedError, match="collection"):
        await module.add_to_favorite("kalinka:webradio:track:u1")
    with pytest.raises(NotImplementedError, match="collection"):
        await module.playlist_create("Morning", "")
