import asyncio
import logging
from importlib.metadata import version
from unittest.mock import Mock
from xml.etree import ElementTree

from kalinka_plugin_sdk import __version__ as sdk_version
from kalinka_plugin_sdk.api import EventListener, PlayQueueController
from kalinka_plugin_sdk.plugin import InputPluginContext

from conftest import FakeDirectory
from kalinka_plugin_webradio.config_model import WebRadioConfig
from kalinka_plugin_webradio.directory import RadioBrowserClient
from kalinka_plugin_webradio.module_setup import KalinkaPluginWebRadio


class SlowDirectory(FakeDirectory):
    def __init__(self):
        super().__init__()
        self.discovery_cancelled = False

    async def discover(self):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.discovery_cancelled = True
            raise


def context():
    return InputPluginContext(
        logger=logging.getLogger("webradio"),
        plugin_id="webradio",
        sdk_version=sdk_version,
        config=WebRadioConfig(),
        listener=Mock(spec=EventListener),
        playqueue=Mock(spec=PlayQueueController),
    )


async def test_shutdown_stops_discovery_and_closes_the_directory(monkeypatch):
    directory = SlowDirectory()
    agents = []

    def create(user_agent):
        agents.append(user_agent)
        return directory

    monkeypatch.setattr(RadioBrowserClient, "create", staticmethod(create))
    plugin = KalinkaPluginWebRadio()

    await plugin.setup(context())
    await asyncio.sleep(0)
    assert plugin.get_interface() is not None
    await plugin.shutdown()

    assert agents == [f"kalinka-plugin-webradio/{version('kalinka-plugin-webradio')}"]
    assert directory.discovery_cancelled
    assert directory.closed
    assert plugin.get_interface() is None


async def test_shutdown_before_setup_does_nothing():
    await KalinkaPluginWebRadio().shutdown()


def test_the_packaged_icon_is_one_the_server_serves():
    icons = WebRadioConfig.__module_icon_files__
    data = icons.standard.read_bytes()
    root = ElementTree.fromstring(data)

    assert icons.small == icons.standard
    assert icons.monochrome
    assert len(data) <= 256 * 1024
    assert b"<!DOCTYPE" not in data.upper()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 24 24"
