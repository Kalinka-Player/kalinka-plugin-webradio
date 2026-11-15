import pytest

from kalinka_plugin_sdk.datamodel import EntityType
from kalinka_plugin_sdk.inputmodule import DirectUrl

from conftest import record
from kalinka_plugin_webradio.stations import (
    Station,
    station_item,
    station_source,
    station_track,
)


def test_a_record_is_tidied():
    station = Station.from_record(
        record(
            "u1",
            name="  Radio\t Paradise \n",
            codec="aac+",
            tags="Jazz, smooth jazz,,jazz , LOUNGE",
            country="The Russian Federation",
            countrycode="ru",
        )
    )

    assert station.name == "Radio Paradise"
    assert station.codec == "AAC+"
    assert station.tags == ("jazz", "smooth jazz", "lounge")
    assert station.country == "Russian Federation"
    assert station.country_code == "RU"


def test_a_record_with_missing_fields_still_parses():
    station = Station.from_record({"stationuuid": "u1", "bitrate": None, "hls": "x"})

    assert station.bitrate == 0
    assert station.hls is False
    assert station.tags == ()
    assert not station.playable


@pytest.mark.parametrize("codec", ["MP3", "AAC", "AAC+", "FLAC"])
def test_streams_the_renderer_decodes_are_playable(codec):
    assert Station.from_record(record("u1", codec=codec)).playable


@pytest.mark.parametrize(
    "fields, reason",
    [
        ({"hls": 1}, "Station u1 streams over HLS, which Kalinka does not play"),
        ({"codec": "OGG"}, "Station u1 streams OGG, which Kalinka does not play"),
        ({"codec": "UNKNOWN"}, "Station u1 streams UNKNOWN, which Kalinka does not play"),
        ({"codec": ""}, "Station u1 streams an unknown format, which Kalinka does not play"),
        ({"ssl_error": 1}, "Station u1 has an invalid security certificate"),
        ({"url_resolved": ""}, "Station u1 has no stream address"),
        ({"url_resolved": "mms://stream.example/u1"}, "Station u1 has no stream address"),
        ({"name": "  "}, "This station has no name in the radio directory"),
    ],
)
def test_unplayable_streams_say_why(fields, reason):
    station = Station.from_record(record("u1", **fields))

    assert not station.playable
    assert station.unplayable_reason == reason


def test_a_station_plays_as_a_track_of_unknown_length():
    station = Station.from_record(
        record(
            "u1",
            name="Jazz FM",
            tags="smooth jazz,radio,jazz",
            favicon="https://logo.example/u1.png",
        )
    )

    track = station_track(station)

    assert track.id.to_string == "kalinka:webradio:track:u1"
    assert track.title == "Jazz FM"
    assert track.duration == 0
    assert track.performer.name == "Germany"
    assert track.performer.id.to_string == "kalinka:webradio:catalog:country-DE"
    assert track.album.id == track.id
    assert track.album.title == "Smooth Jazz, Jazz"
    assert [genre.id.to_string for genre in track.album.genres] == [
        "kalinka:webradio:genre:smooth-jazz",
        "kalinka:webradio:genre:jazz",
    ]
    assert track.album.image.large == "https://logo.example/u1.png"
    assert track.image == track.album.image


def test_a_station_without_a_country_has_no_performer():
    station = Station.from_record(record("u1", country="", countrycode=""))

    assert station_track(station).performer is None


def test_a_favicon_that_is_not_a_web_address_gives_no_cover():
    station = Station.from_record(record("u1", favicon="data:image/png;base64,AAAA"))

    assert station_track(station).album.image is None


@pytest.mark.parametrize(
    "fields, summary",
    [
        ({}, "Germany · MP3 128 kbps"),
        ({"codec": "FLAC", "bitrate": 0}, "Germany · FLAC"),
        ({"country": "", "countrycode": ""}, "MP3 128 kbps"),
    ],
)
def test_a_listed_station_shows_its_country_and_quality(fields, summary):
    item = station_item(Station.from_record(record("u1", **fields)))

    assert item.subname == summary
    assert item.can_add
    assert not item.can_browse
    assert item.track.id.type == EntityType.TRACK


@pytest.mark.parametrize(
    "codec, mime_type, audio_codec",
    [
        ("MP3", "audio/mpeg", "mp3"),
        ("AAC", "audio/aac", "aac"),
        ("AAC+", "audio/aacp", "aac"),
        ("FLAC", "audio/flac", "flac"),
    ],
)
def test_a_station_plays_from_its_stream(codec, mime_type, audio_codec):
    source = station_source(Station.from_record(record("u1", codec=codec)))

    assert source.source == DirectUrl(url="https://stream.example/u1")
    assert source.format == mime_type
    assert source.audio_codec == audio_codec
    assert not source.sequential
