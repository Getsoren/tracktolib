import os
import time
from pathlib import Path

import niquests
import pytest

from tests.s3.conftest import get_botocore_client

S3_BUCKET = "test-niquests"


@pytest.fixture(scope="function")
def s3_bucket():
    return S3_BUCKET


@pytest.mark.usefixtures("setup_bucket")
class TestS3Session:
    async def test_session_put_get_delete(self, s3_bucket, s3_client):
        """Test S3Session wrapper class."""
        # Put object
        test_data = b"Hello from S3Session!"
        resp = await s3_client.put_object(s3_bucket, "session-test/hello.txt", test_data, acl=None)
        assert resp.status_code == 200

        # Get object
        result = await s3_client.get_object(s3_bucket, "session-test/hello.txt")
        assert result == test_data

        # List files
        files = [f async for f in s3_client.list_files(s3_bucket, "session-test/")]
        assert len(files) == 1
        assert files[0].get("Key") == "session-test/hello.txt"

        # Delete object
        resp = await s3_client.delete_object(s3_bucket, "session-test/hello.txt")
        assert resp.status_code == 204

    async def test_session_streaming_small_file(self, s3_bucket, s3_client):
        """Test S3Session streaming upload with small file."""
        test_data = b"Small streaming content"

        async def data_stream():
            yield test_data

        await s3_client.file_upload(
            s3_bucket,
            "session-test/stream.txt",
            data_stream(),
            content_length=len(test_data),
        )

        result = await s3_client.get_object(s3_bucket, "session-test/stream.txt")
        assert result == test_data

    @pytest.mark.parametrize(
        "acl",
        [
            pytest.param(None, id="acl_none"),
            pytest.param("private", id="acl_private"),
            pytest.param("public-read", id="acl_public_read"),
        ],
    )
    async def test_session_put_object_with_acl(self, s3_bucket, s3_client, acl):
        """Test S3Session.put_object with different ACL values."""
        key = f"session-test/acl-{acl}.txt"
        test_data = b"Hello with ACL from S3Session!"
        resp = await s3_client.put_object(s3_bucket, key, test_data, acl=acl)
        assert resp.status_code == 200

        result = await s3_client.get_object(s3_bucket, key)
        assert result == test_data


