"""Unit tests for MIME type routing."""

import pytest

from ingestor.logic.mime_router import MimeRouter


class TestMimeRouter:
    """Tests for MimeRouter class."""

    def setup_method(self) -> None:
        """Create router instance for each test."""
        self.router = MimeRouter()

    # ==========================================
    # is_supported tests
    # ==========================================

    def test_is_supported_pdf(self) -> None:
        """Test PDF MIME type is supported."""
        assert self.router.is_supported("application/pdf") is True

    def test_is_supported_docx(self) -> None:
        """Test DOCX MIME type is supported."""
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert self.router.is_supported(mime) is True

    def test_is_supported_pptx(self) -> None:
        """Test PPTX MIME type is supported."""
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert self.router.is_supported(mime) is True

    def test_is_supported_html(self) -> None:
        """Test HTML MIME type is supported."""
        assert self.router.is_supported("text/html") is True

    def test_is_supported_images(self) -> None:
        """Test image MIME types are supported."""
        image_types = ["image/bmp", "image/jpeg", "image/jpg", "image/png", "image/tiff"]
        for mime in image_types:
            assert self.router.is_supported(mime) is True, f"{mime} should be supported"

    def test_is_supported_audio(self) -> None:
        """Test audio MIME types are supported."""
        audio_types = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave"]
        for mime in audio_types:
            assert self.router.is_supported(mime) is True, f"{mime} should be supported"

    def test_is_supported_video(self) -> None:
        """Test video MIME types are supported."""
        video_types = ["video/mp4", "video/x-msvideo", "video/x-matroska", "video/quicktime"]
        for mime in video_types:
            assert self.router.is_supported(mime) is True, f"{mime} should be supported"

    def test_is_supported_text(self) -> None:
        """Test text MIME types are supported."""
        text_types = [
            "text/plain",
            "text/markdown",
            "application/json",
            "application/x-sh",
            "text/x-shellscript",
        ]
        for mime in text_types:
            assert self.router.is_supported(mime) is True, f"{mime} should be supported"

    def test_is_supported_unsupported(self) -> None:
        """Test unsupported MIME types return False."""
        unsupported = [
            "application/x-unknown",
            "video/webm",
            "audio/ogg",
            "application/zip",
            "image/svg+xml",
        ]
        for mime in unsupported:
            assert self.router.is_supported(mime) is False, f"{mime} should NOT be supported"

    def test_is_supported_case_insensitive(self) -> None:
        """Test MIME type matching is case insensitive."""
        assert self.router.is_supported("APPLICATION/PDF") is True
        assert self.router.is_supported("Image/JPEG") is True
        assert self.router.is_supported("TEXT/Plain") is True

    # ==========================================
    # get_document_type tests
    # ==========================================

    def test_get_document_type_pdf(self) -> None:
        """Test document type for PDF."""
        assert self.router.get_document_type("application/pdf") == "pdf"

    def test_get_document_type_docx(self) -> None:
        """Test document type for DOCX."""
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert self.router.get_document_type(mime) == "docx"

    def test_get_document_type_images(self) -> None:
        """Test document types for images."""
        assert self.router.get_document_type("image/jpeg") == "jpeg"
        assert self.router.get_document_type("image/jpg") == "jpeg"  # Both map to jpeg
        assert self.router.get_document_type("image/png") == "png"
        assert self.router.get_document_type("image/bmp") == "bmp"
        assert self.router.get_document_type("image/tiff") == "tiff"

    def test_get_document_type_audio(self) -> None:
        """Test document types for audio."""
        assert self.router.get_document_type("audio/mpeg") == "mp3"
        assert self.router.get_document_type("audio/mp3") == "mp3"
        assert self.router.get_document_type("audio/wav") == "wav"

    def test_get_document_type_video(self) -> None:
        """Test document types for video."""
        assert self.router.get_document_type("video/mp4") == "mp4"
        assert self.router.get_document_type("video/x-msvideo") == "avi"
        assert self.router.get_document_type("video/x-matroska") == "mkv"
        assert self.router.get_document_type("video/quicktime") == "mov"

    def test_get_document_type_text(self) -> None:
        """Test document types for text files."""
        assert self.router.get_document_type("text/plain") == "txt"
        assert self.router.get_document_type("text/markdown") == "md"
        assert self.router.get_document_type("application/json") == "json"
        assert self.router.get_document_type("application/x-sh") == "sh"

    def test_get_document_type_unsupported_raises(self) -> None:
        """Test unsupported MIME type raises KeyError."""
        with pytest.raises(KeyError):
            self.router.get_document_type("application/x-unknown")

    def test_get_document_type_case_insensitive(self) -> None:
        """Test document type lookup is case insensitive."""
        assert self.router.get_document_type("APPLICATION/PDF") == "pdf"

    # ==========================================
    # get_extractor_type tests
    # ==========================================

    def test_get_extractor_type_pdf(self) -> None:
        """Test extractor type for PDF."""
        assert self.router.get_extractor_type("application/pdf") == "pdf"

    def test_get_extractor_type_docx(self) -> None:
        """Test extractor type for DOCX."""
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert self.router.get_extractor_type(mime) == "docx"

    def test_get_extractor_type_pptx(self) -> None:
        """Test extractor type for PPTX."""
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        assert self.router.get_extractor_type(mime) == "pptx"

    def test_get_extractor_type_html(self) -> None:
        """Test extractor type for HTML."""
        assert self.router.get_extractor_type("text/html") == "html"

    def test_get_extractor_type_images_all_same(self) -> None:
        """Test all image MIME types use 'image' extractor."""
        image_types = ["image/bmp", "image/jpeg", "image/png", "image/tiff"]
        for mime in image_types:
            assert self.router.get_extractor_type(mime) == "image"

    def test_get_extractor_type_audio_all_same(self) -> None:
        """Test all audio MIME types use 'audio' extractor."""
        audio_types = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"]
        for mime in audio_types:
            assert self.router.get_extractor_type(mime) == "audio"

    def test_get_extractor_type_video_all_same(self) -> None:
        """Test all video MIME types use 'video' extractor."""
        video_types = ["video/mp4", "video/x-msvideo", "video/x-matroska"]
        for mime in video_types:
            assert self.router.get_extractor_type(mime) == "video"

    def test_get_extractor_type_text_all_same(self) -> None:
        """Test all text MIME types use 'text' extractor."""
        text_types = ["text/plain", "text/markdown", "application/json", "application/x-sh"]
        for mime in text_types:
            assert self.router.get_extractor_type(mime) == "text"

    def test_get_extractor_type_unsupported_raises(self) -> None:
        """Test unsupported MIME type raises KeyError."""
        with pytest.raises(KeyError):
            self.router.get_extractor_type("application/zip")

    # ==========================================
    # get_supported_mime_types tests
    # ==========================================

    def test_get_supported_mime_types_count(self) -> None:
        """Test supported MIME types includes all 18+ types."""
        mime_types = self.router.get_supported_mime_types()
        # Should have at least 18 types per nv-ingest docs
        # (some types have multiple MIME aliases)
        assert len(mime_types) >= 18

    def test_get_supported_mime_types_returns_list(self) -> None:
        """Test get_supported_mime_types returns a list."""
        result = self.router.get_supported_mime_types()
        assert isinstance(result, list)

    def test_get_supported_mime_types_includes_all_categories(self) -> None:
        """Test supported MIME types includes all categories."""
        mime_types = self.router.get_supported_mime_types()

        # Should include at least one from each category
        assert "application/pdf" in mime_types
        assert "text/html" in mime_types
        assert any(m.startswith("image/") for m in mime_types)
        assert any(m.startswith("audio/") for m in mime_types)
        assert any(m.startswith("video/") for m in mime_types)
        assert "text/plain" in mime_types

    # ==========================================
    # get_supported_extensions tests
    # ==========================================

    def test_get_supported_extensions_returns_list(self) -> None:
        """Test get_supported_extensions returns a list."""
        result = self.router.get_supported_extensions()
        assert isinstance(result, list)

    def test_get_supported_extensions_no_duplicates(self) -> None:
        """Test supported extensions have no duplicates."""
        extensions = self.router.get_supported_extensions()
        assert len(extensions) == len(set(extensions))

    def test_get_supported_extensions_includes_common_types(self) -> None:
        """Test supported extensions includes common file types."""
        extensions = self.router.get_supported_extensions()

        expected = ["pdf", "docx", "pptx", "html", "txt", "md", "json"]
        for ext in expected:
            assert ext in extensions, f"{ext} should be a supported extension"

    # ==========================================
    # get_extractor_for_extension tests
    # ==========================================

    def test_get_extractor_for_extension_pdf(self) -> None:
        """Test extractor for PDF extension."""
        assert self.router.get_extractor_for_extension("pdf") == "pdf"
        assert self.router.get_extractor_for_extension(".pdf") == "pdf"

    def test_get_extractor_for_extension_docx(self) -> None:
        """Test extractor for DOCX extension."""
        assert self.router.get_extractor_for_extension("docx") == "docx"

    def test_get_extractor_for_extension_images(self) -> None:
        """Test extractor for image extensions."""
        # Note: jpg maps to jpeg doc_type, so only jpeg/png/bmp/tiff work
        # The extension lookup finds by doc_type, not MIME alias
        for ext in ["jpeg", "png", "bmp", "tiff"]:
            result = self.router.get_extractor_for_extension(ext)
            assert result == "image", f"{ext} should use image extractor"

        # jpg is not a doc_type (jpeg is), so returns None
        result = self.router.get_extractor_for_extension("jpg")
        assert result is None  # jpg maps to jpeg doc_type, not found by "jpg"

    def test_get_extractor_for_extension_case_insensitive(self) -> None:
        """Test extension lookup is case insensitive."""
        assert self.router.get_extractor_for_extension("PDF") == "pdf"
        assert self.router.get_extractor_for_extension(".PDF") == "pdf"

    def test_get_extractor_for_extension_unknown(self) -> None:
        """Test unknown extension returns None."""
        assert self.router.get_extractor_for_extension("xyz") is None
        assert self.router.get_extractor_for_extension(".unknown") is None


