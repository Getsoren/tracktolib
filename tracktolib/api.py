import json
import warnings
from dataclasses import dataclass, field
from inspect import getdoc
from typing import (
    Any,
    AsyncIterator,
    Callable,
    ClassVar,
    Coroutine,
    Literal,
    Mapping,
    Sequence,
    TypeAlias,
    TypedDict,
    get_args,
    get_origin,
    get_type_hints,
)

from .utils import get_first_line, json_serial

try:
    import starlette.status
    from fastapi import APIRouter, params
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, ConfigDict
    from pydantic.alias_generators import to_camel
except ImportError:
    raise ImportError('Please install fastapi, pydantic or tracktolib with "api" to use this module')


# noqa: N802
def Depends[D](
    dependency: Callable[
        ...,
        Coroutine[Any, Any, D] | Coroutine[Any, Any, D | None] | AsyncIterator[D] | D,
    ]
    | None = None,
    *,
    use_cache: bool = True,
) -> D:
    """TODO: add support for __call__ (maybe see https://github.com/python/typing/discussions/1106 ?)"""
    return params.Depends(dependency, use_cache=use_cache)  # pyright: ignore [reportReturnType]


type _BaseModelBound = BaseModel | None | Sequence[BaseModel]
type Response[B: _BaseModelBound] = Mapping | Sequence[Mapping] | B

Method = Literal["GET", "POST", "DELETE", "PATCH", "PUT"]

type EnpointFn[B: _BaseModelBound] = Callable[..., Response[B]]

Dependencies: TypeAlias = Sequence[params.Depends] | None
StatusCode: TypeAlias = int | None


class MethodMeta(TypedDict):
    fn: EnpointFn[Any]
    status_code: StatusCode
    dependencies: Dependencies
    path: str | None
    response_model: type[BaseModel | None | Sequence[BaseModel]] | None
    openapi_extra: dict[str, Any] | None
    name: str | None
    summary: str | None
    description: str | None
    deprecated: bool | None


@dataclass
class Endpoint:
    _methods: dict[Method, MethodMeta] = field(init=False, default_factory=dict)

    @property
    def methods(self):
        return self._methods

    def get[B: _BaseModelBound](
        self,
        status_code: StatusCode = None,
        dependencies: Dependencies = None,
        path: str | None = None,
        model: type[B] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        name: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        deprecated: bool | None = None,
    ):
        return _get_method_wrapper(
            cls=self,
            method="GET",
            status_code=status_code,
            dependencies=dependencies,
            path=path,
            model=model,
            openapi_extra=openapi_extra,
            name=name,
            summary=summary,
            description=description,
            deprecated=deprecated,
        )

    def post[B: _BaseModelBound](
        self,
        *,
        status_code: StatusCode = None,
        dependencies: Dependencies = None,
        path: str | None = None,
        model: type[B] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        name: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        deprecated: bool | None = None,
    ):
        return _get_method_wrapper(
            cls=self,
            method="POST",
            status_code=status_code,
            dependencies=dependencies,
            path=path,
            model=model,
            openapi_extra=openapi_extra,
            name=name,
            summary=summary,
            description=description,
            deprecated=deprecated,
        )

    def put[B: _BaseModelBound](
        self,
        status_code: StatusCode = None,
        dependencies: Dependencies = None,
        path: str | None = None,
        model: type[B] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        name: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        deprecated: bool | None = None,
    ):
        return _get_method_wrapper(
            cls=self,
            method="PUT",
            status_code=status_code,
            dependencies=dependencies,
            path=path,
            model=model,
            openapi_extra=openapi_extra,
            name=name,
            summary=summary,
            description=description,
            deprecated=deprecated,
        )

    def delete[B: _BaseModelBound](
        self,
        status_code: StatusCode = None,
        dependencies: Dependencies = None,
        path: str | None = None,
        model: type[B] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        name: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        deprecated: bool | None = None,
    ):
        return _get_method_wrapper(
            cls=self,
            method="DELETE",
            status_code=status_code,
            dependencies=dependencies,
            path=path,
            model=model,
            openapi_extra=openapi_extra,
            name=name,
            summary=summary,
            description=description,
            deprecated=deprecated,
        )

    def patch[B: _BaseModelBound](
        self,
        status_code: StatusCode = None,
        dependencies: Dependencies = None,
        path: str | None = None,
        model: type[B] | None = None,
        openapi_extra: dict[str, Any] | None = None,
        name: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        deprecated: bool | None = None,
    ):
        return _get_method_wrapper(
            cls=self,
            method="PATCH",
            status_code=status_code,
            dependencies=dependencies,
            path=path,
            model=model,
            openapi_extra=openapi_extra,
            name=name,
            summary=summary,
            description=description,
            deprecated=deprecated,
        )


