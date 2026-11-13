import pytest

from api import typescript


def test_the_committed_web_types_are_the_ones_the_api_serves():
    # Out of date: run `make web-types` and commit web/src/api.gen.ts.
    assert typescript.OUTPUT.read_text(encoding="utf-8") == typescript.render()


def test_json_schema_becomes_typescript():
    assert typescript.to_type({"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]}) == "string | null"
    nested = {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}
    assert typescript.to_type(nested) == "number[][]"
    assert typescript.to_type({"type": "array", "items": {"enum": ["a", "b"], "type": "string"}}) == '("a" | "b")[]'
    point = {"type": "array", "prefixItems": [{"type": "number"}, {"type": "number"}], "minItems": 2, "maxItems": 2}
    assert typescript.to_type({"type": "array", "items": point}) == "[number, number][]"
    assert typescript.to_type({"const": "MultiLineString", "type": "string"}) == '"MultiLineString"'
    assert typescript.to_type({"$ref": "#/components/schemas/Sla"}) == "Sla"
    assert typescript.to_type({"type": "object", "additionalProperties": True}) == "Record<string, unknown>"
    with pytest.raises(ValueError, match="no TypeScript type"):
        typescript.to_type({"type": "file"})


def test_a_model_becomes_an_interface_with_its_descriptions():
    schema = {
        "description": "One thing.",
        "properties": {
            "name": {"type": "string", "description": "Its name."},
            "count": {"type": "integer", "default": 0},  # a default: optional in the schema, always in a response
        },
        "required": ["name"],
    }
    assert typescript.interface("Thing", schema) == (
        "/** One thing. */\nexport interface Thing {\n  /** Its name. */\n  name: string;\n  count: number;\n}"
    )
