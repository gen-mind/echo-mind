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
        logger.error("❌ Validation error: %s", error.message)
        error_info["should_retry"] = False
        error_info["details"]["field"] = error.field

    elif isinstance(error, DocumentNotFoundError):
        logger.error("❌ Document not found: %d", error.document_id)
        error_info["should_retry"] = False
        error_info["details"]["document_id"] = error.document_id

    elif isinstance(error, UnsupportedMimeTypeError):
        logger.error("❌ Unsupported MIME type: %s", error.mime_type)
        error_info["should_retry"] = False
        error_info["details"]["mime_type"] = error.mime_type

    # Transient errors - should retry
    elif isinstance(error, FileNotFoundInStorageError):
        # File may still be uploading
        logger.warning("⚠️ File not found (may be uploading): %s", error.file_path)
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["file_path"] = error.file_path
        error_info["details"]["bucket"] = error.bucket

    # Note: AudioExtractionError must come before ExtractionError (inheritance)
    elif isinstance(error, AudioExtractionError):
        # Riva NIM may be unavailable
        logger.warning("⚠️ Audio extraction failed (Riva NIM): %s", error.message)
        error_info["should_retry"] = True
        error_info["retry_after"] = 30.0

    elif isinstance(error, ExtractionError):
        if error.is_transient:
            logger.warning("⚠️ Transient extraction error: %s", error.message)
            error_info["should_retry"] = True
            error_info["retry_after"] = 10.0
        else:
            logger.error("❌ Terminal extraction error: %s", error.message)
            error_info["should_retry"] = False
        error_info["details"]["source_type"] = error.source_type
        error_info["details"]["document_id"] = error.document_id

    elif isinstance(error, ChunkingError):
        if error.is_transient:
            # Tokenizer may need download
            logger.warning("⚠️ Chunking error (transient): %s", error.message)
            error_info["should_retry"] = True
            error_info["retry_after"] = 5.0
        else:
            logger.error("❌ Chunking error (terminal): %s", error.message)
            error_info["should_retry"] = False
        error_info["details"]["document_id"] = error.document_id

    elif isinstance(error, EmbeddingError):
        # Embedder service may be overloaded
        logger.warning("⚠️ Embedding error: %s", error.message)
        error_info["should_retry"] = True
        error_info["retry_after"] = 10.0
        error_info["details"]["document_id"] = error.document_id
        error_info["details"]["chunk_index"] = error.chunk_index

    elif isinstance(error, MinioError):
        logger.warning("⚠️ MinIO error in %s: %s", error.operation, error.reason)
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["operation"] = error.operation

    elif isinstance(error, DatabaseError):
        logger.warning("⚠️ Database error in %s: %s", error.operation, error.reason)
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["operation"] = error.operation

    elif isinstance(error, GrpcError):
        logger.warning("⚠️ gRPC error to %s: %s", error.service, error.reason)
        error_info["should_retry"] = True
        error_info["retry_after"] = 10.0
        error_info["details"]["service"] = error.service
        error_info["details"]["code"] = error.code

    elif isinstance(error, NatsError):
        logger.warning("⚠️ NATS error in %s: %s", error.operation, error.reason)
        error_info["should_retry"] = True
        error_info["retry_after"] = 5.0
        error_info["details"]["operation"] = error.operation

    else:
        # Unknown IngestorError - retry by default
        logger.error("❌ Unknown ingestor error: %s", error.message)
        error_info["should_retry"] = True
        error_info["retry_after"] = 30.0

    return error_info
