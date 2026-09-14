from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tracktolib.s3.minio import download_bucket


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("../outside.txt", id="parent-traversal"),
        pytest.param("nested/../../outside.txt", id="nested-traversal"),
        pytest.param("/absolute.txt", id="absolute"),
        pytest.param("link/outside.txt", id="symlink-directory"),
        pytest.param("file-link", id="symlink-file"),
    ],
)
def test_download_rejects_escape(tmp_path: Path, key: str):
    destination = tmp_path / "downloads"
    destination.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    (destination / "link").symlink_to(tmp_path, target_is_directory=True)
    (destination / "file-link").symlink_to(outside)
    client = Mock()
    client.list_objects.return_value = [SimpleNamespace(object_name=key)]

    with pytest.raises(ValueError, match="escapes output directory"):
        download_bucket(client, "bucket", destination)

    client.get_object.assert_not_called()
    assert outside.read_bytes() == b"keep"


def test_download_nested_object(tmp_path: Path):
    client = Mock()
    client.list_objects.return_value = [SimpleNamespace(object_name="nested/file.txt")]
    client.get_object.return_value.stream.return_value = [b"contents"]

    files = download_bucket(client, "bucket", tmp_path)

    assert files == [tmp_path / "nested/file.txt"]
    assert files[0].read_bytes() == b"contents"
