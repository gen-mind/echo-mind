from google.protobuf import timestamp_pb2 as _timestamp_pb2
import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DocumentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DOCUMENT_STATUS_UNSPECIFIED: _ClassVar[DocumentStatus]
    DOCUMENT_STATUS_PENDING: _ClassVar[DocumentStatus]
    DOCUMENT_STATUS_PROCESSING: _ClassVar[DocumentStatus]
    DOCUMENT_STATUS_COMPLETED: _ClassVar[DocumentStatus]
    DOCUMENT_STATUS_FAILED: _ClassVar[DocumentStatus]
DOCUMENT_STATUS_UNSPECIFIED: DocumentStatus
DOCUMENT_STATUS_PENDING: DocumentStatus
DOCUMENT_STATUS_PROCESSING: DocumentStatus
DOCUMENT_STATUS_COMPLETED: DocumentStatus
DOCUMENT_STATUS_FAILED: DocumentStatus

class Document(_message.Message):
    __slots__ = ("id", "parent_id", "connector_id", "source_id", "url", "original_url", "title", "content_type", "status", "status_message", "chunk_count", "creation_date", "last_update")
    ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_ID_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    ORIGINAL_URL_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STATUS_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    id: int
    parent_id: int
    connector_id: int
    source_id: str
    url: str
    original_url: str
    title: str
    content_type: str
    status: DocumentStatus
    status_message: str
    chunk_count: int
    creation_date: _timestamp_pb2.Timestamp
    last_update: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., parent_id: _Optional[int] = ..., connector_id: _Optional[int] = ..., source_id: _Optional[str] = ..., url: _Optional[str] = ..., original_url: _Optional[str] = ..., title: _Optional[str] = ..., content_type: _Optional[str] = ..., status: _Optional[_Union[DocumentStatus, str]] = ..., status_message: _Optional[str] = ..., chunk_count: _Optional[int] = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_update: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ListDocumentsRequest(_message.Message):
    __slots__ = ("pagination", "connector_id", "status")
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    pagination: _common_pb2.PaginationRequest
    connector_id: int
    status: DocumentStatus
    def __init__(self, pagination: _Optional[_Union[_common_pb2.PaginationRequest, _Mapping]] = ..., connector_id: _Optional[int] = ..., status: _Optional[_Union[DocumentStatus, str]] = ...) -> None: ...

class ListDocumentsResponse(_message.Message):
    __slots__ = ("documents", "pagination")
    DOCUMENTS_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    documents: _containers.RepeatedCompositeFieldContainer[Document]
    pagination: _common_pb2.PaginationResponse
    def __init__(self, documents: _Optional[_Iterable[_Union[Document, _Mapping]]] = ..., pagination: _Optional[_Union[_common_pb2.PaginationResponse, _Mapping]] = ...) -> None: ...

class GetDocumentResponse(_message.Message):
    __slots__ = ("document",)
    DOCUMENT_FIELD_NUMBER: _ClassVar[int]
    document: Document
    def __init__(self, document: _Optional[_Union[Document, _Mapping]] = ...) -> None: ...

class SearchDocumentsRequest(_message.Message):
    __slots__ = ("query", "connector_id", "limit", "min_score")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    MIN_SCORE_FIELD_NUMBER: _ClassVar[int]
    query: str
    connector_id: int
    limit: int
    min_score: float
    def __init__(self, query: _Optional[str] = ..., connector_id: _Optional[int] = ..., limit: _Optional[int] = ..., min_score: _Optional[float] = ...) -> None: ...

class DocumentSearchResult(_message.Message):
    __slots__ = ("document", "chunk_id", "chunk_content", "score")
    DOCUMENT_FIELD_NUMBER: _ClassVar[int]
    CHUNK_ID_FIELD_NUMBER: _ClassVar[int]
    CHUNK_CONTENT_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    document: Document
    chunk_id: str
    chunk_content: str
    score: float
    def __init__(self, document: _Optional[_Union[Document, _Mapping]] = ..., chunk_id: _Optional[str] = ..., chunk_content: _Optional[str] = ..., score: _Optional[float] = ...) -> None: ...

class SearchDocumentsResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[DocumentSearchResult]
    def __init__(self, results: _Optional[_Iterable[_Union[DocumentSearchResult, _Mapping]]] = ...) -> None: ...
