import httpx
import pytest

from kalinka_plugin_webradio.directory import (
    DISCOVERY_HOST,
    DirectoryUnavailable,
    Mirrors,
    RadioBrowserClient,
)


class Server:
    """Answers requests by host, recording each one."""

    def __init__(self, **answers):
        self.answers = answers
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers[request.url.host.replace(".", "_").replace("-", "_")]
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return answer(request)
        return answer

    @property
    def hosts(self):
        return [request.url.host for request in self.requests]


def client_for(server, hosts=("a.example", "b.example")):
    return RadioBrowserClient(
        httpx.AsyncClient(transport=httpx.MockTransport(server)),
        Mirrors(hosts, shuffle=lambda hosts: hosts.reverse()),
    )


def ok(body=()):
    return httpx.Response(200, json=list(body))


def test_mirrors_start_with_the_discovery_name():
    assert Mirrors().hosts == [DISCOVERY_HOST]


def test_mirrors_take_new_servers_in_random_order_once_each():
    mirrors = Mirrors(shuffle=lambda hosts: hosts.reverse())

    mirrors.replace(["de1.example", "", "at1.example", "de1.example"])

    assert mirrors.hosts == ["at1.example", "de1.example"]


def test_mirrors_keep_their_servers_when_given_none():
    mirrors = Mirrors(["de1.example"])

    mirrors.replace([])

    assert mirrors.hosts == ["de1.example"]


def test_a_failed_server_is_tried_last():
    mirrors = Mirrors(["a", "b", "c"])

    mirrors.demote("a")
    mirrors.demote("unknown")

    assert mirrors.hosts == ["b", "c", "a"]


async def test_the_client_names_the_app_it_belongs_to(monkeypatch):
    seen = []

    async def answer(self, request):
        seen.append(request)
        return httpx.Response(200, json=[])

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", answer)
    client = RadioBrowserClient.create("kalinka-plugin-webradio/1.2.3")

    await client.countries()
    await client.aclose()

    assert seen[0].headers["User-Agent"] == "kalinka-plugin-webradio/1.2.3"
    assert seen[0].url.host == DISCOVERY_HOST


async def test_discovery_spreads_requests_over_the_listed_servers():
    server = Server(
        all_api_radio_browser_info=ok(
            [
                {"ip": "1.2.3.4", "name": "de1.example"},
                {"ip": "::1", "name": "de1.example"},
                {"ip": "5.6.7.8", "name": "fi1.example"},
            ]
        ),
        fi1_example=ok(),
    )
    client = client_for(server, hosts=(DISCOVERY_HOST,))

    await client.discover()
    await client.countries()

    assert server.requests[0].url.path == "/json/servers"
    assert server.hosts[1] == "fi1.example"


async def test_failed_discovery_keeps_asking_the_discovery_name():
    server = Server(all_api_radio_browser_info=httpx.ConnectError("no route"))
    client = client_for(server, hosts=(DISCOVERY_HOST,))

    await client.discover()
    with pytest.raises(DirectoryUnavailable):
        await client.countries()

    assert server.hosts == [DISCOVERY_HOST, DISCOVERY_HOST]


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("refused"),
        httpx.Response(503),
        httpx.Response(200, text="<html>maintenance</html>"),
    ],
)
async def test_a_failing_server_hands_over_to_the_next(failure):
    server = Server(a_example=failure, b_example=ok([{"name": "x"}]))
    client = client_for(server)

    assert await client.countries() == [{"name": "x"}]
    await client.countries()

    assert server.hosts == ["a.example", "b.example", "b.example"]


async def test_a_slow_server_is_not_retried_elsewhere():
    server = Server(a_example=httpx.ReadTimeout("slow"), b_example=ok())
    client = client_for(server)

    with pytest.raises(DirectoryUnavailable):
        await client.countries()

    assert server.hosts == ["a.example"]


async def test_a_rejected_request_is_raised_as_it_is():
    server = Server(a_example=httpx.Response(400), b_example=ok())
    client = client_for(server)

    with pytest.raises(httpx.HTTPStatusError):
        await client.countries()

    assert server.hosts == ["a.example"]


async def test_a_call_asks_at_most_two_servers():
    down = httpx.ConnectError("refused")
    server = Server(a_example=down, b_example=down, c_example=down)
    client = client_for(server, hosts=("a.example", "b.example", "c.example"))

    with pytest.raises(DirectoryUnavailable):
        await client.countries()

    assert server.hosts == ["a.example", "b.example"]


async def test_the_endpoints_ask_for_what_they_name():
    server = Server(a_example=ok())
    client = client_for(server, hosts=("a.example",))

    await client.search_stations({"order": "votes", "limit": 5})
    await client.stations_by_uuid(["u1", "u2"])
    await client.tags({"limit": 3}, name_contains="drum & bass")
    await client.countries()
    await client.languages()
    await client.count_click("u1")

    assert [(r.url.path, dict(r.url.params)) for r in server.requests] == [
        ("/json/stations/search", {"order": "votes", "limit": "5"}),
        ("/json/stations/byuuid", {"uuids": "u1,u2"}),
        ("/json/tags/drum & bass", {"limit": "3"}),
        ("/json/countries", {"order": "stationcount", "reverse": "true", "hidebroken": "true"}),
        ("/json/languages", {"order": "stationcount", "reverse": "true", "hidebroken": "true"}),
        ("/json/url/u1", {}),
    ]
    assert server.requests[2].url.raw_path.startswith(b"/json/tags/drum%20%26%20bass")
