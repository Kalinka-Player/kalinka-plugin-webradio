import asyncio
from contextlib import suppress
from importlib.metadata import version
from typing import Optional

from kalinka_plugin_sdk.plugin import InputModulePlugin, InputPluginContext

from .config_model import WebRadioConfig
from .directory import RadioBrowserClient
from .ids import SOURCE
from .kalinka_plugin_webradio_input_module import WebRadioInputModule

PACKAGE = "kalinka-plugin-webradio"


class KalinkaPluginWebRadio(InputModulePlugin):
    """The Web Radio plugin: owns the directory client and the input module
    reading through it, from ``setup()`` until ``shutdown()``."""

    REQUIRES_SDK = ">=3.23,<4"
    PLUGIN_ID = SOURCE
    CONFIG_MODEL = WebRadioConfig

    def __init__(self):
        self.interface: Optional[WebRadioInputModule] = None
        self._client: Optional[RadioBrowserClient] = None
        self._discovery: Optional[asyncio.Task] = None

    def get_interface(self) -> Optional[WebRadioInputModule]:
        return self.interface

    async def setup(self, context: InputPluginContext) -> None:
        # radio-browser asks every client to name itself as app/version.
        self._client = RadioBrowserClient.create(f"{PACKAGE}/{version(PACKAGE)}")
        self.interface = WebRadioInputModule(self._client)
        self._discovery = asyncio.create_task(self._client.discover())
        context.logger.info("%s set up (SDK %s)", self.PLUGIN_ID, context.sdk_version)

    async def shutdown(self) -> None:
        if self._discovery is not None:
            self._discovery.cancel()
            with suppress(asyncio.CancelledError):
                await self._discovery
        if self.interface is not None:
            await self.interface.aclose()
        if self._client is not None:
            await self._client.aclose()
        self.interface = None
        self._client = None
        self._discovery = None
