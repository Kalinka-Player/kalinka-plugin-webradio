# Contributing

## AI-assisted development

This plugin is built with **substantial AI assistance**, working from maintainer-defined requirements. Technical direction, review, testing and acceptance of changes remain the responsibility of the maintainer.

AI use is disclosed at the repository level rather than on individual commits, so commit messages and pull requests carry no co-authorship trailers or generated-with footers.

The level of assistance differs across the project; each Kalinka repository states its own in its `CONTRIBUTING.md`.

If AI assistance played a significant part in a pull request you send, a note in the description is welcome — it helps direct review.

## Sending a change

Set up the development environment as the README describes. Run `python -m pytest` and `python -m flake8 --select=F src tests scripts/check_package.py` before sending a change. Tests must not contact radio-browser.info; the test suite fails any test that tries.

Keep the SDK and server requirements consistent across `pyproject.toml`, `module_setup.py`, `debian/control.in`, `scripts/check_package.py`, the README and the plugin hub entry.

## Releasing

Add the version's notes to `CHANGELOG.md`, commit, and push a `kalinka-plugin-webradio-vX.Y.Z` tag. Release CI tests on Python 3.11 and 3.13, builds and tests the package on Debian 13 and Ubuntu 24.04 for ARM64 and x86-64, and publishes one architecture-independent `.deb` with its SHA-256 checksum. Published assets are never replaced; changed bytes need a new version. Then add the release's URL, digest, size and source commit to [kalinka-plugins](https://github.com/Kalinka-Player/kalinka-plugins).

## License

GPL-3.0-or-later; see `LICENSE`.
