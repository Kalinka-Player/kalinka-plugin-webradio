from kalinka_plugin_sdk.datamodel import EntityId, EntityType

SOURCE = "webradio"
DISPLAY_NAME = "Web Radio"

ROOT = "root"
GENRE_PREFIX = "genre-"
COUNTRY_PREFIX = "country-"
LANGUAGE_PREFIX = "language-"


def track_id(station_uuid: str) -> EntityId:
    return EntityId(id=station_uuid, type=EntityType.TRACK, source=SOURCE)


def catalog_id(slug: str) -> EntityId:
    return EntityId(id=slug, type=EntityType.CATALOG, source=SOURCE)


def genre_id(slug: str) -> EntityId:
    return EntityId(id=slug, type=EntityType.GENRE, source=SOURCE)