def _get_method_wrapper[B: _BaseModelBound](
    cls: Endpoint,
    method: Method,
    *,
    status_code: StatusCode = None,
    dependencies: Dependencies = None,
    path: str | None = None,
    model: type[B] | None = None,
    openapi_extra: dict[str, Any] | None = None,
    name: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    deprecated: bool | None = None,
):
    def _set_method_wrapper(func: EnpointFn):
        if model is not None:
            _openapi_extra = {
                **(openapi_extra or {}),
                **generate_list_name_model(model, status_code),
            }
        else:
            _openapi_extra = openapi_extra
        _meta: MethodMeta = {
            "fn": func,
            "status_code": status_code,
            "dependencies": dependencies,
            "path": path,
            "response_model": model,
            "openapi_extra": _openapi_extra,
            "name": name,
            "summary": summary,
            "description": description,
            "deprecated": deprecated,
        }
        cls._methods[method] = _meta

    return _set_method_wrapper


_NoneType = type(None)


def _get_return_type(fn):
    return_type = get_type_hints(fn)["return"]
    _args = get_args(return_type)
    is_optional = _NoneType in _args
    _model = [x for x in _args if x is not _NoneType][-1]
    return _model if not is_optional else _model | None


def add_endpoint(
    path: str,
    router: APIRouter,
    endpoint: Endpoint,
    *,
    dependencies: Dependencies = None,
):
    for _method, _meta in endpoint.methods.items():
        _fn = _meta["fn"]
        _status_code = _meta["status_code"]
        _dependencies = _meta["dependencies"]
        _path = _meta["path"]
        _response_model = _meta["response_model"]
        _name = _meta.get("name")
        _summary = _meta.get("summary")
        _description = _meta.get("description")
        _deprecated = _meta.get("deprecated")
        if not _response_model:
            try:
                _response_model = _get_return_type(_fn)
            except KeyError:
                raise ValueError(f"Could not find a return type for {_method} {path}")

        full_path = path if not _path else f"{path}/{_path}"

        description = getdoc(_fn)
        if not description:
            warnings.warn(f"Docstring is missing for {_method} {path}")
        else:
            _name = _name if _name else get_first_line(description)
            _summary = _summary if _summary else get_first_line(description)

        # Todo: add warning name is not None
        router.add_api_route(
            full_path,
            _fn,
            methods=[_method],
            name=_name,
            summary=_summary,
            description=description,
            response_model=_response_model,
            status_code=_status_code,
            dependencies=[*(_dependencies or []), *(dependencies or [])],
            openapi_extra=_meta.get("openapi_extra"),
            deprecated=_deprecated,
        )


@dataclass(init=False)
class JSONSerialResponse(JSONResponse):
    json_serial: ClassVar[Callable[[Any], str]] = field(default=json_serial)

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
            # json_serial is a plain function stored on the class; self.json_serial would bind it and pass self as the value
            default=type(self).json_serial,
        ).encode("utf-8")


def model_to_list(string: str) -> str:
    return f"Array[{string}]"


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, coerce_numbers_to_str=True, populate_by_name=True)


def check_status(resp, status: int = starlette.status.HTTP_200_OK):
    if resp.status_code != status:
        raise AssertionError(json.dumps(resp.json(), indent=4))


def generate_list_name_model[B: _BaseModelBound](model: type[B], status: int | None = None) -> dict:
    _status = "200" if status is None else str(status)
    if get_origin(model) and get_origin(model) is list:
        _title = f"Array[{get_args(model)[0].__name__}]"
    else:
        _title = model.__name__ if hasattr(model, "__name__") else None

    # Todo verify response content type
    return {"responses": {_status: {"content": {"application/json": {"schema": {"title": _title}}}}}}
