#!/bin/bash
# Proto Generation Script for EchoMind
# Generates Python protobuf stubs and Pydantic models from .proto files
#
# Structure (per CLAUDE.md):
#   src/proto/public/*.proto   -> models/public/   (API-facing models)
#   src/proto/internal/*.proto -> models/internal/ (service-to-service models)
#   src/proto/common.proto     -> models/          (shared types)
#
# Usage: ./scripts/generate_proto.sh
#
# Requirements:
#   pip install grpcio-tools mypy-protobuf pydantic-protobuf-gen

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_ROOT/src/proto"
OUTPUT_DIR="$PROJECT_ROOT/src/echomind_lib/models"

echo "=== EchoMind Proto Generation ==="
echo "Proto source: $PROTO_DIR"
echo "Output: $OUTPUT_DIR"
echo ""

# Create output directories
mkdir -p "$OUTPUT_DIR/public"
mkdir -p "$OUTPUT_DIR/internal"

# Clean ALL old generated files
echo "Cleaning old generated files..."
rm -rf "$OUTPUT_DIR"/*.py "$OUTPUT_DIR"/*.pyi "$OUTPUT_DIR"/*.json 2>/dev/null || true
rm -rf "$OUTPUT_DIR/public"/* 2>/dev/null || true
rm -rf "$OUTPUT_DIR/internal"/* 2>/dev/null || true

# Collect all proto files
COMMON_PROTO="$PROTO_DIR/common.proto"
PUBLIC_PROTOS=$(find "$PROTO_DIR/public" -name "*.proto" 2>/dev/null || true)
INTERNAL_PROTOS=$(find "$PROTO_DIR/internal" -name "*.proto" 2>/dev/null || true)
ALL_PROTOS="$COMMON_PROTO $PUBLIC_PROTOS $INTERNAL_PROTOS"

echo "Found proto files:"
for proto in $ALL_PROTOS; do
    echo "  - $(basename $proto)"
done
echo ""

# Step 1: Generate all protobuf stubs and Pydantic models
echo "Step 1: Generating protobuf stubs and Pydantic models..."
python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --pyi_out="$OUTPUT_DIR" \
    --pydantic_out="$OUTPUT_DIR" \
    $ALL_PROTOS
echo "  ✓ Generated"

# Step 2: Move public models to public/ folder
# The protoc generates files based on package name, so public/* goes to public/
# But pydantic_out puts *_model.py at root - we need to identify and move them
echo "Step 2: Organizing files into public/internal folders..."

# Get list of public proto base names (without .proto extension)
for proto in $PUBLIC_PROTOS; do
    base=$(basename "$proto" .proto)
    # Move corresponding *_model.py to public/
    if [ -f "$OUTPUT_DIR/${base}_model.py" ]; then
        mv "$OUTPUT_DIR/${base}_model.py" "$OUTPUT_DIR/public/"
    fi
done

# Get list of internal proto base names
for proto in $INTERNAL_PROTOS; do
    base=$(basename "$proto" .proto)
    # Move corresponding *_model.py to internal/
    if [ -f "$OUTPUT_DIR/${base}_model.py" ]; then
        mv "$OUTPUT_DIR/${base}_model.py" "$OUTPUT_DIR/internal/"
    fi
done

echo "  ✓ Files organized"

# Step 3: Create __init__.py files
echo "Step 3: Generating exports..."

# Public __init__.py
{
    echo '"""'
    echo 'Public API models - exposed to web/mobile clients.'
    echo ''
    echo 'DO NOT EDIT - Auto-generated from src/proto/public/'
    echo '"""'
    echo ''
    for py_file in "$OUTPUT_DIR/public"/*_model.py "$OUTPUT_DIR/public"/*_p2p.py; do
        if [ -f "$py_file" ]; then
            module=$(basename "$py_file" .py)
            echo "from .$module import *"
        fi
    done
} > "$OUTPUT_DIR/public/__init__.py"

# Internal __init__.py
{
    echo '"""'
    echo 'Internal service models - backend service-to-service only.'
    echo ''
    echo 'DO NOT EDIT - Auto-generated from src/proto/internal/'
    echo '"""'
    echo ''
    for py_file in "$OUTPUT_DIR/internal"/*_model.py "$OUTPUT_DIR/internal"/*_p2p.py; do
        if [ -f "$py_file" ]; then
            module=$(basename "$py_file" .py)
            echo "from .$module import *"
        fi
    done
} > "$OUTPUT_DIR/internal/__init__.py"

# Root __init__.py - re-exports public models for convenience
{
    echo '"""'
    echo 'Auto-generated Pydantic models from protobuf definitions.'
    echo ''
    echo 'DO NOT EDIT - This directory is auto-generated from src/proto/'
    echo 'Regenerate with: ./scripts/generate_proto.sh'
    echo ''
    echo 'Structure:'
    echo '  models/public/   - API-facing models (User, Assistant, etc.)'
    echo '  models/internal/ - Service-to-service models (SemanticData, etc.)'
    echo ''
    echo 'Usage:'
    echo '    # Public models (for API routes)'
    echo '    from echomind_lib.models.public import User, Assistant'
    echo '    '
    echo '    # Internal models (for NATS messages)'
    echo '    from echomind_lib.models.internal import SemanticData'
    echo '    '
    echo '    # Convert to protobuf for NATS'
    echo '    proto_bytes = user.to_protobuf().SerializeToString()'
    echo '"""'
    echo ''
    echo '# Re-export public models for convenience'
    echo 'from .public import *'
} > "$OUTPUT_DIR/__init__.py"

echo "  ✓ Exports generated"

echo ""
echo "=== Generation Complete ==="
echo "Public models: $(ls -1 "$OUTPUT_DIR/public"/*.py 2>/dev/null | wc -l | tr -d ' ') files"
echo "Internal models: $(ls -1 "$OUTPUT_DIR/internal"/*.py 2>/dev/null | wc -l | tr -d ' ') files"
echo ""
echo "Import in your code:"
echo "  from echomind_lib.models.public import User, Assistant"
echo "  from echomind_lib.models.internal import SemanticData"