@pytest.mark.usefixtures("setup_bucket")
class TestS3NiquestsBasicOperations:
    @pytest.mark.parametrize(
        ("operation", "key", "data", "expected_status", "expected_content"),
        [
            pytest.param("put", "test/hello.txt", b"Hello, World!", 200, None, id="put_object"),
            pytest.param("get", "test/hello.txt", b"Hello, World!", None, b"Hello, World!", id="get_object"),
            pytest.param("get_nonexistent", "test/nonexistent.txt", None, None, None, id="get_nonexistent"),
            pytest.param("delete", "test/hello.txt", b"Hello, World!", 204, None, id="delete_object"),
        ],
    )
    async def test_basic_operations(
        self, s3_bucket, s3_backend, operation, key, data, expected_status, expected_content
    ):
        from tracktolib.s3.niquests import s3_delete_object, s3_get_object, s3_put_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                if operation == "put":
                    resp = await s3_put_object(s3, client, s3_bucket, key, data, acl=None)
                    assert resp.status_code == expected_status
                elif operation == "get":
                    await s3_put_object(s3, client, s3_bucket, key, data, acl=None)
                    result = await s3_get_object(s3, client, s3_bucket, key)
                    assert result == expected_content
                elif operation == "get_nonexistent":
                    result = await s3_get_object(s3, client, s3_bucket, key)
                    assert result is None
                elif operation == "delete":
                    await s3_put_object(s3, client, s3_bucket, key, data, acl=None)
                    resp = await s3_delete_object(s3, client, s3_bucket, key)
                    assert resp.status_code == expected_status
                    result = await s3_get_object(s3, client, s3_bucket, key)
                    assert result is None

    @pytest.mark.parametrize(
        "acl",
        [
            pytest.param(None, id="acl_none"),
            pytest.param("private", id="acl_private"),
            pytest.param("public-read", id="acl_public_read"),
        ],
    )
    async def test_put_object_with_acl(self, s3_bucket, s3_backend, acl):
        """Test put_object with different ACL values."""
        from tracktolib.s3.niquests import s3_get_object, s3_put_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                key = f"test/acl-test-{acl}.txt"
                data = b"Hello with ACL!"
                resp = await s3_put_object(s3, client, s3_bucket, key, data, acl=acl)
                assert resp.status_code == 200

                # Verify content was uploaded correctly
                result = await s3_get_object(s3, client, s3_bucket, key)
                assert result == data

    async def test_list_files(self, s3_bucket, s3_backend):
        """Test listing files with a prefix."""
        from tracktolib.s3.niquests import s3_list_files, s3_put_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                # Create some test files (acl=None to avoid ACL issues)
                await s3_put_object(s3, client, s3_bucket, "prefix/file1.txt", b"content1", acl=None)
                await s3_put_object(s3, client, s3_bucket, "prefix/file2.txt", b"content2", acl=None)
                await s3_put_object(s3, client, s3_bucket, "other/file3.txt", b"content3", acl=None)

                # List with prefix (async iterator)
                files = [f async for f in s3_list_files(s3, client, s3_bucket, "prefix/")]
                keys = [k for f in files if (k := f.get("Key"))]
                assert sorted(keys) == ["prefix/file1.txt", "prefix/file2.txt"]

                # Verify S3Object typing - Size should be int
                for f in files:
                    assert isinstance(f.get("Size"), int)

    @pytest.mark.parametrize(
        ("search_query", "max_items", "page_size", "expected_count", "expected_keys"),
        [
            pytest.param(None, 2, None, 2, None, id="max_items"),
            pytest.param(None, None, 1, 3, None, id="page_size"),
            pytest.param(
                "Contents[?Size > `50`][]",
                None,
                None,
                2,
                ["filter/large.txt", "filter/medium.txt"],
                id="search_query",
            ),
        ],
    )
    async def test_list_files_with_filters(
        self, s3_bucket, s3_backend, search_query, max_items, page_size, expected_count, expected_keys
    ):
        """Test listing files with max_items, page_size, and search_query."""
        from tracktolib.s3.niquests import s3_list_files, s3_put_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                # Create test files with different sizes
                await s3_put_object(s3, client, s3_bucket, "filter/small.txt", b"x", acl=None)
                await s3_put_object(s3, client, s3_bucket, "filter/medium.txt", b"x" * 100, acl=None)
                await s3_put_object(s3, client, s3_bucket, "filter/large.txt", b"x" * 200, acl=None)

                files = [
                    f
                    async for f in s3_list_files(
                        s3,
                        client,
                        s3_bucket,
                        "filter/",
                        search_query=search_query,
                        max_items=max_items,
                        page_size=page_size,
                    )
                ]
                assert len(files) == expected_count
                if expected_keys is not None:
                    keys = sorted([k for f in files if (k := f.get("Key"))])
                    assert keys == expected_keys


