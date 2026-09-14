from importlib import metadata

import tracktolib


def test_package_version_matches_distribution():
    assert tracktolib.__version__ == metadata.version("tracktolib")
