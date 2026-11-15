from pydantic import Field
from kalinka_plugin_sdk.module_config import ModuleConfig


class WebRadioConfig(ModuleConfig):
    name: str = Field(
        default="webradio",
        title="Web Radio",
        frozen=True,
        exclude=True,
    )
    enabled: bool = Field(
        default=False,
        title="Module enabled",
        json_schema_extra={"importance": "simple"},
    )