class TestMimeMapCompleteness:
    """Tests for MIME_MAP completeness."""

    def setup_method(self) -> None:
        """Create router instance."""
        self.router = MimeRouter()

    def test_mime_map_has_all_18_file_types(self) -> None:
        """Test MIME_MAP supports all 18 nv-ingest file types."""
        # From nv-ingest README:
        # Documents: PDF, DOCX, PPTX
        # HTML: HTML
        # Images: BMP, JPEG, PNG, TIFF
        # Audio: MP3, WAV
        # Video: AVI, MKV, MOV, MP4
        # Text: TXT, MD, JSON, SH

        expected_doc_types = {
            "pdf", "docx", "pptx",  # Documents
            "html",  # HTML
            "bmp", "jpeg", "png", "tiff",  # Images
            "mp3", "wav",  # Audio
            "avi", "mkv", "mov", "mp4",  # Video
            "txt", "md", "json", "sh",  # Text
        }

        extensions = set(self.router.get_supported_extensions())

        for doc_type in expected_doc_types:
            assert doc_type in extensions, f"{doc_type} should be supported"

    def test_all_mime_map_entries_have_two_values(self) -> None:
        """Test all MIME_MAP entries have (doc_type, extractor_type) tuple."""
        for mime, value in self.router.MIME_MAP.items():
            assert isinstance(value, tuple), f"{mime} should map to tuple"
            assert len(value) == 2, f"{mime} tuple should have 2 values"
            assert isinstance(value[0], str), f"{mime} doc_type should be str"
            assert isinstance(value[1], str), f"{mime} extractor_type should be str"