@pytest.mark.usefixtures("setup_bucket")
class TestS3StreamingUpload:
    async def test_multipart_upload_manual(self, s3_bucket, s3_backend):
        """Test multipart upload with manual part uploads."""
        from tracktolib.s3.niquests import s3_get_object, s3_multipart_upload

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                key = "test/multipart-manual.bin"
                # Minimum part size is 5MB
                part1 = b"A" * (5 * 1024 * 1024)  # 5MB
                part2 = b"B" * (5 * 1024 * 1024)  # 5MB

                async with s3_multipart_upload(s3, client, s3_bucket, key) as mpart:
                    await mpart.fetch_create()
                    await mpart.upload_part(part1)
                    await mpart.upload_part(part2)

                # Verify uploaded content
                result = await s3_get_object(s3, client, s3_bucket, key)
                assert result == part1 + part2

    async def test_multipart_upload_abort(self, s3_bucket, s3_backend):
        """Test aborting a multipart upload."""
        from tracktolib.s3.niquests import s3_get_object, s3_multipart_upload

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                key = "test/multipart-abort.bin"
                part1 = b"A" * (5 * 1024 * 1024)

                async with s3_multipart_upload(s3, client, s3_bucket, key) as mpart:
                    await mpart.fetch_create()
                    await mpart.upload_part(part1)
                    await mpart.fetch_abort()

                # Verify file doesn't exist (upload was aborted)
                result = await s3_get_object(s3, client, s3_bucket, key)
                assert result is None

    @pytest.mark.parametrize(
        ("key", "data_size", "chunk_size", "content_length"),
        [
            pytest.param("test/small-stream.txt", 18, 18, 18, id="small_file"),
            pytest.param("test/large-stream.bin", 12 * 1024 * 1024, 3 * 1024 * 1024, None, id="large_file"),
            pytest.param("test/single-part.bin", 4 * 1024 * 1024, 1024 * 1024, None, id="single_part"),
        ],
    )
    async def test_s3_file_upload(self, s3_bucket, s3_backend, key, data_size, chunk_size, content_length):
        from tracktolib.s3.niquests import s3_file_upload, s3_get_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                test_data = b"X" * data_size

                async def data_stream():
                    for i in range(0, len(test_data), chunk_size):
                        yield test_data[i : i + chunk_size]

                upload_progress_called = False

                def on_upload(req: niquests.PreparedRequest):
                    nonlocal upload_progress_called
                    if req.upload_progress is not None:
                        upload_progress_called = True

                await s3_file_upload(
                    s3,
                    client,
                    s3_bucket,
                    key,
                    data_stream(),
                    min_part_size=5 * 1024 * 1024,
                    on_upload=on_upload,
                    content_length=content_length,
                )

                assert upload_progress_called
                result = await s3_get_object(s3, client, s3_bucket, key)
                assert result == test_data

    async def test_s3_file_upload_with_custom_http_session(self, s3_bucket, s3_backend):
        """Test s3_file_upload with external multiplexed niquests.AsyncSession."""
        from tracktolib.s3.niquests import s3_file_upload, s3_get_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession(multiplexed=True) as client:
                key = "test/custom-session-stream.bin"
                data_size = 12 * 1024 * 1024
                chunk_size = 3 * 1024 * 1024
                test_data = b"Y" * data_size

                async def data_stream():
                    for i in range(0, len(test_data), chunk_size):
                        yield test_data[i : i + chunk_size]

                await s3_file_upload(
                    s3,
                    client,
                    s3_bucket,
                    key,
                    data_stream(),
                    min_part_size=5 * 1024 * 1024,
                )

                result = await s3_get_object(s3, client, s3_bucket, key)
                assert result == test_data

    @pytest.mark.parametrize(
        "acl",
        [
            pytest.param(None, id="acl_none"),
            pytest.param("private", id="acl_private"),
            pytest.param("public-read", id="acl_public_read"),
        ],
    )
    async def test_s3_file_upload_with_acl(self, s3_bucket, s3_backend, acl):
        """Test s3_file_upload with different ACL values."""
        from tracktolib.s3.niquests import s3_file_upload, s3_get_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                key = f"test/acl-stream-{acl}.bin"
                data_size = 12 * 1024 * 1024
                chunk_size = 3 * 1024 * 1024
                test_data = b"Z" * data_size

                async def data_stream():
                    for i in range(0, len(test_data), chunk_size):
                        yield test_data[i : i + chunk_size]

                await s3_file_upload(
                    s3,
                    client,
                    s3_bucket,
                    key,
                    data_stream(),
                    min_part_size=5 * 1024 * 1024,
                    acl=acl,
                )

                result = await s3_get_object(s3, client, s3_bucket, key)
                assert result == test_data


