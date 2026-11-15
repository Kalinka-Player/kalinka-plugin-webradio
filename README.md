# Kalinka Plugin Web Radio

Internet radio stations from the radio-browser.info directory

## Overview

This plugin was generated from the Kalinka Plugin cookiecutter template and provides a input_module implementation for the Kalinka Music Player system.

## Plugin Information

- **Plugin Name**: Web Radio
- **Plugin ID**: `webradio`
- **Python package**: `kalinka_plugin_webradio`
- **Plugin Type**: input_module
- **Author**: Dmitry Savin <envelsavinds@gmail.com>
- **License**: GPL-3.0-or-later
- **Version**: 0.1.0

## Plugin Structure

```
kalinka-plugin-webradio/
├── README.md                    # This file
├── pyproject.toml              # Python package configuration
├── src/
│   └── kalinka_plugin_webradio/
│       ├── __init__.py         # Package initialization
│       ├── _version.py         # Version information
│       ├── config_model.py     # Plugin configuration schema
│       ├── module_setup.py     # Plugin entry point and setup
│       └── kalinka_plugin_webradio_input_module.py  # Input module implementation
├── debian/                     # Debian packaging files
│   ├── control.in             # Package metadata template
│   ├── prerm                 # Pre-removal script
│   ├── rules                 # Build rules
│   └── triggers              # Restarts Kalinka to pick up the wheel
├── scripts/
│   ├── build_wheel.sh        # Build Python wheel
│   └── build_deb.sh          # Build Debian package
└── tests/
    └── test_smoke.py         # Basic smoke tests
```

## Key Components

### 1. Configuration Model (`config_model.py`)
Defines the configuration schema using Pydantic models that inherit from `ModuleConfig`:

```python
from pydantic import Field
from kalinka_plugin_sdk.module_config import ModuleConfig

class WebRadioConfig(ModuleConfig):
    name: str = Field(default="webradio", frozen=True, exclude=True)
    enabled: bool = Field(
        default=False,
        title="Module enabled",
        json_schema_extra={"importance": "simple"},
    )
    # Add your plugin-specific configuration fields here
```

### 2. Module Setup (`module_setup.py`)
The main entry point class that Kalinka instantiates for your plugin:

```python
from typing import Optional

from kalinka_plugin_sdk.inputmodule import InputModule
from kalinka_plugin_sdk.plugin import InputModulePlugin, InputPluginContext

class KalinkaPluginWebRadio(InputModulePlugin):
    REQUIRES_SDK = ">=3.22,<4"
    PLUGIN_ID = "webradio"
    CONFIG_MODEL = WebRadioConfig

    def __init__(self):
        self.interface = None

    def get_interface(self) -> Optional[InputModule]:
        return self.interface

    async def setup(self, context: InputPluginContext) -> None:
        """Entry point used by Kalinka"""
        self.interface = WebRadioInputModule(context.config)
        context.logger.info("%s set up (SDK %s)", self.PLUGIN_ID, context.sdk_version)

    async def shutdown(self) -> None:
        """Clean up resources"""
        self.interface = None
```
### 3. Input Module Implementation (`kalinka_plugin_webradio_input_module.py`)
Implements the `InputModule` interface with all required methods for music streaming functionality:

- `module_name()` - Return display name of the module
- `search()` - Search for tracks, albums, artists
- `browse()` - Browse music catalogs
- `get_track_info()` - Get detailed track information
- `get_track_source()` - Resolve where a track plays from, given its id
- `list_favorite()` - List user favorites
- `get_favorite_ids()` - Get all favorite IDs
- `add_to_favorite()` - Add items to favorites
- `remove_from_favorite()` - Remove items from favorites
- `list_filter_values()` - List the values of one catalog filter field
- `get()` - Get specific entity by ID
- `playlist_user_list()` - List user playlists
- `playlist_create()` - Create new playlist
- `playlist_update()` - Update playlist metadata
- `playlist_delete()` - Delete playlist
- `playlist_add_tracks()` - Add tracks to playlist
- `playlist_remove_tracks()` - Remove tracks from playlist
- `get_resource_path()` - Get cover art resource URLs

## Building

### Prerequisites
- Python 3.11+
- `kalinka-plugin-sdk` package
- Build tools: `python3-build`, `setuptools`, `setuptools-scm`, `wheel`
- For Debian packaging: `dpkg-dev`
- Git repository with proper tags for version detection

### Version Management
This plugin uses **setuptools_scm** for automatic version detection:
- **Release builds**: Tag your release with `kalinka-plugin-webradio-v1.2.3` format
- **Development builds**: setuptools_scm automatically generates dev versions like `1.2.4.dev0+gc1e6070.d20250928`
- **Clean releases**: Commit all changes and tag for clean release versions

### Build Python Wheel
```bash
./scripts/build_wheel.sh
```
The script automatically:
- Detects version from git tags using setuptools_scm
- Generates `_version.py` with the detected version
- Builds the wheel with proper version metadata

### Build Debian Package
```bash
./scripts/build_deb.sh
```
The script automatically:
- Builds the wheel first to detect the version
- Generates Debian control files with the correct version
- Creates a `.deb` package ready for installation

The Debian package will:
1. Install the wheel to `/opt/kalinka/wheels/`
2. Activate the `kalinka-server-restart` trigger, so Kalinka restarts and its startup installs the wheel into Kalinka's venv

## Installation

### From Wheel
```bash
# Install into Kalinka's venv
/opt/kalinka/venv/bin/pip install dist/kalinka_plugin_webradio-*.whl
```

### From Debian Package
```bash
sudo dpkg -i kalinka-plugin-webradio_*_all.deb
```

## Configuration

After installation, the plugin appears in Kalinka's configuration interface where you can:
- Enable/disable the plugin
- Configure plugin-specific settings
- Test the plugin functionality

## Development

### Testing
Run the included smoke tests:

```bash
pytest tests/
```

### Logging
`context.logger` is a standard `logging.Logger` named after the plugin. Pass values as
%-style arguments; it takes no keyword fields:

```python
context.logger.info("Found %d albums for %s", len(albums), query)
```

### Error Handling
Implement proper error handling for network/API failures and provide meaningful error messages.

## License

This plugin is released under the GPL-3.0-or-later license.

## Support

For questions about this plugin or plugin development in general:
- Check the Kalinka Plugin SDK documentation
- Review other plugins in the ecosystem
- Consult the main Kalinka project documentation
