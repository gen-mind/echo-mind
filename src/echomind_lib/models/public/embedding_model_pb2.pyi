from google.protobuf import timestamp_pb2 as _timestamp_pb2
import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EmbeddingModel(_message.Message):
    __slots__ = ("id", "model_id", "model_name", "model_dimension", "endpoint", "is_active", "creation_date", "last_update")
    ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_NAME_FIELD_NUMBER: _ClassVar[int]
    MODEL_DIMENSION_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    id: int
    model_id: str
    model_name: str
    model_dimension: int
    endpoint: str
    is_active: bool
    creation_date: _timestamp_pb2.Timestamp
    last_update: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., model_id: _Optional[str] = ..., model_name: _Optional[str] = ..., model_dimension: _Optional[int] = ..., endpoint: _Optional[str] = ..., is_active: bool = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_update: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateEmbeddingModelRequest(_message.Message):
    __slots__ = ("model_id", "model_name", "model_dimension", "endpoint")
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_NAME_FIELD_NUMBER: _ClassVar[int]
    MODEL_DIMENSION_FIELD_NUMBER: _ClassVar[int]
    ENDPOINT_FIELD_NUMBER: _ClassVar[int]
    model_id: str
    model_name: str
    model_dimension: int
    endpoint: str
    def __init__(self, model_id: _Optional[str] = ..., model_name: _Optional[str] = ..., model_dimension: _Optional[int] = ..., endpoint: _Optional[str] = ...) -> None: ...

class ListEmbeddingModelsResponse(_message.Message):
    __slots__ = ("models",)
    MODELS_FIELD_NUMBER: _ClassVar[int]
    models: _containers.RepeatedCompositeFieldContainer[EmbeddingModel]
    def __init__(self, models: _Optional[_Iterable[_Union[EmbeddingModel, _Mapping]]] = ...) -> None: ...

class GetActiveEmbeddingModelResponse(_message.Message):
    __slots__ = ("model",)
    MODEL_FIELD_NUMBER: _ClassVar[int]
    model: EmbeddingModel
    def __init__(self, model: _Optional[_Union[EmbeddingModel, _Mapping]] = ...) -> None: ...

class ActivateEmbeddingModelResponse(_message.Message):
    __slots__ = ("success", "message", "requires_reindex", "documents_affected")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_REINDEX_FIELD_NUMBER: _ClassVar[int]
    DOCUMENTS_AFFECTED_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    requires_reindex: bool
    documents_affected: int
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., requires_reindex: bool = ..., documents_affected: _Optional[int] = ...) -> None: ...
