from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PaginationRequest(_message.Message):
    __slots__ = ("page", "limit")
    PAGE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    page: int
    limit: int
    def __init__(self, page: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class PaginationResponse(_message.Message):
    __slots__ = ("page", "limit", "total", "pages")
    PAGE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    PAGES_FIELD_NUMBER: _ClassVar[int]
    page: int
    limit: int
    total: int
    pages: int
    def __init__(self, page: _Optional[int] = ..., limit: _Optional[int] = ..., total: _Optional[int] = ..., pages: _Optional[int] = ...) -> None: ...

class FieldError(_message.Message):
    __slots__ = ("field", "message")
    FIELD_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    field: str
    message: str
    def __init__(self, field: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class ErrorResponse(_message.Message):
    __slots__ = ("code", "message", "details")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    details: _containers.RepeatedCompositeFieldContainer[FieldError]
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ..., details: _Optional[_Iterable[_Union[FieldError, _Mapping]]] = ...) -> None: ...

class AuditInfo(_message.Message):
    __slots__ = ("creation_date", "last_update", "user_id_last_update")
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    USER_ID_LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    creation_date: _timestamp_pb2.Timestamp
    last_update: _timestamp_pb2.Timestamp
    user_id_last_update: int
    def __init__(self, creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_update: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., user_id_last_update: _Optional[int] = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class IdRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class SuccessResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...
