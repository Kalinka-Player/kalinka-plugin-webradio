"""
Pytest smoke tests for kalinka-plugin-webradio
"""

import asyncio
import inspect
import logging
import pytest
from importlib.metadata import entry_points
from unittest.mock import Mock

from kalinka_plugin_sdk import __version__ as sdk_version
from kalinka_plugin_sdk.api import EventListener
from kalinka_plugin_sdk.api import PlayQueueController
from kalinka_plugin_sdk.inputmodule import InputModule
from kalinka_plugin_sdk.plugin import InputPluginContext, cast_plugin_interface

from conftest import FakeDirectory


@pytest.mark.smoke
def test_entry_point_visible():
    """Test that the plugin entry point is discoverable"""
    eps = entry_points(group="kalinka.plugins")
    # In editable mode, ensure it's discoverable after `pip install -e .`
    assert any(
        ep.name == "kalinka_plugin_webradio" for ep in eps
    ), "Plugin entry point 'kalinka_plugin_webradio' not found in kalinka.plugins group"

    for ep in eps:
        if ep.name == "kalinka_plugin_webradio":
            plugin = ep.load()
            assert plugin is not None
            assert hasattr(plugin, "PLUGIN_ID")
            assert plugin.PLUGIN_ID == "webradio"
            assert hasattr(plugin, "REQUIRES_SDK")
            assert hasattr(plugin, "CONFIG_MODEL")
            obj = plugin()
            assert hasattr(obj, "setup")
            assert hasattr(obj, "shutdown")

            config = plugin.CONFIG_MODEL()
            assert config is not None

            break


@pytest.mark.smoke
def test_imports():
    """Test that all plugin modules can be imported"""
    # These imports should not raise ImportError
    from kalinka_plugin_webradio.config_model import WebRadioConfig
    from kalinka_plugin_webradio.module_setup import KalinkaPluginWebRadio
    from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import WebRadioInputModule

    # Verify the imported classes/functions exist
    assert WebRadioConfig is not None
    assert KalinkaPluginWebRadio is not None
    assert WebRadioInputModule is not None


def _context(config):
    """A context like the one the server hands the plugin's setup()"""
    return InputPluginContext(
        logger=logging.getLogger("webradio"),
        plugin_id="webradio",
        sdk_version=sdk_version,
        config=config,
        listener=Mock(spec=EventListener),
        playqueue=Mock(spec=PlayQueueController),
    )


@pytest.mark.smoke
def test_setup_and_shutdown_as_the_server_runs_them(caplog):
    """The server awaits setup() and shutdown() and logs through a standard logging.Logger"""
    from kalinka_plugin_webradio.module_setup import KalinkaPluginWebRadio

    # At DEBUG every log call is formatted, so a malformed one fails here
    caplog.set_level(logging.DEBUG, logger="webradio")
    plugin = KalinkaPluginWebRadio()
    context = _context(plugin.CONFIG_MODEL(enabled=True))

    async def run():
        await plugin.setup(context)
        interface = cast_plugin_interface(plugin)
        await plugin.shutdown()
        return interface

    interface = asyncio.run(run())

    assert isinstance(interface, InputModule)


@pytest.mark.smoke
def test_config_model_instantiation():
    """Test that config model can be instantiated with correct defaults"""
    from kalinka_plugin_webradio.config_model import WebRadioConfig
    from kalinka_plugin_webradio.module_setup import KalinkaPluginWebRadio

    config = WebRadioConfig()

    # The settings page addresses the config by its name, the server by PLUGIN_ID
    assert config.name == KalinkaPluginWebRadio.PLUGIN_ID
    # Check that the config name title matches plugin display name
    assert config.__class__.model_fields["name"].title == "Web Radio"
    # Enabled field should be boolean and should have a default value
    assert isinstance(config.enabled, bool)
    # Without the simple tag the enable toggle drops off the simple settings page
    assert config.__class__.model_fields["enabled"].json_schema_extra["importance"] == "simple"


def test_config_model_validation():
    """Test that config model validation works"""
    from kalinka_plugin_webradio.config_model import WebRadioConfig

    # Test with valid data
    config = WebRadioConfig(enabled=True)
    assert config.enabled is True
    assert config.name == "webradio"

    # Test with custom name (frozen=True prevents modification after creation, not during init)
    config_with_name = WebRadioConfig(name="different_name", enabled=True)
    assert config_with_name.name == "different_name"
    assert config_with_name.enabled is True


def test_config_model_frozen_field():
    """Test that name field is frozen after creation"""
    from kalinka_plugin_webradio.config_model import WebRadioConfig
    import pytest

    config = WebRadioConfig()

    # Attempting to modify the frozen 'name' field should raise an exception
    with pytest.raises(Exception):  # Should raise ValidationError or similar
        config.name = "modified_name"


@pytest.mark.smoke
def test_input_module_instantiation():
    """Test that input module can be instantiated"""
    from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import WebRadioInputModule

    module = WebRadioInputModule(FakeDirectory())

    assert module is not None


@pytest.mark.smoke
def test_input_module_name():
    """Test that input module returns correct name"""
    from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import WebRadioInputModule

    module = WebRadioInputModule(FakeDirectory())

    # Entity ids name their source by it, so it is the plugin id, not the display name
    assert module.module_name() == "webradio"
    assert module.display_name() == "Web Radio"


def test_module_setup_constants():
    """Test that module setup has required constants"""
    from kalinka_plugin_webradio.module_setup import KalinkaPluginWebRadio

    plugin_class = KalinkaPluginWebRadio
    assert plugin_class.REQUIRES_SDK == ">=3.23,<4"
    assert plugin_class.PLUGIN_ID == "webradio"
    assert plugin_class.CONFIG_MODEL is not None

    # Test instantiation
    plugin_instance = plugin_class()
    assert hasattr(plugin_instance, "setup")
    assert hasattr(plugin_instance, "shutdown")
    assert callable(plugin_instance.setup)
    assert callable(plugin_instance.shutdown)


@pytest.mark.parametrize(
    "method_name",
    [
        "module_name",
        "search",
        "browse",
        "get_track_info",
        "get_track_source",
        "list_favorite",
        "get_favorite_ids",
        "add_to_favorite",
        "remove_from_favorite",
        "list_filter_values",
        "get",
        "playlist_user_list",
        "playlist_create",
        "playlist_update",
        "playlist_delete",
        "playlist_add_tracks",
        "playlist_remove_tracks",
        "get_resource_path",
    ],
)
def test_input_module_has_required_methods(method_name):
    """Test that input module has all required interface methods, async where the SDK's are"""
    from kalinka_plugin_webradio.kalinka_plugin_webradio_input_module import WebRadioInputModule

    module = WebRadioInputModule(FakeDirectory())

    assert hasattr(module, method_name), f"Missing required method: {method_name}"
    assert callable(
        getattr(module, method_name)
    ), f"Method {method_name} is not callable"
    assert inspect.iscoroutinefunction(
        getattr(module, method_name)
    ) == inspect.iscoroutinefunction(
        getattr(InputModule, method_name)
    ), f"Method {method_name} must be async exactly when InputModule's is"
