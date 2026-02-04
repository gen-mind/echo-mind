"""
Error handling middleware for the Ingestor Service.

Converts domain exceptions to structured error information
with retry guidance for NATS message handling.
"""

import logging
from typing import Any

from ingestor.logic.exceptions import (
    AudioExtractionError,
    ChunkingError,
    DatabaseError,
    DocumentNotFoundError,
    EmbeddingError,
    ExtractionError,
    FileNotFoundInStorageError,
    GrpcError,
    IngestorError,
    MinioError,
    NatsError,
    OwnershipMismatchError,
    UnsupportedMimeTypeError,
    ValidationError,
)

logger = logging.getLogger("echomind-ingestor.error_handler")


async def handle_ingestor_error(error: IngestorError) -> dict[str, Any]:
    """
    Handle Ingestor errors and return structured error information.

    Determines whether the error is retryable and provides
    guidance for NATS message handling (ack, nak, term).

    Args:
        error: The IngestorError to handle.

    Returns:
        Dictionary containing:
        - error_type: Exception class name
        - message: Human-readable error message
        - should_retry: Whether NATS should redeliver
        - retry_after: Optional delay before retry (seconds)
        - details: Additional error-specific details
    """
    error_info: dict[str, Any] = {
        "error_type": type(error).__name__,
        "message": error.message,
        "should_retry": False,
        "retry_after": None,
        "details": {},
    }

    # Terminal errors - don't retry
    if isinstance(error, ValidationError):
        logger.error(f"❌ Validation error: {error.message}")
        error_info["should_retry"] = False
        error_info["details"]["field"] = error.field

    elif isinstance(error, DocumentNotFoundError):
        logger.error(f"❌ Document not found: {error.document_id}")
        error_info["should_retry"] = False
        error_info["details"]["document_id"] = error.document_id

    elif isinstance(error, OwnershipMismatchError):
        # SECURITY: Never retry - indicates forged or corrupted message
        logger.critical(
            f"🚨 SECURITY: Ownership mismatch detected! Document {error.document_id} - "
            f"claimed connector={error.expected_connector_id} (actual={error.actual_connector_id}), "
            f"claimed user={error.expected_user_id} (actual={error.actual_user_id})"
        )
        error_info["should_retry"] = False
        error_info["details"]["document_id"] = error.document_id
        error_info["details"]["claimed_connector_id"] = error.expected_connector_id
        error_info["details"]["actual_connector_id"] = error.actual_connector_id
        error_info["details"]["claimed_user_id"] = error.expected_user_id
        error_info["details"]["actual_user_id"] = error.actual_user_id
        error_info["details"]["security_alert"] = True

    elif isinstance(error, UnsupportedMimeTypeError):
        logger.error(f"❌ Unsupported MIME type: {error.mime_type}")
        error_info["should_retry"] = False
        error_info["details"]["mime_type"] = error.mime_type

    # Transient errors - should retry
    elif isinstance(error, FileNotFoundInStorageError):
        # File may still be uploading
        logger.warning(f"⚠️ File not found (may be uploading): {error.file_path}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["file_path"] = error.file_path
        error_info["details"]["bucket"] = error.bucket

    # Note: AudioExtractionError must come before ExtractionError (inheritance)
    elif isinstance(error, AudioExtractionError):
        # Riva NIM may be unavailable
        logger.warning(f"⚠️ Audio extraction failed (Riva NIM): {error.message}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 30.0

    elif isinstance(error, ExtractionError):
        if error.is_transient:
            logger.warning(f"⚠️ Transient extraction error: {error.message}")
            error_info["should_retry"] = True
            error_info["retry_after"] = 10.0
        else:
            logger.error(f"❌ Terminal extraction error: {error.message}")
            error_info["should_retry"] = False
        error_info["details"]["source_type"] = error.source_type
        error_info["details"]["document_id"] = error.document_id

    elif isinstance(error, ChunkingError):
        if error.is_transient:
            # Tokenizer may need download
            logger.warning(f"⚠️ Chunking error (transient): {error.message}")
            error_info["should_retry"] = True
            error_info["retry_after"] = 5.0
        else:
            logger.error(f"❌ Chunking error (terminal): {error.message}")
            error_info["should_retry"] = False
        error_info["details"]["document_id"] = error.document_id

    elif isinstance(error, EmbeddingError):
        # Embedder service may be overloaded
        logger.warning(f"⚠️ Embedding error: {error.message}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 10.0
        error_info["details"]["document_id"] = error.document_id
        error_info["details"]["chunk_index"] = error.chunk_index

    elif isinstance(error, MinioError):
        logger.warning(f"⚠️ MinIO error in {error.operation}: {error.reason}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["operation"] = error.operation

    elif isinstance(error, DatabaseError):
        logger.warning(f"⚠️ Database error in {error.operation}: {error.reason}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["operation"] = error.operation

    elif isinstance(error, GrpcError):
        logger.warning(f"⚠️ gRPC error to {error.service}: {error.reason}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 10.0
        error_info["details"]["service"] = error.service
        error_info["details"]["code"] = error.code

    elif isinstance(error, NatsError):
        logger.warning(f"⚠️ NATS error in {error.operation}: {error.reason}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["operation"] = error.operation

    else:
        # Unknown IngestorError - retry by default
        logger.error(f"❌ Unknown ingestor error: {error.message}")
        error_info["should_retry"] = True
        error_info["retry_after"] = 30.0

    return error_info
