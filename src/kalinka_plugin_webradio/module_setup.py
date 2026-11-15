from typing import Optional

from kalinka_plugin_sdk.inputmodule import InputModule
from kalinka_plugin_sdk.plugin import InputModulePlugin, InputPluginContext

from .config_model import WebRadioConfig
from .kalinka_plugin_webradio_input_module import WebRadioInputModule


class KalinkaPluginWebRadio(InputModulePlugin):
    """
    Kalinka plugin class. This is the main entry point for the plugin.
    """
    REQUIRES_SDK = ">=3.22,<4"
    PLUGIN_ID = "webradio"
    CONFIG_MODEL = WebRadioConfig

    def __init__(self):
        self.interface = None

    def get_interface(self) -> Optional[InputModule]:
        return self.interface

    async def setup(self, context: InputPluginContext) -> None:
        """
        Entry point used by Kalinka. Register subscriptions, timers, etc.
        This function must not block.
        """
        self.interface = WebRadioInputModule(context.config)
        context.logger.info("%s set up (SDK %s)", self.PLUGIN_ID, context.sdk_version)

    async def shutdown(self) -> None:
        """
        Entry point used by Kalinka when unloading the plugin. Clean up resources here.
        Should not raise exceptions - log errors instead.
        """
        self.interface = None
