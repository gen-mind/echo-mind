"""
Business logic for the Ingestor service.

Protocol-agnostic logic for document extraction, chunking, and embedding.

Note: Imports are intentionally not included here to avoid loading heavy
dependencies (pandas, nv_ingest_api) during test collection. Import directly
from submodules:

    from ingestor.logic.exceptions import ValidationError
    from ingestor.logic.mime_router import MimeRouter
    from ingestor.logic.document_processor import DocumentProcessor
    from ingestor.logic.ingestor_service import IngestorService
"""
