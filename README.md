# Web Radio for Kalinka Player

Web Radio adds internet radio to [Kalinka Player](https://github.com/Kalinka-Player/KalinkaPlayer). It lists stations from [radio-browser.info](https://www.radio-browser.info), a free, community-maintained directory of more than 50,000 stations, and plays them through your Kalinka renderer. No account is needed.

## Install

Web Radio needs Kalinka Player 5.19.0 or newer on Debian 13 or Ubuntu 24.04, on ARM64 or x86-64. Download the `.deb` and `SHA256SUMS` from the [latest release](https://github.com/Kalinka-Player/kalinka-plugin-webradio/releases/latest), then on the Kalinka Player server run:

```sh
sha256sum -c SHA256SUMS --ignore-missing
sudo apt install ./kalinka-plugin-webradio_<version>_all.deb
```

Kalinka Player restarts to pick up the plugin. Web Radio is enabled straight away and appears among your sources.

## Finding stations

Popular, Trending, Top Voted and High Quality list stations by how many people played them in the last day, how fast that is rising, listener votes, and stream quality. High Quality starts with lossless FLAC streams and goes on to stations streaming at 256 kbps or more. Genres, Countries and Languages each lead to a list of stations, the busiest first.

Every list can be searched by station name and narrowed by genre. The genre filter offers a list of common genres, and typing in it finds any other tag the directory uses, such as "synthwave". Choosing several genres shows stations that carry all of them. Stations also turn up in Kalinka's search.

Web Radio keeps no favorites or playlists of its own. Add stations to a Kalinka collection instead.

## Limitations

Only stations whose streams the renderer can decode are listed: MP3, AAC and FLAC. Stations that stream over HLS, or in Opus or Ogg, are left out.

A station plays live, so it has no running time and cannot be skipped through. If the stream connection drops, or playback moves to another renderer, the station does not resume; play it again. The title of the song a station is playing is not shown.

Each time a station starts, Web Radio tells radio-browser.info, as the directory asks its apps to; that count is what its popularity lists are built from. Station information comes from the directory's volunteers and can be out of date.

## Development

```sh
git clone https://github.com/Kalinka-Player/kalinka-plugin-webradio.git
cd kalinka-plugin-webradio
python3 -m venv .venv
. .venv/bin/activate
python -m pip install \
  "kalinka-plugin-sdk @ git+https://github.com/Kalinka-Player/KalinkaPlayer@5986b63b652e45e32db36ad6d968f88604e4280a#subdirectory=packages/kalinka-plugin-sdk" \
  -e '.[dev]'
python -m pytest
./scripts/build_deb.sh
```

Versions come from `kalinka-plugin-webradio-vX.Y.Z` tags. See [CONTRIBUTING.md](CONTRIBUTING.md) for releasing.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE). Web Radio is not affiliated with radio-browser.info or with the stations it lists.
