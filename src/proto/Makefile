# Proto compilation Makefile
# Generates Python and TypeScript types from .proto files

PROTO_DIR := .
PUBLIC_DIR := public
INTERNAL_DIR := internal
PYTHON_OUT := ../echomind_lib/models
TS_OUT := ../../web/src/gen_types

# Proto compiler
PROTOC := protoc

# Python plugins
PYTHON_GRPC := grpc_tools.protoc
PYDANTIC_PLUGIN := pydantic-protobuf-gen

.PHONY: all clean python typescript pydantic

all: python

# Generate Python protobuf stubs + Pydantic models
python:
	@echo "Generating Python protobuf and Pydantic models..."
	@mkdir -p $(PYTHON_OUT)
	python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=$(PYTHON_OUT) \
		--pyi_out=$(PYTHON_OUT) \
		--pydantic_out=$(PYTHON_OUT) \
		$(PROTO_DIR)/common.proto \
		$(PUBLIC_DIR)/*.proto \
		$(INTERNAL_DIR)/*.proto
	@echo "Python protobuf and Pydantic models generated in $(PYTHON_OUT)"

# Generate TypeScript types (for web client)
typescript:
	@echo "Generating TypeScript types..."
	@mkdir -p $(TS_OUT)
	$(PROTOC) \
		-I$(PROTO_DIR) \
		-I$(PUBLIC_DIR) \
		--plugin=protoc-gen-ts=$(shell which protoc-gen-ts) \
		--ts_out=$(TS_OUT) \
		$(PUBLIC_DIR)/*.proto
	@echo "TypeScript types generated in $(TS_OUT)"

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	rm -rf $(PYTHON_OUT)/*.py $(PYTHON_OUT)/*.pyi
	rm -rf $(TS_OUT)/*.ts
	@echo "Clean complete"

# Install dependencies for proto generation
install-deps:
	pip install grpcio-tools protobuf
	# For TypeScript generation:
	# npm install -g ts-protoc-gen
