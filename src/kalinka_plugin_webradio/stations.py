from dataclasses import dataclass
from typing import Any, FrozenSet, Mapping, Optional, Tuple

from kalinka_plugin_sdk.datamodel import (
    Album,
    Artist,
    BrowseItem,
    CoverImage,
    Genre,
    Track,
)
from kalinka_plugin_sdk.inputmodule import DirectUrl, TrackSource

from .genres import genres_of
from .ids import COUNTRY_PREFIX, catalog_id, genre_id, track_id

# Codec as radio-browser records it -> (MIME type the renderer decodes by,
# codec shown in Now Playing). OGG is left out: radio-browser files Opus and
# Ogg FLAC streams under it, and the renderer decodes neither.
_FORMATS = {
    "MP3": ("audio/mpeg", "mp3"),
    "AAC": ("audio/aac", "aac"),
    "AAC+": ("audio/aacp", "aac"),
    "FLAC": ("audio/flac", "flac"),
}


def country_label(name: str) -> str:
    """A country's name as shown: radio-browser spells some with a leading
    article ("The Russian Federation")."""
    name = name.strip()
    return name[4:] if name.startswith("The ") else name


@dataclass(frozen=True)
class Station:
    """One station's directory record, reduced to what listing and playing it need."""

    uuid: str
    name: str
    stream_url: str
    codec: str
    bitrate: int
    hls: bool
    ssl_error: bool
    favicon: str
    country: str
    country_code: str
    tags: Tuple[str, ...]

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "Station":
        return cls(
            uuid=str(record.get("stationuuid") or "").strip(),
            name=" ".join(str(record.get("name") or "").split()),
            stream_url=str(record.get("url_resolved") or "").strip(),
            codec=str(record.get("codec") or "").strip().upper(),
            bitrate=_number(record.get("bitrate")),
            hls=bool(_number(record.get("hls"))),
            ssl_error=bool(_number(record.get("ssl_error"))),
            favicon=str(record.get("favicon") or "").strip(),
            country=country_label(str(record.get("country") or "")),
            country_code=str(record.get("countrycode") or "").strip().upper(),
            tags=_tags(record.get("tags")),
        )

    @property
    def unplayable_reason(self) -> Optional[str]:
        """Why the renderer cannot play this stream as the directory last saw
        it, worded for the listener; None when it can."""
        if not self.uuid or not self.name:
            return "This station has no name in the radio directory"
        if not self.stream_url.startswith(("http://", "https://")):
            return f"{self.name} has no stream address"
        if self.hls:
            return f"{self.name} streams over HLS, which Kalinka does not play"
        if self.codec not in _FORMATS:
            return f"{self.name} streams {self.codec or 'an unknown format'}, which Kalinka does not play"
        if self.ssl_error:
            return f"{self.name} has an invalid security certificate"
        return None

    @property
    def playable(self) -> bool:
        return self.unplayable_reason is None

    def has_tags(self, tags: FrozenSet[str]) -> bool:
        return tags.issubset(self.tags)


def station_track(station: Station) -> Track:
    cover = _cover(station.favicon)
    genres = genres_of(station.tags)
    return Track(
        id=track_id(station.uuid),
        title=station.name,
        duration=0,
        performer=_performer(station),
        # Its own id, so nothing groups different stations as one release.
        album=Album(
            id=track_id(station.uuid),
            title=", ".join(genre.label for genre in genres),
            genres=[Genre(id=genre_id(genre.slug), name=genre.label) for genre in genres],
            image=cover,
        ),
        image=cover,
    )


def station_item(station: Station) -> BrowseItem:
    track = station_track(station)
    return BrowseItem(
        id=track.id,
        name=track.title,
        subname=_summary(station) or None,
        can_browse=False,
        can_add=True,
        track=track,
    )


def station_source(station: Station) -> TrackSource:
    """Where the renderer fetches a playable station's stream."""
    mime_type, codec = _FORMATS[station.codec]
    return TrackSource(
        source=DirectUrl(url=station.stream_url),
        format=mime_type,
        audio_codec=codec,
    )


def _performer(station: Station) -> Optional[Artist]:
    # The country stands in for an artist; a catalog id keeps clients from
    # offering to open it as one.
    if not station.country_code:
        return None
    return Artist(
        id=catalog_id(COUNTRY_PREFIX + station.country_code),
        name=station.country or station.country_code,
    )


def _summary(station: Station) -> str:
    quality = (
        f"{station.codec} {station.bitrate} kbps" if station.bitrate else station.codec
    )
    return " · ".join(part for part in (station.country, quality) if part)


def _cover(favicon: str) -> Optional[CoverImage]:
    if not favicon.startswith(("http://", "https://")):
        return None
    return CoverImage(small=favicon, thumbnail=favicon, large=favicon)


def _tags(value: Any) -> Tuple[str, ...]:
    tags = (tag.strip().casefold() for tag in str(value or "").split(","))
    return tuple(dict.fromkeys(tag for tag in tags if tag))


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