@pytest.mark.usefixtures("setup_bucket")
class TestS3BucketManagement:
    @pytest.mark.parametrize(
        ("policy_input", "policy_type"),
        [
            pytest.param(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "s3:GetObject",
                            "Resource": "arn:aws:s3:::test-niquests/*",
                        }
                    ],
                },
                "dict",
                id="policy_as_dict",
            ),
            pytest.param(
                '{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::test-niquests/*"}]}',
                "str",
                id="policy_as_str",
            ),
        ],
    )
    async def test_bucket_policy_crud(self, s3_bucket, s3_backend, policy_input, policy_type):
        """Test put, get, and delete bucket policy operations."""
        from tracktolib.s3.niquests import s3_delete_bucket_policy, s3_get_bucket_policy, s3_put_bucket_policy

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                # Put policy
                resp = await s3_put_bucket_policy(s3, client, s3_bucket, policy_input)
                assert resp.status_code in (200, 204)  # AWS/MinIO 204, moto 200

                # Get policy
                result = await s3_get_bucket_policy(s3, client, s3_bucket)
                assert result is not None
                assert result["Version"] == "2012-10-17"
                assert len(result["Statement"]) == 1

                # Delete policy
                resp = await s3_delete_bucket_policy(s3, client, s3_bucket)
                assert resp.status_code in (200, 204)

    async def test_get_bucket_policy_nonexistent(self, s3_bucket, s3_backend):
        """Test getting a bucket policy that doesn't exist."""
        from tracktolib.s3.niquests import s3_get_bucket_policy

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                # Get non-existent policy (should return None or raise depending on provider)
                result = await s3_get_bucket_policy(s3, client, s3_bucket)
                # Providers differ on missing policies (empty body vs error)
                assert result is None or isinstance(result, dict)

    @pytest.mark.parametrize(
        "num_objects",
        [
            pytest.param(0, id="empty_bucket"),
            pytest.param(3, id="few_objects"),
            pytest.param(10, id="many_objects"),
        ],
    )
    async def test_empty_bucket(self, s3_bucket, s3_backend, num_objects):
        """Test emptying a bucket with various numbers of objects."""
        from tracktolib.s3.niquests import s3_empty_bucket, s3_list_files, s3_put_object

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                # Create test objects
                for i in range(num_objects):
                    await s3_put_object(
                        s3, client, s3_bucket, f"empty-test/file{i}.txt", f"content{i}".encode(), acl=None
                    )

                # Verify objects exist
                files_before = [f async for f in s3_list_files(s3, client, s3_bucket, "empty-test/")]
                assert len(files_before) == num_objects

                # Empty the bucket
                deleted_count = await s3_empty_bucket(s3, client, s3_bucket)
                assert deleted_count == num_objects

                # Verify bucket is empty
                files_after = [f async for f in s3_list_files(s3, client, s3_bucket, "")]
                assert len(files_after) == 0


