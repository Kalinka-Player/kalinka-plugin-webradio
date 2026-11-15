from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class CuratedGenre:
    """A genre offered by name, and the radio-browser tag its stations carry.

    radio-browser has no genres, only free-form tags, and its most used tags
    include "music", "radio" and place names. The genres offered are therefore
    a fixed list of tags that name one.
    """

    tag: str
    label: str

    @property
    def slug(self) -> str:
        return self.tag.replace(" ", "-")


# Ordered by how many stations carried each tag on 2026-11-15.
GENRES = tuple(
    CuratedGenre(tag, label)
    for tag, label in (
        ("pop", "Pop"),
        ("news", "News"),
        ("rock", "Rock"),
        ("talk", "Talk"),
        ("dance", "Dance"),
        ("oldies", "Oldies"),
        ("classical", "Classical"),
        ("jazz", "Jazz"),
        ("80s", "80s"),
        ("electronic", "Electronic"),
        ("christian", "Christian"),
        ("top 40", "Top 40"),
        ("90s", "90s"),
        ("classic rock", "Classic Rock"),
        ("classic hits", "Classic Hits"),
        ("house", "House"),
        ("country", "Country"),
        ("folk", "Folk"),
        ("alternative", "Alternative"),
        ("70s", "70s"),
        ("soul", "Soul"),
        ("indie", "Indie"),
        ("chillout", "Chillout"),
        ("gospel", "Gospel"),
        ("metal", "Metal"),
        ("techno", "Techno"),
        ("ambient", "Ambient"),
        ("sports", "Sports"),
        ("easy listening", "Easy Listening"),
        ("lounge", "Lounge"),
        ("rap", "Rap"),
        ("disco", "Disco"),
        ("blues", "Blues"),
        ("funk", "Funk"),
        ("salsa", "Salsa"),
        ("reggae", "Reggae"),
        ("trance", "Trance"),
        ("smooth jazz", "Smooth Jazz"),
        ("60s", "60s"),
        ("schlager", "Schlager"),
        ("world music", "World Music"),
        ("hip hop", "Hip Hop"),
        ("rnb", "R&B"),
        ("hard rock", "Hard Rock"),
        ("reggaeton", "Reggaeton"),
        ("latin", "Latin"),
        ("punk", "Punk"),
        ("drum and bass", "Drum and Bass"),
    )
)

BY_SLUG = {genre.slug: genre for genre in GENRES}
BY_TAG = {genre.tag: genre for genre in GENRES}


def genres_of(tags: Iterable[str]) -> List[CuratedGenre]:
    """The curated genres among a station's tags, in the station's order."""
    return list(dict.fromkeys(BY_TAG[tag] for tag in tags if tag in BY_TAG))
