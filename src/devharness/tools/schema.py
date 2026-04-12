"""Auto-generate JSON Schema from Python function signatures and type hints."""

from __future__ import annotations

import inspect
import types
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Callable,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

# Mapping of Python types to JSON Schema types.
_PRIMITIVE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    Path: "string",
}


def _is_optional(tp: Any) -> tuple[bool, Any]:
    """Return (True, inner_type) if *tp* is ``Optional[X]`` (i.e. ``X | None``)."""
    origin = get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = get_args(tp)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and len(args) == 2:
            return True, non_none[0]
    return False, tp


def _type_to_schema(tp: Any) -> dict[str, Any]:
    """Convert a single Python type annotation to a JSON Schema fragment."""
    # Handle Annotated[X, Field(...)]
    if get_origin(tp) is Annotated:
        args = get_args(tp)
        base_schema = _type_to_schema(args[0])
        # Look for pydantic Field or any object with a ``description`` attribute.
        for meta in args[1:]:
            desc = getattr(meta, "description", None)
            if desc:
                base_schema["description"] = desc
        return base_schema

    # Optional
    is_opt, inner = _is_optional(tp)
    if is_opt:
        return _type_to_schema(inner)

    # Primitives
    if tp in _PRIMITIVE_MAP:
        return {"type": _PRIMITIVE_MAP[tp]}

    # list[X]
    origin = get_origin(tp)
    if origin is list:
        args = get_args(tp)
        items = _type_to_schema(args[0]) if args else {}
        return {"type": "array", "items": items}

    # dict[K, V]
    if origin is dict:
        args = get_args(tp)
        additional = _type_to_schema(args[1]) if args and len(args) > 1 else {}
        return {"type": "object", "additionalProperties": additional}

    # Fallback
    return {"type": "string"}


def fn_to_json_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """Inspect *fn*'s signature and type hints and produce a JSON Schema dict.

    Parameters named ``self``, ``cls``, and ``kwargs`` are skipped.  Parameters
    without a default value are marked as ``required``.
    """
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls", "kwargs"):
            continue

        tp = hints.get(name, str)
        prop_schema = _type_to_schema(tp)

        # If the parameter has a default, it is optional.
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop_schema["default"] = param.default

        properties[name] = prop_schema

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema
