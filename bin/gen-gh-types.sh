#!/usr/bin/env bash
#
# DESCRIPTION
#   Generate TypedDicts from GitHub's OpenAPI spec for the tracktolib.gh module.
#   Downloads the full GitHub REST API spec, filters to required schemas, and
#   generates Python TypedDict classes using datamodel-codegen.
#
# USAGE
#   bin/gen-gh-types.sh
#
#   No arguments required. The script outputs to tracktolib/gh/types.py.
#   To add new schemas, edit the SCHEMAS array in this script.

set -euo pipefail


cd "$(dirname "$0")/.." || exit

OUTPUT_FILE="tracktolib/gh/types.py"
TEMP_FULL=$(mktemp)
TEMP_SPEC=$(mktemp)
trap 'rm -f "$TEMP_FULL" "$TEMP_SPEC"' EXIT

GITHUB_OPENAPI_URL="https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"

# Schemas we need (and their dependencies will be resolved)
SCHEMAS=(
  "issue-comment"
  "label"
  "deployment"
  "deployment-status"
  "nullable-simple-user"
  "simple-user"
  "nullable-integration"

  "reaction-rollup"
  "reaction"

  "pull-request-simple"
  "pull-request"
  "pull-request-review"
)

echo "Downloading GitHub OpenAPI spec..."
curl -sL "$GITHUB_OPENAPI_URL" -o "$TEMP_FULL"

echo "Filtering to required schemas..."
# Build jq filter for selected schemas
SCHEMA_FILTER=$(printf '"%s",' "${SCHEMAS[@]}" | sed 's/,$//')

jq --argjson schemas "[$SCHEMA_FILTER]" '
{
  openapi: .openapi,
  info: .info,
  servers: .servers,
  components: {
    schemas: (.components.schemas | with_entries(select(.key as $k | $schemas | index($k))))
  }
}' "$TEMP_FULL" > "$TEMP_SPEC"

# Patch pull-request-simple/pull-request/pull-request-review to avoid heavy deps (repository, team, etc.)
# Keep all properties but replace complex $ref ones with plain object types,
# except labels (use label $ref), head/base (keep ref/label/sha only).
jq '
def obj: { type: "object" };
def nullable_obj: { oneOf: [{ type: "object" }, { type: "null" }] };
def obj_array: { type: "array", items: { type: "object" } };
.components.schemas["pull-request-simple"].properties |= (
  .labels = { type: "array", items: { "$ref": "#/components/schemas/label" } } |
  .head = {
    type: "object",
    properties: { ref: { type: "string" }, label: { type: "string" }, sha: { type: "string" } },
    required: ["ref", "label", "sha"]
  } |
  .base = {
    type: "object",
    properties: { ref: { type: "string" }, label: { type: "string" }, sha: { type: "string" } },
    required: ["ref", "label", "sha"]
  } |
  .user = nullable_obj |
  .assignee = nullable_obj |
  .milestone = nullable_obj |
  .auto_merge = nullable_obj |
  .assignees = obj_array |
  .requested_reviewers = obj_array |
  .requested_teams = obj_array |
  ._links = obj |
  .author_association = { type: "string" }
) |
.components.schemas["pull-request"].properties |= (
  .labels = { type: "array", items: { "$ref": "#/components/schemas/label" } } |
  .head = {
    type: "object",
    properties: { ref: { type: "string" }, label: { type: "string" }, sha: { type: "string" } },
    required: ["ref", "label", "sha"]
  } |
  .base = {
    type: "object",
    properties: { ref: { type: "string" }, label: { type: "string" }, sha: { type: "string" } },
    required: ["ref", "label", "sha"]
  } |
  .milestone = nullable_obj |
  .auto_merge = nullable_obj |
  .stack = nullable_obj |
  .assignees = obj_array |
  .requested_reviewers = obj_array |
  .requested_teams = obj_array |
  ._links = obj |
  .author_association = { type: "string" }
) |
.components.schemas["pull-request-review"].properties |= (
  ._links = obj |
  .author_association = { type: "string" }
)
' "$TEMP_SPEC" > "$TEMP_SPEC.tmp" && mv "$TEMP_SPEC.tmp" "$TEMP_SPEC"

echo "Generating TypedDicts..."
uv run datamodel-codegen \
  --input "$TEMP_SPEC" \
  --input-file-type openapi \
  --output "$OUTPUT_FILE" \
  --output-model-type typing.TypedDict \
  --target-python-version 3.13 \
  --disable-future-imports \
  --use-standard-collections \
  --use-union-operator \
  --use-double-quotes \
  --collapse-root-models \
  --strip-default-none \
  --use-schema-description \
  --openapi-scopes schemas

# Clean up generated file (portable sed - works on both macOS and Linux)
# TypedDict is imported from typing_extensions (extra_items support), drop the typing one
sed -e '/^#   filename:/d' -e 's/^from typing import \(.*\), TypedDict$/from typing import \1/' \
  "$OUTPUT_FILE" > "$OUTPUT_FILE.tmp" && mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"

uv run ruff format "$OUTPUT_FILE"

echo "Done! Generated $(wc -l < "$OUTPUT_FILE") lines to $OUTPUT_FILE"
