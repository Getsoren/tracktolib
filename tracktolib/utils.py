import asyncio
import collections
import datetime as dt
import importlib.util
import io
import itertools
import mmap
import os
import subprocess
import sys
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    Coroutine,
    Iterable,
    Iterator,
    Literal,
    overload,
)

type OnCmdUpdate = Callable[[str], None]
type OnCmdDone = Callable[[str, str, int], None]


def exec_cmd(
    cmd: str | list[str],
    *,
    env: dict | None = None,
    on_update: OnCmdUpdate | None = None,
    on_done: OnCmdDone | None = None,
    **kwargs,
) -> str:
    default_shell = os.getenv("SHELL", "/bin/bash")

    process = subprocess.Popen(
        cmd,
        shell=isinstance(cmd, str),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        executable=default_shell if isinstance(cmd, str) else None,
        env=env,
        text=True,
        **kwargs,
    )

    if on_update is not None:
        for line in process.stderr or []:
            on_update(line)

    stdout, stderr = process.communicate()
    exit_code = process.wait()

    if on_done is not None:
        on_done(stdout, stderr, exit_code)

    if exit_code != 0:
        raise Exception(stderr)
    return stdout


async def aexec_cmd(cmd: str | list[str], *, encoding: str = "utf-8", env: dict | None = None) -> str:
    default_shell = os.getenv("SHELL", "/bin/bash")

    if isinstance(cmd, str):
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, executable=default_shell, env=env
        )
    else:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(stderr.decode(encoding))
    return stdout.decode(encoding)


def import_module(path: Path):
    """
    Import a module from a path.
    Eg:
        # >>> =
        >>> module = import_module(Path('~/my_module.py'))
        >>> module.my_function()
    """
    name = path.name.removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise ImportError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    if spec.loader is not None:
        spec.loader.exec_module(module)
    return module


@overload
def get_chunks[T](it: Iterable[T], size: int, *, as_list: Literal[False]) -> Iterator[Iterable[T]]: ...


@overload
def get_chunks[T](it: Iterable[T], size: int, *, as_list: Literal[True]) -> Iterator[list[T]]: ...


@overload
def get_chunks[T](it: Iterable[T], size: int) -> Iterator[list[T]]: ...


def get_chunks[T](it: Iterable[T], size: int, *, as_list: bool = True) -> Iterator[Iterable[T]]:
    iterator = iter(it)
    for first in iterator:
        d = itertools.chain([first], itertools.islice(iterator, size - 1))
        yield d if not as_list else list(d)


async def get_stream_chunk_str(
    data_stream: AsyncIterable[str],
    min_size: int,
) -> AsyncIterator[str]:
    """Buffers an async string stream and yields chunks of at least `min_size`."""
    buffer = ""
    buffer_size = 0
    async for chunk in data_stream:
        if not chunk:
            continue
        buffer += chunk
        buffer_size += len(chunk)
        while buffer_size >= min_size * 2:
            yield buffer[:min_size]
            buffer = buffer[min_size:]
            buffer_size -= min_size
    if buffer_size > 0:
        yield buffer


class BytesBuffer:
    """Memory-efficient bytes buffer using a deque of chunks.

    Appends are O(1) (no copy). Reads only copy at chunk boundaries via memoryview.
    Adapted from urllib3's BytesQueueBuffer.
    """

    __slots__ = ("buffer", "_size")

    def __init__(self) -> None:
        self.buffer: collections.deque[bytes | memoryview[bytes]] = collections.deque()
        self._size: int = 0

    def __len__(self) -> int:
        return self._size

    def put(self, data: bytes) -> None:
        self.buffer.append(data)
        self._size += len(data)

    def get(self, n: int) -> bytes:
        if not self.buffer:
            raise RuntimeError("buffer is empty")

        # Fast path: first chunk is exactly the right size
        if len(self.buffer[0]) == n and isinstance(self.buffer[0], bytes):
            self._size -= n
            return self.buffer.popleft()  # type: ignore[return-value]

        fetched = 0
        ret = io.BytesIO()
        while fetched < n:
            remaining = n - fetched
            chunk = self.buffer.popleft()
            chunk_length = len(chunk)
            if remaining < chunk_length:
                mv = memoryview(chunk)
                ret.write(mv[:remaining])
                self.buffer.appendleft(mv[remaining:])  # type: ignore[arg-type]
                self._size -= remaining
                break
            ret.write(chunk)
            self._size -= chunk_length
            fetched += chunk_length
            if not self.buffer:
                break
        return ret.getvalue()

    def get_all(self) -> bytes:
        buffer = self.buffer
        if not buffer:
            return b""
        if len(buffer) == 1:
            result = buffer.pop()
            if isinstance(result, memoryview):
                result = result.tobytes()
        else:
            ret = io.BytesIO()
            ret.writelines(buffer.popleft() for _ in range(len(buffer)))
            result = ret.getvalue()
        self._size = 0
        return result  # type: ignore[return-value]


