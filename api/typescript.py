"""The TypeScript types of the web, generated from the OpenAPI schema of the API.

``python -m api.typescript`` writes ``web/src/api.gen.ts`` (``make web-types``), and a test fails when the committed
file is not what the API serves: a field added, renamed or retyped in ``api/schemas.py`` reaches the web's type check
instead of a page that breaks in the browser.

It covers the JSON Schema that pydantic writes for these models (objects, ``$ref``, ``anyOf``, ``enum``, ``const``
and arrays). A general tool (openapi-typescript) would be one more dependency, and it does not support the
TypeScript the web uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.main import create_app
from api.settings import Settings

OUTPUT = Path(__file__).parent.parent / "web" / "src" / "api.gen.ts"
HEADER = """\
// Generated from the OpenAPI schema of the API by `make web-types` (api/typescript.py). Do not edit by hand.
"""
# Generic envelopes: the web declares its own Page<T>.
SKIPPED = ("Page_", "Error", "ErrorResponse")

Schema = dict[str, Any]


class _NoDatabase:
    """The database of an app built only to read its OpenAPI document: no query ever runs."""

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, Any]]:  # noqa: ARG002 - the protocol
        msg = "no database: the app is built only for its schema"
        raise RuntimeError(msg)

    def ping(self) -> bool:
        return False


def schemas() -> dict[str, Schema]:
    """The response models of the API, by name, as its OpenAPI document describes them."""
    spec = create_app(Settings(), database=_NoDatabase()).openapi()
    return spec["components"]["schemas"]


SIMPLE = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
    "object": "Record<string, unknown>",
}


def to_type(schema: Schema) -> str:
    """The TypeScript type of a JSON Schema."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        return " | ".join(dict.fromkeys(to_type(s) for s in schema["anyOf"]))
    if "const" in schema or "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema.get("enum", [schema.get("const")]))
    if schema.get("type") == "array":
        return _array(schema)
    if schema.get("type") not in SIMPLE:
        msg = f"no TypeScript type for the JSON Schema {schema}"
        raise ValueError(msg)
    return SIMPLE[schema["type"]]


def _array(schema: Schema) -> str:
    if "prefixItems" in schema:  # a tuple
        return "[" + ", ".join(to_type(s) for s in schema["prefixItems"]) + "]"
    item = to_type(schema.get("items", {}))
    return f"({item})[]" if " | " in item else f"{item}[]"


def _doc(text: str | None, indent: str = "") -> list[str]:
    if not text:
        return []
    lines = text.strip().splitlines()
    if len(lines) == 1:
        return [f"{indent}/** {lines[0]} */"]
    return [f"{indent}/**", *(f"{indent} * {line}".rstrip() for line in lines), f"{indent} */"]


def interface(name: str, schema: Schema) -> str:
    """One model as an exported interface, with its descriptions as doc comments.

    Every field is required: the schema lists a field with a default as optional (for a request), but a response
    always carries it (FastAPI serialises the whole model).
    """
    lines = [*_doc(schema.get("description")), f"export interface {name} {{"]
    for field, prop in schema["properties"].items():
        lines.extend(_doc(prop.get("description"), "  "))
        lines.append(f"  {field}: {to_type(prop)};")
    lines.append("}")
    return "\n".join(lines)


def render(models: dict[str, Schema] | None = None) -> str:
    """The whole generated file."""
    models = schemas() if models is None else models
    blocks = [interface(name, s) for name, s in sorted(models.items()) if not name.startswith(SKIPPED)]
    return HEADER + "\n" + "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
