from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SandboxStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SANDBOX_STATUS_UNSPECIFIED: _ClassVar[SandboxStatus]
    SANDBOX_STATUS_WARM: _ClassVar[SandboxStatus]
    SANDBOX_STATUS_ASSIGNED: _ClassVar[SandboxStatus]
    SANDBOX_STATUS_ACTIVE: _ClassVar[SandboxStatus]
    SANDBOX_STATUS_DRAINING: _ClassVar[SandboxStatus]
    SANDBOX_STATUS_DESTROYED: _ClassVar[SandboxStatus]

class SandboxEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SANDBOX_EVENT_TYPE_UNSPECIFIED: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_CREATED: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_ASSIGNED: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_ACTIVATED: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_MESSAGE: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_TOOL_CALL: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_DRAINING: _ClassVar[SandboxEventType]
    SANDBOX_EVENT_TYPE_DESTROYED: _ClassVar[SandboxEventType]
SANDBOX_STATUS_UNSPECIFIED: SandboxStatus
SANDBOX_STATUS_WARM: SandboxStatus
SANDBOX_STATUS_ASSIGNED: SandboxStatus
SANDBOX_STATUS_ACTIVE: SandboxStatus
SANDBOX_STATUS_DRAINING: SandboxStatus
SANDBOX_STATUS_DESTROYED: SandboxStatus
SANDBOX_EVENT_TYPE_UNSPECIFIED: SandboxEventType
SANDBOX_EVENT_TYPE_CREATED: SandboxEventType
SANDBOX_EVENT_TYPE_ASSIGNED: SandboxEventType
SANDBOX_EVENT_TYPE_ACTIVATED: SandboxEventType
SANDBOX_EVENT_TYPE_MESSAGE: SandboxEventType
SANDBOX_EVENT_TYPE_TOOL_CALL: SandboxEventType
SANDBOX_EVENT_TYPE_DRAINING: SandboxEventType
SANDBOX_EVENT_TYPE_DESTROYED: SandboxEventType

class SandboxSession(_message.Message):
    __slots__ = ("id", "session_id", "user_id", "chat_session_id", "container_id", "container_name", "status", "assigned_at", "activated_at", "destroyed_at", "agent_config", "message_count", "tool_calls_count", "total_tokens", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CONTAINER_ID_FIELD_NUMBER: _ClassVar[int]
    CONTAINER_NAME_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_AT_FIELD_NUMBER: _ClassVar[int]
    ACTIVATED_AT_FIELD_NUMBER: _ClassVar[int]
    DESTROYED_AT_FIELD_NUMBER: _ClassVar[int]
    AGENT_CONFIG_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALLS_COUNT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_TOKENS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    session_id: str
    user_id: int
    chat_session_id: int
    container_id: str
    container_name: str
    status: SandboxStatus
    assigned_at: _timestamp_pb2.Timestamp
    activated_at: _timestamp_pb2.Timestamp
    destroyed_at: _timestamp_pb2.Timestamp
    agent_config: _struct_pb2.Struct
    message_count: int
    tool_calls_count: int
    total_tokens: int
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., session_id: _Optional[str] = ..., user_id: _Optional[int] = ..., chat_session_id: _Optional[int] = ..., container_id: _Optional[str] = ..., container_name: _Optional[str] = ..., status: _Optional[_Union[SandboxStatus, str]] = ..., assigned_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., activated_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., destroyed_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., agent_config: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., message_count: _Optional[int] = ..., tool_calls_count: _Optional[int] = ..., total_tokens: _Optional[int] = ..., created_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SandboxEvent(_message.Message):
    __slots__ = ("id", "sandbox_session_id", "event_type", "event_data", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SANDBOX_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    EVENT_DATA_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    sandbox_session_id: str
    event_type: SandboxEventType
    event_data: _struct_pb2.Struct
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., sandbox_session_id: _Optional[str] = ..., event_type: _Optional[_Union[SandboxEventType, str]] = ..., event_data: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., created_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