async def get_stream_chunk(
    data_stream: AsyncIterable[bytes],
    min_size: int,
) -> AsyncIterator[bytes]:
    """Buffers an async byte stream and yields chunks of at least `min_size`."""
    buffer = BytesBuffer()
    async for chunk in data_stream:
        if not chunk:
            continue
        buffer.put(chunk)
        while len(buffer) >= min_size * 2:
            yield buffer.get(min_size)
    if len(buffer) > 0:
        yield buffer.get_all()


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    if isinstance(obj, (IPv4Address, IPv6Address)):
        return str(obj)
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Type '{type(obj)}' not serializable")


def get_nb_lines(file: Path) -> int:
    """
    Source: https://stackoverflow.com/a/68385697/2265812

    """
    with file.open("r+") as f:
        buf = mmap.mmap(f.fileno(), 0)

    nb_lines = 0
    while buf.readline():
        nb_lines += 1
    return nb_lines


def fill_dict(items: list[dict], *, keys: list | None = None, default: Any | None = None) -> list[dict]:
    """Returns a list of items with the same key for all"""

    def _fill_dict(x):
        return {k: x.get(k, default) for k in _keys}

    _keys = keys or sorted(frozenset().union(*items))
    return [_fill_dict(x) for x in items]


def to_snake_case(string: str) -> str:
    return "".join(["_" + i.lower() if i.isupper() else i for i in string]).lstrip("_")


def to_camel_case(string: str) -> str:
    return "".join(word.capitalize() if i > 0 else word for i, word in enumerate(string.split("_")))


@overload
def dict_to_camel(d: dict) -> dict: ...


@overload
def dict_to_camel(d: list[dict]) -> list[dict]: ...


def dict_to_camel(d: dict | list):
    """
    Convert all keys of a dict or list of dicts to camel case
    """

    def _parse_item(v):
        return dict_to_camel(v) if isinstance(v, dict) else v

    def _parse_list(dl):
        return [_parse_item(v) for v in dl]

    if isinstance(d, list):
        return _parse_list(d)

    return {to_camel_case(k): _parse_list(v) if isinstance(v, list) else _parse_item(v) for k, v in d.items()}


@overload
def rm_keys(data: dict, keys: list[str]) -> dict: ...


@overload
def rm_keys(data: list[dict], keys: list[str]) -> list[dict]: ...


def rm_keys(data: dict | list[dict], keys: list[str]):
    """Remove keys from a dict or a list of dicts"""
    _data = data if isinstance(data, list) else [data]
    for d in _data:
        for key in keys:
            assert d.pop(key, None) is not None
    return _data if isinstance(data, list) else _data[0]


def num_not_none(*args) -> int:
    """
    Count the number of non None arguments
    """
    return sum(1 for x in args if x is not None)


def deep_reload(m: ModuleType):
    """
    Reload a module and all its submodules
    """
    sub_mods = [_mod for _mod in sys.modules if _mod == m.__name__ or _mod.startswith(f"{m.__name__}.")]
    for pkg in sorted(sub_mods, key=lambda item: item.count("."), reverse=True):
        importlib.reload(sys.modules[pkg])


def get_first_line(lines: str) -> str:
    _lines = lines.split("\n")
    return _lines[0] if _lines else lines


async def run_coros[R](
    coros: Iterable[Coroutine[Any, Any, R]],
    sem: asyncio.Semaphore | None = None,
) -> AsyncIterator[R]:
    """Run coroutines and yield results in order.

    Args:
        coros: Coroutines to execute
        sem: If provided, run in parallel with rate limiting.
             If None, run sequentially.

    Yields:
        Results in input order.

    Example:
        async for result in run_coros([fetch(1), fetch(2)], sem):
            print(result)
    """
    coro_list = list(coros)

    if sem is None:
        for coro in coro_list:
            yield await coro
    else:

        async def with_sem(coro: Coroutine[Any, Any, R]) -> R:
            async with sem:
                return await coro

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(with_sem(c)) for c in coro_list]

        for task in tasks:
            yield task.result()
