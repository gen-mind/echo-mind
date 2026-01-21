"""
Auto-generated Pydantic models from protobuf definitions.

DO NOT EDIT - This directory is auto-generated from src/proto/
Regenerate with: ./scripts/generate_proto.sh

Structure:
  models/public/   - API-facing models (User, Assistant, etc.)
  models/internal/ - Service-to-service models (SemanticData, etc.)

Usage:
    # Public models (for API routes)
    from echomind_lib.models.public import User, Assistant
    
    # Internal models (for NATS messages)
    from echomind_lib.models.internal import SemanticData
    
    # Convert to protobuf for NATS
    proto_bytes = user.to_protobuf().SerializeToString()
"""

# Re-export public models for convenience
from .public import *
