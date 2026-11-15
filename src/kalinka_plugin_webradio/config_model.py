from pathlib import Path
from typing import ClassVar

from pydantic import Field

from kalinka_plugin_sdk import ModuleIconFiles
from kalinka_plugin_sdk.module_config import ModuleConfig

from .ids import DISPLAY_NAME, SOURCE

_ICON = Path(__file__).with_name("icons") / "webradio.svg"


class WebRadioConfig(ModuleConfig):
    __module_icon__: ClassVar[str] = "music_note_outlined"
    __module_icon_color__: ClassVar[str] = "#C4501B"
    __module_icon_files__: ClassVar[ModuleIconFiles] = ModuleIconFiles(
        small=_ICON, standard=_ICON, monochrome=True
    )

    name: str = Field(
        default=SOURCE,
        title=DISPLAY_NAME,
        description="Internet radio stations from the radio-browser.info directory.",
        frozen=True,
        exclude=True,
    )
    enabled: bool = Field(
        default=True,
        title="Enable Web Radio",
        json_schema_extra={"importance": "simple"},
    )
