"""
MIME type routing for document processing.

Maps all 18 supported file types to appropriate extractors.
Based on nv-ingest README.md file type support.
"""


class MimeRouter:
    """
    Routes content by MIME type to appropriate extractor.

    Supports 18 file types as documented in nv-ingest README:
    - Documents: PDF, DOCX, PPTX
    - HTML: HTML files
    - Images: BMP, JPEG, PNG, TIFF
    - Audio: MP3, WAV
    - Video: AVI, MKV, MOV, MP4 (early access)
    - Text: TXT, MD, JSON, SH
    """

    # MIME type to (document_type, extractor_type) mapping
    MIME_MAP: dict[str, tuple[str, str]] = {
        # Documents
        "application/pdf": ("pdf", "pdf"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            "docx",
            "docx",
        ),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
            "pptx",
            "pptx",
        ),

        # HTML
        "text/html": ("html", "html"),

        # Images
        "image/bmp": ("bmp", "image"),
        "image/jpeg": ("jpeg", "image"),
        "image/jpg": ("jpeg", "image"),
        "image/png": ("png", "image"),
        "image/tiff": ("tiff", "image"),

        # Audio
        "audio/mpeg": ("mp3", "audio"),
        "audio/mp3": ("mp3", "audio"),
        "audio/wav": ("wav", "audio"),
        "audio/x-wav": ("wav", "audio"),
        "audio/wave": ("wav", "audio"),

        # Video (early access)
        "video/mp4": ("mp4", "video"),
        "video/x-msvideo": ("avi", "video"),
        "video/x-matroska": ("mkv", "video"),
        "video/quicktime": ("mov", "video"),

        # Text files
        "text/plain": ("txt", "text"),
        "text/markdown": ("md", "text"),
        "application/json": ("json", "text"),
        "application/x-sh": ("sh", "text"),
        "text/x-shellscript": ("sh", "text"),
    }

    def is_supported(self, mime_type: str) -> bool:
        """
        Check if MIME type is supported.

        Args:
            mime_type: MIME type to check.

        Returns:
            True if supported, False otherwise.
        """
        return mime_type.lower() in self.MIME_MAP

    def get_document_type(self, mime_type: str) -> str:
        """
        Get document type for MIME type.

        Args:
            mime_type: MIME type.

        Returns:
            Document type string (pdf, docx, etc).

        Raises:
            KeyError: If MIME type not supported.
        """
        return self.MIME_MAP[mime_type.lower()][0]

    def get_extractor_type(self, mime_type: str) -> str:
        """
        Get extractor type for MIME type.

        Args:
            mime_type: MIME type.

        Returns:
            Extractor type (pdf, docx, image, audio, etc).

        Raises:
            KeyError: If MIME type not supported.
        """
        return self.MIME_MAP[mime_type.lower()][1]

    def get_supported_mime_types(self) -> list[str]:
        """
        Get list of all supported MIME types.

        Returns:
            List of MIME type strings.
        """
        return list(self.MIME_MAP.keys())

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of all supported file extensions.

        Returns:
            List of extension strings (without dot).
        """
        return list(set(doc_type for doc_type, _ in self.MIME_MAP.values()))

    def get_extractor_for_extension(self, extension: str) -> str | None:
        """
        Get extractor type for file extension.

        Args:
            extension: File extension (with or without dot).

        Returns:
            Extractor type or None if not supported.
        """
        ext = extension.lower().lstrip(".")
        for doc_type, extractor_type in self.MIME_MAP.values():
            if doc_type == ext:
                return extractor_type
        return None
