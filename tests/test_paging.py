import asyncio

import pytest

from conftest import record
from kalinka_plugin_webradio.directory import DirectoryUnavailable
from kalinka_plugin_webradio.paging import StationPages, StationSearch
from kalinka_plugin_webradio.stations import Station


class Rows:
    """A directory search over fixed rows that records what it was asked."""

    def __init__(self, rows_by_search):
        self.rows_by_search = rows_by_search
        self.calls = []
        self.fail_next = False

    async def __call__(self, params, offset, limit):
        self.calls.append((params.get("order"), offset, limit))
        if self.fail_next:
            self.fail_next = False
            raise DirectoryUnavailable("down")
        rows = self.rows_by_search[params.get("order")]
        return [Station.from_record(row) for row in rows[offset : offset + limit]]


def by(order, required_tags=()):
    return StationSearch.of({"order": order}, required_tags)


def uuids(stations):
    return [station.uuid for station in stations]


def mixed(count):
    """Every third station streams over HLS."""
    return [record(f"s{i}", hls=int(i % 3 == 2)) for i in range(count)]


async def test_pages_count_playable_stations_only():
    rows = Rows({"clicks": mixed(30)})
    pages = StationPages(rows, batch=10)
    playable = [f"s{i}" for i in range(30) if i % 3 != 2]

    first, _ = await pages.page((by("clicks"),), 0, 7)
    second, _ = await pages.page((by("clicks"),), 7, 7)
    third, total = await pages.page((by("clicks"),), 14, 7)

    assert uuids(first + second + third) == playable[:20]
    assert total == 20


async def test_later_pages_carry_on_where_the_directory_stopped():
    rows = Rows({"clicks": mixed(30)})
    pages = StationPages(rows, batch=10)

    await pages.page((by("clicks"),), 0, 5)
    await pages.page((by("clicks"),), 5, 5)

    assert rows.calls == [("clicks", 0, 10), ("clicks", 10, 10)]


async def test_the_total_promises_more_until_the_searches_run_out():
    rows = Rows({"clicks": mixed(30)})
    pages = StationPages(rows, batch=10)

    _, total = await pages.page((by("clicks"),), 0, 5)
    assert total == 7 + 5

    _, total = await pages.page((by("clicks"),), 0, 100)
    assert total == 20


async def test_searches_are_listed_in_turn_each_station_once():
    rows = Rows(
        {
            "flac": [record("f1"), record("f2")],
            "bitrate": [record("b1"), record("f2"), record("b2")],
        }
    )
    pages = StationPages(rows, batch=10)

    stations, total = await pages.page((by("flac"), by("bitrate")), 0, 10)

    assert uuids(stations) == ["f1", "f2", "b1", "b2"]
    assert total == 4


async def test_required_tags_hold_stations_to_the_exact_tag():
    rows = Rows(
        {
            "clicks": [
                record("a", tags="acid jazz"),
                record("b", tags="jazz,lounge"),
                record("c", tags="jazz"),
            ]
        }
    )
    pages = StationPages(rows, batch=10)

    stations, _ = await pages.page((by("clicks", ["jazz", "lounge"]),), 0, 10)

    assert uuids(stations) == ["b"]


async def test_a_page_asks_the_directory_a_bounded_number_of_times():
    rows = Rows({"clicks": [record(f"s{i}", hls=1) for i in range(100)]})
    pages = StationPages(rows, batch=10, max_batches=3)

    stations, total = await pages.page((by("clicks"),), 0, 5)

    assert stations == []
    assert total == 5
    assert len(rows.calls) == 3


async def test_a_page_larger_than_a_batch_is_fetched_whole():
    rows = Rows({"clicks": mixed(300)})
    pages = StationPages(rows, batch=10)

    await pages.page((by("clicks"),), 0, 50)

    assert rows.calls[0] == ("clicks", 0, 50)


async def test_a_listing_is_fetched_afresh_once_it_expires():
    now = [0.0]
    rows = Rows({"clicks": mixed(30)})
    pages = StationPages(rows, batch=10, ttl_s=60, clock=lambda: now[0])

    await pages.page((by("clicks"),), 0, 5)
    now[0] = 59
    await pages.page((by("clicks"),), 0, 5)
    assert len(rows.calls) == 1

    now[0] = 121
    await pages.page((by("clicks"),), 0, 5)
    assert rows.calls[-1] == ("clicks", 0, 10)
    assert len(rows.calls) == 2


async def test_the_least_recently_read_listing_is_forgotten_first():
    rows = Rows({"a": mixed(10), "b": mixed(10), "c": mixed(10)})
    pages = StationPages(rows, batch=10, max_listings=2)

    await pages.page((by("a"),), 0, 3)
    await pages.page((by("b"),), 0, 3)
    await pages.page((by("a"),), 0, 3)
    await pages.page((by("c"),), 0, 3)
    await pages.page((by("a"),), 0, 3)
    await pages.page((by("b"),), 0, 3)

    assert [order for order, _, _ in rows.calls] == ["a", "b", "c", "b"]


async def test_concurrent_pages_of_one_listing_share_its_fetches():
    release = asyncio.Event()
    calls = []

    async def slow(params, offset, limit):
        calls.append(offset)
        await release.wait()
        return [Station.from_record(row) for row in mixed(30)[offset : offset + limit]]

    pages = StationPages(slow, batch=10)
    first = asyncio.create_task(pages.page((by("clicks"),), 0, 5))
    second = asyncio.create_task(pages.page((by("clicks"),), 0, 5))
    await asyncio.sleep(0)
    release.set()

    (one, _), (two, _) = await asyncio.gather(first, second)

    assert calls == [0]
    assert uuids(one) == uuids(two)


async def test_a_failed_fetch_leaves_the_listing_to_carry_on():
    rows = Rows({"clicks": mixed(30)})
    pages = StationPages(rows, batch=10)
    await pages.page((by("clicks"),), 0, 5)

    rows.fail_next = True
    with pytest.raises(DirectoryUnavailable):
        await pages.page((by("clicks"),), 5, 5)
    stations, _ = await pages.page((by("clicks"),), 5, 5)

    assert uuids(stations) == ["s7", "s9", "s10", "s12", "s13"]
    assert rows.calls[-1] == ("clicks", 10, 10)
