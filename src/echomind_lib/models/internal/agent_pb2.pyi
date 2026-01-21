from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MemoryType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MEMORY_TYPE_UNSPECIFIED: _ClassVar[MemoryType]
    MEMORY_TYPE_EPISODIC: _ClassVar[MemoryType]
    MEMORY_TYPE_SEMANTIC: _ClassVar[MemoryType]
    MEMORY_TYPE_PROCEDURAL: _ClassVar[MemoryType]
MEMORY_TYPE_UNSPECIFIED: MemoryType
MEMORY_TYPE_EPISODIC: MemoryType
MEMORY_TYPE_SEMANTIC: MemoryType
MEMORY_TYPE_PROCEDURAL: MemoryType

class AgentMemory(_message.Message):
    __slots__ = ("id", "user_id", "memory_type", "content", "embedding_id", "importance_score", "access_count")
    ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    MEMORY_TYPE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_ID_FIELD_NUMBER: _ClassVar[int]
    IMPORTANCE_SCORE_FIELD_NUMBER: _ClassVar[int]
    ACCESS_COUNT_FIELD_NUMBER: _ClassVar[int]
    id: int
    user_id: int
    memory_type: MemoryType
    content: str
    embedding_id: str
    importance_score: float
    access_count: int
    def __init__(self, id: _Optional[int] = ..., user_id: _Optional[int] = ..., memory_type: _Optional[_Union[MemoryType, str]] = ..., content: _Optional[str] = ..., embedding_id: _Optional[str] = ..., importance_score: _Optional[float] = ..., access_count: _Optional[int] = ...) -> None: ...

class ToolCall(_message.Message):
    __slots__ = ("tool_name", "parameters", "result", "duration_ms")
    TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    tool_name: str
    parameters: _struct_pb2.Struct
    result: _struct_pb2.Struct
    duration_ms: int
    def __init__(self, tool_name: _Optional[str] = ..., parameters: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., result: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., duration_ms: _Optional[int] = ...) -> None: ...

class PlanStep(_message.Message):
    __slots__ = ("action", "description", "completed", "result")
    ACTION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    action: str
    description: str
    completed: bool
    result: _struct_pb2.Struct
    def __init__(self, action: _Optional[str] = ..., description: _Optional[str] = ..., completed: bool = ..., result: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class AgentRequest(_message.Message):
    __slots__ = ("session_id", "user_id", "query", "relevant_memories")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    RELEVANT_MEMORIES_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    user_id: int
    query: str
    relevant_memories: _containers.RepeatedCompositeFieldContainer[AgentMemory]
    def __init__(self, session_id: _Optional[int] = ..., user_id: _Optional[int] = ..., query: _Optional[str] = ..., relevant_memories: _Optional[_Iterable[_Union[AgentMemory, _Mapping]]] = ...) -> None: ...

class AgentResponse(_message.Message):
    __slots__ = ("response", "tool_calls", "plan", "tokens_used")
    RESPONSE_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALLS_FIELD_NUMBER: _ClassVar[int]
    PLAN_FIELD_NUMBER: _ClassVar[int]
    TOKENS_USED_FIELD_NUMBER: _ClassVar[int]
    response: str
    tool_calls: _containers.RepeatedCompositeFieldContainer[ToolCall]
    plan: _containers.RepeatedCompositeFieldContainer[PlanStep]
    tokens_used: int
    def __init__(self, response: _Optional[str] = ..., tool_calls: _Optional[_Iterable[_Union[ToolCall, _Mapping]]] = ..., plan: _Optional[_Iterable[_Union[PlanStep, _Mapping]]] = ..., tokens_used: _Optional[int] = ...) -> None: ...
