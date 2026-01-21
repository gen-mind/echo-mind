from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ChatMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHAT_MODE_UNSPECIFIED: _ClassVar[ChatMode]
    CHAT_MODE_CHAT: _ClassVar[ChatMode]
    CHAT_MODE_SEARCH: _ClassVar[ChatMode]

class MessageRole(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MESSAGE_ROLE_UNSPECIFIED: _ClassVar[MessageRole]
    MESSAGE_ROLE_USER: _ClassVar[MessageRole]
    MESSAGE_ROLE_ASSISTANT: _ClassVar[MessageRole]
    MESSAGE_ROLE_SYSTEM: _ClassVar[MessageRole]
CHAT_MODE_UNSPECIFIED: ChatMode
CHAT_MODE_CHAT: ChatMode
CHAT_MODE_SEARCH: ChatMode
MESSAGE_ROLE_UNSPECIFIED: MessageRole
MESSAGE_ROLE_USER: MessageRole
MESSAGE_ROLE_ASSISTANT: MessageRole
MESSAGE_ROLE_SYSTEM: MessageRole

class ChatSession(_message.Message):
    __slots__ = ("id", "user_id", "assistant_id", "title", "mode", "message_count", "creation_date", "last_update", "last_message_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ASSISTANT_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    LAST_MESSAGE_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    user_id: int
    assistant_id: int
    title: str
    mode: ChatMode
    message_count: int
    creation_date: _timestamp_pb2.Timestamp
    last_update: _timestamp_pb2.Timestamp
    last_message_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., user_id: _Optional[int] = ..., assistant_id: _Optional[int] = ..., title: _Optional[str] = ..., mode: _Optional[_Union[ChatMode, str]] = ..., message_count: _Optional[int] = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_update: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_message_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ChatMessage(_message.Message):
    __slots__ = ("id", "chat_session_id", "role", "content", "token_count", "parent_message_id", "rephrased_query", "retrieval_context", "tool_calls", "error", "creation_date")
    ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TOKEN_COUNT_FIELD_NUMBER: _ClassVar[int]
    PARENT_MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    REPHRASED_QUERY_FIELD_NUMBER: _ClassVar[int]
    RETRIEVAL_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALLS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    id: int
    chat_session_id: int
    role: MessageRole
    content: str
    token_count: int
    parent_message_id: int
    rephrased_query: str
    retrieval_context: _struct_pb2.Struct
    tool_calls: _struct_pb2.Struct
    error: str
    creation_date: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., chat_session_id: _Optional[int] = ..., role: _Optional[_Union[MessageRole, str]] = ..., content: _Optional[str] = ..., token_count: _Optional[int] = ..., parent_message_id: _Optional[int] = ..., rephrased_query: _Optional[str] = ..., retrieval_context: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., tool_calls: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., error: _Optional[str] = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class MessageSource(_message.Message):
    __slots__ = ("document_id", "chunk_id", "score", "title", "snippet")
    DOCUMENT_ID_FIELD_NUMBER: _ClassVar[int]
    CHUNK_ID_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SNIPPET_FIELD_NUMBER: _ClassVar[int]
    document_id: int
    chunk_id: str
    score: float
    title: str
    snippet: str
    def __init__(self, document_id: _Optional[int] = ..., chunk_id: _Optional[str] = ..., score: _Optional[float] = ..., title: _Optional[str] = ..., snippet: _Optional[str] = ...) -> None: ...

class MessageFeedback(_message.Message):
    __slots__ = ("id", "chat_message_id", "user_id", "is_positive", "feedback_text", "creation_date")
    ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    IS_POSITIVE_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_TEXT_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    id: int
    chat_message_id: int
    user_id: int
    is_positive: bool
    feedback_text: str
    creation_date: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., chat_message_id: _Optional[int] = ..., user_id: _Optional[int] = ..., is_positive: bool = ..., feedback_text: _Optional[str] = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateChatSessionRequest(_message.Message):
    __slots__ = ("assistant_id", "title", "mode")
    ASSISTANT_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    assistant_id: int
    title: str
    mode: ChatMode
    def __init__(self, assistant_id: _Optional[int] = ..., title: _Optional[str] = ..., mode: _Optional[_Union[ChatMode, str]] = ...) -> None: ...

class ListChatSessionsRequest(_message.Message):
    __slots__ = ("pagination", "assistant_id")
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    ASSISTANT_ID_FIELD_NUMBER: _ClassVar[int]
    pagination: _common_pb2.PaginationRequest
    assistant_id: int
    def __init__(self, pagination: _Optional[_Union[_common_pb2.PaginationRequest, _Mapping]] = ..., assistant_id: _Optional[int] = ...) -> None: ...

class ListChatSessionsResponse(_message.Message):
    __slots__ = ("sessions", "pagination")
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    sessions: _containers.RepeatedCompositeFieldContainer[ChatSession]
    pagination: _common_pb2.PaginationResponse
    def __init__(self, sessions: _Optional[_Iterable[_Union[ChatSession, _Mapping]]] = ..., pagination: _Optional[_Union[_common_pb2.PaginationResponse, _Mapping]] = ...) -> None: ...

class GetChatSessionResponse(_message.Message):
    __slots__ = ("session", "messages")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    session: ChatSession
    messages: _containers.RepeatedCompositeFieldContainer[ChatMessage]
    def __init__(self, session: _Optional[_Union[ChatSession, _Mapping]] = ..., messages: _Optional[_Iterable[_Union[ChatMessage, _Mapping]]] = ...) -> None: ...

class ListMessagesRequest(_message.Message):
    __slots__ = ("session_id", "pagination")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    pagination: _common_pb2.PaginationRequest
    def __init__(self, session_id: _Optional[int] = ..., pagination: _Optional[_Union[_common_pb2.PaginationRequest, _Mapping]] = ...) -> None: ...

class ListMessagesResponse(_message.Message):
    __slots__ = ("messages", "pagination")
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    messages: _containers.RepeatedCompositeFieldContainer[ChatMessage]
    pagination: _common_pb2.PaginationResponse
    def __init__(self, messages: _Optional[_Iterable[_Union[ChatMessage, _Mapping]]] = ..., pagination: _Optional[_Union[_common_pb2.PaginationResponse, _Mapping]] = ...) -> None: ...

class GetMessageResponse(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: ChatMessage
    def __init__(self, message: _Optional[_Union[ChatMessage, _Mapping]] = ...) -> None: ...

class GetMessageSourcesResponse(_message.Message):
    __slots__ = ("sources",)
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    sources: _containers.RepeatedCompositeFieldContainer[MessageSource]
    def __init__(self, sources: _Optional[_Iterable[_Union[MessageSource, _Mapping]]] = ...) -> None: ...

class SubmitFeedbackRequest(_message.Message):
    __slots__ = ("message_id", "is_positive", "feedback_text")
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    IS_POSITIVE_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_TEXT_FIELD_NUMBER: _ClassVar[int]
    message_id: int
    is_positive: bool
    feedback_text: str
    def __init__(self, message_id: _Optional[int] = ..., is_positive: bool = ..., feedback_text: _Optional[str] = ...) -> None: ...

class SubmitFeedbackResponse(_message.Message):
    __slots__ = ("feedback",)
    FEEDBACK_FIELD_NUMBER: _ClassVar[int]
    feedback: MessageFeedback
    def __init__(self, feedback: _Optional[_Union[MessageFeedback, _Mapping]] = ...) -> None: ...

class WsChatStart(_message.Message):
    __slots__ = ("session_id", "query", "mode")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    query: str
    mode: ChatMode
    def __init__(self, session_id: _Optional[int] = ..., query: _Optional[str] = ..., mode: _Optional[_Union[ChatMode, str]] = ...) -> None: ...

class WsChatCancel(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    def __init__(self, session_id: _Optional[int] = ...) -> None: ...

class WsRetrievalStart(_message.Message):
    __slots__ = ("session_id", "query", "rephrased_query")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    REPHRASED_QUERY_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    query: str
    rephrased_query: str
    def __init__(self, session_id: _Optional[int] = ..., query: _Optional[str] = ..., rephrased_query: _Optional[str] = ...) -> None: ...

class WsRetrievalComplete(_message.Message):
    __slots__ = ("session_id", "sources")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    sources: _containers.RepeatedCompositeFieldContainer[MessageSource]
    def __init__(self, session_id: _Optional[int] = ..., sources: _Optional[_Iterable[_Union[MessageSource, _Mapping]]] = ...) -> None: ...

class WsGenerationToken(_message.Message):
    __slots__ = ("session_id", "token")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    token: str
    def __init__(self, session_id: _Optional[int] = ..., token: _Optional[str] = ...) -> None: ...

class WsGenerationComplete(_message.Message):
    __slots__ = ("session_id", "message_id", "token_count")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_COUNT_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    message_id: int
    token_count: int
    def __init__(self, session_id: _Optional[int] = ..., message_id: _Optional[int] = ..., token_count: _Optional[int] = ...) -> None: ...

class WsError(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...
