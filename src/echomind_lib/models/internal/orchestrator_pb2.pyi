from google.protobuf import struct_pb2 as _struct_pb2
from public import connector_pb2 as _connector_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ConnectorSyncRequest(_message.Message):
    __slots__ = ("connector_id", "type", "user_id", "scope", "scope_id", "config", "state", "chunking_session")
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    SCOPE_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    CHUNKING_SESSION_FIELD_NUMBER: _ClassVar[int]
    connector_id: int
    type: _connector_pb2.ConnectorType
    user_id: int
    scope: _connector_pb2.ConnectorScope
    scope_id: str
    config: _struct_pb2.Struct
    state: _struct_pb2.Struct
    chunking_session: str
    def __init__(self, connector_id: _Optional[int] = ..., type: _Optional[_Union[_connector_pb2.ConnectorType, str]] = ..., user_id: _Optional[int] = ..., scope: _Optional[_Union[_connector_pb2.ConnectorScope, str]] = ..., scope_id: _Optional[str] = ..., config: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., state: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., chunking_session: _Optional[str] = ...) -> None: ...

class DocumentProcessRequest(_message.Message):
    __slots__ = ("document_id", "connector_id", "user_id", "minio_path", "chunking_session", "scope", "scope_id")
    DOCUMENT_ID_FIELD_NUMBER: _ClassVar[int]
    CONNECTOR_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    MINIO_PATH_FIELD_NUMBER: _ClassVar[int]
    CHUNKING_SESSION_FIELD_NUMBER: _ClassVar[int]
    SCOPE_FIELD_NUMBER: _ClassVar[int]
    SCOPE_ID_FIELD_NUMBER: _ClassVar[int]
    document_id: int
    connector_id: int
    user_id: int
    minio_path: str
    chunking_session: str
    scope: _connector_pb2.ConnectorScope
    scope_id: str
    def __init__(self, document_id: _Optional[int] = ..., connector_id: _Optional[int] = ..., user_id: _Optional[int] = ..., minio_path: _Optional[str] = ..., chunking_session: _Optional[str] = ..., scope: _Optional[_Union[_connector_pb2.ConnectorScope, str]] = ..., scope_id: _Optional[str] = ...) -> None: ...