@pytest.mark.usefixtures("setup_bucket")
class TestS3SessionBucketManagement:
    async def test_session_bucket_policy(self, s3_bucket, s3_client):
        """Test S3Session bucket policy methods."""
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{s3_bucket}/*",
                }
            ],
        }

        # Put policy
        resp = await s3_client.put_bucket_policy(s3_bucket, policy)
        assert resp.status_code in (200, 204)  # AWS/MinIO 204, moto 200

        # Get policy
        result = await s3_client.get_bucket_policy(s3_bucket)
        assert result is not None
        assert result["Version"] == "2012-10-17"

        # Delete policy
        resp = await s3_client.delete_bucket_policy(s3_bucket)
        assert resp.status_code in (200, 204)

    async def test_session_empty_bucket(self, s3_bucket, s3_client):
        """Test S3Session empty_bucket method."""
        # Create test objects
        for i in range(5):
            await s3_client.put_object(s3_bucket, f"session-empty/file{i}.txt", f"content{i}".encode(), acl=None)

        # Empty the bucket
        deleted_count = await s3_client.empty_bucket(s3_bucket)
        assert deleted_count == 5

        # Verify bucket is empty
        files = [f async for f in s3_client.list_files(s3_bucket, "")]
        assert len(files) == 0


@pytest.mark.usefixtures("setup_bucket")
class TestS3WebsiteConfig:
    @pytest.mark.parametrize(
        ("index_document", "error_document"),
        [
            pytest.param("index.html", None, id="index_only"),
            pytest.param("index.html", "error.html", id="index_and_error"),
            pytest.param("home.htm", "404.htm", id="custom_names"),
        ],
    )
    async def test_bucket_website_config(self, s3_bucket, s3_backend, index_document, error_document):
        """Test put and delete bucket website configuration."""
        from tracktolib.s3.niquests import s3_delete_bucket_website, s3_put_bucket_website

        with get_botocore_client(s3_backend) as s3:
            async with niquests.AsyncSession() as client:
                # Put website config
                resp = await s3_put_bucket_website(s3, client, s3_bucket, index_document, error_document)
                assert resp.status_code == 200

                # Delete website config
                resp = await s3_delete_bucket_website(s3, client, s3_bucket)
                assert resp.status_code == 204

    async def test_session_bucket_website(self, s3_bucket, s3_client):
        """Test S3Session bucket website methods."""
        # Put website config
        resp = await s3_client.put_bucket_website(s3_bucket, "index.html", "error.html")
        assert resp.status_code == 200

        # Delete website config
        resp = await s3_client.delete_bucket_website(s3_bucket)
        assert resp.status_code == 204


def _create_local_files(tmp_path: Path, files: dict[str, str]) -> None:
    """Create local files from a dict of {relative_path: content}."""
    for path, content in files.items():
        file_path = tmp_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


@pytest.mark.usefixtures("setup_bucket")
class TestS3SyncDirectory:
    @pytest.fixture
    def local_dir(self, tmp_path):
        """Fixture providing a temp directory with helper to create files."""

        def create(files: dict[str, str]) -> Path:
            _create_local_files(tmp_path, files)
            return tmp_path

        return create

    @pytest.mark.parametrize(
        ("files", "prefix", "expected"),
        [
            pytest.param(
                {"file1.txt": "content1", "subdir/file2.txt": "content2"},
                "sync-new",
                {"uploaded": ["sync-new/file1.txt", "sync-new/subdir/file2.txt"], "deleted": [], "skipped": []},
                id="new_files",
            ),
            pytest.param(
                {"root.txt": "root content"},
                "",
                {"uploaded": ["root.txt"], "deleted": [], "skipped": []},
                id="empty_prefix",
            ),
            pytest.param(
                {"a.txt": "a", "b/c.txt": "c"},
                "prefix",
                {"uploaded": ["prefix/a.txt", "prefix/b/c.txt"], "deleted": [], "skipped": []},
                id="nested_with_prefix",
            ),
            pytest.param(
                {"file.txt": "content"},
                "deep/nested/prefix",
                {"uploaded": ["deep/nested/prefix/file.txt"], "deleted": [], "skipped": []},
                id="deep_prefix",
            ),
        ],
    )
    async def test_sync_upload(self, s3_bucket, s3_client, local_dir, files, prefix, expected):
        """Test syncing new files to S3."""
        tmp_path = local_dir(files)
        result = await s3_client.sync_directory(s3_bucket, tmp_path, prefix)

        assert sorted(result["uploaded"]) == expected["uploaded"]
        assert result["deleted"] == expected["deleted"]
        assert result["skipped"] == expected["skipped"]

    @pytest.mark.parametrize(
        ("files", "on_setup", "sync_kwargs", "expected"),
        [
            pytest.param(
                {"file.txt": "content"},
                lambda p: None,  # No change, file should be skipped
                {},
                {"uploaded": [], "deleted": [], "skipped": ["sync/file.txt"]},
                id="skip_unchanged",
            ),
            pytest.param(
                {"file.txt": "same size content!!"},
                lambda p: (p / "file.txt").write_text("much longer content now"),
                {},
                {"uploaded": ["sync/file.txt"], "deleted": [], "skipped": []},
                id="upload_changed_size",
            ),
            pytest.param(
                {"file.txt": "same size content!!"},
                lambda p: os.utime(p / "file.txt", (time.time() + 10, time.time() + 10)),
                {},
                {"uploaded": ["sync/file.txt"], "deleted": [], "skipped": []},
                id="upload_newer_mtime",
            ),
            pytest.param(
                {"keep.txt": "keep", "remove.txt": "remove"},
                lambda p: (p / "remove.txt").unlink(),
                {"delete": True},
                {"uploaded": [], "deleted": ["sync/remove.txt"], "skipped": ["sync/keep.txt"]},
                id="delete_remote",
            ),
            pytest.param(
                {"keep.txt": "keep", "remove.txt": "remove"},
                lambda p: (p / "remove.txt").unlink(),
                {"delete": False},
                {"uploaded": [], "deleted": [], "skipped": ["sync/keep.txt"]},
                id="keep_remote",
            ),
        ],
    )
    async def test_sync_second_pass(self, s3_bucket, s3_client, local_dir, files, on_setup, sync_kwargs, expected):
        """Test sync behavior on second pass after modifications."""
        tmp_path = local_dir(files)

        # Set mtime to past for initial sync
        past_time = time.time() - 3600
        for f in tmp_path.rglob("*"):
            if f.is_file():
                os.utime(f, (past_time, past_time))

        await s3_client.sync_directory(s3_bucket, tmp_path, "sync")

        # Apply modification
        on_setup(tmp_path)

        result = await s3_client.sync_directory(s3_bucket, tmp_path, "sync", **sync_kwargs)
        assert result["uploaded"] == expected["uploaded"]
        assert result["deleted"] == expected["deleted"]
        assert result["skipped"] == expected["skipped"]

    async def test_sync_callbacks(self, s3_bucket, s3_client, local_dir):
        """Test sync with callback functions."""
        tmp_path = local_dir({"new.txt": "new", "existing.txt": "existing"})

        # First sync for existing.txt
        await s3_client.sync_directory(s3_bucket, tmp_path, "sync-cb")

        # Set mtime to past so existing.txt is skipped
        past_time = time.time() - 3600
        os.utime(tmp_path / "existing.txt", (past_time, past_time))

        # Add file to delete remotely
        await s3_client.put_object(s3_bucket, "sync-cb/to-delete.txt", b"delete me")

        # Remove new.txt and recreate to ensure it's uploaded
        (tmp_path / "new.txt").unlink()
        (tmp_path / "new.txt").write_text("new")

        uploaded: list[tuple[Path, str]] = []
        deleted: list[str] = []
        skipped: list[tuple[Path, str]] = []

        await s3_client.sync_directory(
            s3_bucket,
            tmp_path,
            "sync-cb",
            delete=True,
            on_upload=lambda p, k: uploaded.append((p, k)),
            on_delete=lambda k: deleted.append(k),
            on_skip=lambda p, k: skipped.append((p, k)),
        )

        assert len(uploaded) == 1
        assert uploaded[0][1] == "sync-cb/new.txt"
        assert deleted == ["sync-cb/to-delete.txt"]
        assert len(skipped) == 1
        assert skipped[0][1] == "sync-cb/existing.txt"

    @pytest.mark.parametrize(
        ("path_factory", "expected_error"),
        [
            pytest.param(lambda p: p / "nonexistent", "does not exist", id="nonexistent"),
            pytest.param(lambda p: p / "file.txt", "not a directory", id="file_not_dir"),
        ],
    )
    async def test_sync_invalid_local_dir(self, s3_bucket, s3_client, tmp_path, path_factory, expected_error):
        """Test sync raises ValueError for invalid local directory."""
        (tmp_path / "file.txt").write_text("content")
        invalid_path = path_factory(tmp_path)

        with pytest.raises(ValueError, match=expected_error):
            await s3_client.sync_directory(s3_bucket, invalid_path, "sync")
