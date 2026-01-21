from google.protobuf import timestamp_pb2 as _timestamp_pb2
import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Assistant(_message.Message):
    __slots__ = ("id", "name", "description", "llm_id", "system_prompt", "task_prompt", "starter_messages", "is_default", "is_visible", "display_priority", "created_by", "creation_date", "last_update")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LLM_ID_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_FIELD_NUMBER: _ClassVar[int]
    TASK_PROMPT_FIELD_NUMBER: _ClassVar[int]
    STARTER_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    IS_DEFAULT_FIELD_NUMBER: _ClassVar[int]
    IS_VISIBLE_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    CREATED_BY_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    id: int
    name: str
    description: str
    llm_id: int
    system_prompt: str
    task_prompt: str
    starter_messages: _containers.RepeatedScalarFieldContainer[str]
    is_default: bool
    is_visible: bool
    display_priority: int
    created_by: int
    creation_date: _timestamp_pb2.Timestamp
    last_update: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., llm_id: _Optional[int] = ..., system_prompt: _Optional[str] = ..., task_prompt: _Optional[str] = ..., starter_messages: _Optional[_Iterable[str]] = ..., is_default: bool = ..., is_visible: bool = ..., display_priority: _Optional[int] = ..., created_by: _Optional[int] = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_update: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateAssistantRequest(_message.Message):
    __slots__ = ("name", "description", "llm_id", "system_prompt", "task_prompt", "starter_messages", "is_default", "is_visible", "display_priority")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LLM_ID_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_FIELD_NUMBER: _ClassVar[int]
    TASK_PROMPT_FIELD_NUMBER: _ClassVar[int]
    STARTER_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    IS_DEFAULT_FIELD_NUMBER: _ClassVar[int]
    IS_VISIBLE_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    llm_id: int
    system_prompt: str
    task_prompt: str
    starter_messages: _containers.RepeatedScalarFieldContainer[str]
    is_default: bool
    is_visible: bool
    display_priority: int
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., llm_id: _Optional[int] = ..., system_prompt: _Optional[str] = ..., task_prompt: _Optional[str] = ..., starter_messages: _Optional[_Iterable[str]] = ..., is_default: bool = ..., is_visible: bool = ..., display_priority: _Optional[int] = ...) -> None: ...

class UpdateAssistantRequest(_message.Message):
    __slots__ = ("id", "name", "description", "llm_id", "system_prompt", "task_prompt", "starter_messages", "is_default", "is_visible", "display_priority")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LLM_ID_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_FIELD_NUMBER: _ClassVar[int]
    TASK_PROMPT_FIELD_NUMBER: _ClassVar[int]
    STARTER_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    IS_DEFAULT_FIELD_NUMBER: _ClassVar[int]
    IS_VISIBLE_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_PRIORITY_FIELD_NUMBER: _ClassVar[int]
    id: int
    name: str
    description: str
    llm_id: int
    system_prompt: str
    task_prompt: str
    starter_messages: _containers.RepeatedScalarFieldContainer[str]
    is_default: bool
    is_visible: bool
    display_priority: int
    def __init__(self, id: _Optional[int] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., llm_id: _Optional[int] = ..., system_prompt: _Optional[str] = ..., task_prompt: _Optional[str] = ..., starter_messages: _Optional[_Iterable[str]] = ..., is_default: bool = ..., is_visible: bool = ..., display_priority: _Optional[int] = ...) -> None: ...

class ListAssistantsRequest(_message.Message):
    __slots__ = ("pagination", "is_visible")
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    IS_VISIBLE_FIELD_NUMBER: _ClassVar[int]
    pagination: _common_pb2.PaginationRequest
    is_visible: bool
    def __init__(self, pagination: _Optional[_Union[_common_pb2.PaginationRequest, _Mapping]] = ..., is_visible: bool = ...) -> None: ...

class ListAssistantsResponse(_message.Message):
    __slots__ = ("assistants", "pagination")
    ASSISTANTS_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    assistants: _containers.RepeatedCompositeFieldContainer[Assistant]
    pagination: _common_pb2.PaginationResponse
    def __init__(self, assistants: _Optional[_Iterable[_Union[Assistant, _Mapping]]] = ..., pagination: _Optional[_Union[_common_pb2.PaginationResponse, _Mapping]] = ...) -> None: ...

class GetAssistantResponse(_message.Message):
    __slots__ = ("assistant",)
    ASSISTANT_FIELD_NUMBER: _ClassVar[int]
    assistant: Assistant
    def __init__(self, assistant: _Optional[_Union[Assistant, _Mapping]] = ...) -> None: ...
