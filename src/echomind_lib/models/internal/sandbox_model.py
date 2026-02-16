# !/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File    :   sandbox_model.py
@Time    :   2026-02-16 23:16:08
@Desc    :   Generated Pydantic models from protobuf definitions
"""

import datetime
from enum import Enum as _Enum
from google.protobuf import message as _message, message_factory
from protobuf_pydantic_gen.ext import model2protobuf, pool, protobuf2model
from pydantic import BaseModel, ConfigDict, Field as _Field
from typing import Optional, Type, Any


class SandboxStatus(_Enum):
    SANDBOX_STATUS_UNSPECIFIED = 0
    SANDBOX_STATUS_WARM = 1
    SANDBOX_STATUS_ASSIGNED = 2
    SANDBOX_STATUS_ACTIVE = 3
    SANDBOX_STATUS_DRAINING = 4
    SANDBOX_STATUS_DESTROYED = 5


class SandboxEventType(_Enum):
    SANDBOX_EVENT_TYPE_UNSPECIFIED = 0
    SANDBOX_EVENT_TYPE_CREATED = 1
    SANDBOX_EVENT_TYPE_ASSIGNED = 2
    SANDBOX_EVENT_TYPE_ACTIVATED = 3
    SANDBOX_EVENT_TYPE_MESSAGE = 4
    SANDBOX_EVENT_TYPE_TOOL_CALL = 5
    SANDBOX_EVENT_TYPE_DRAINING = 6
    SANDBOX_EVENT_TYPE_DESTROYED = 7
    SANDBOX_EVENT_TYPE_ERROR = 8


class SandboxSession(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: Optional[str] = _Field(default="")
    session_id: Optional[str] = _Field(default="")
    user_id: Optional[int] = _Field(default=0)
    chat_session_id: Optional[int] = _Field(default=0)
    container_id: Optional[str] = _Field(default="")
    container_name: Optional[str] = _Field(default="")
    status: Optional[SandboxStatus] = _Field(default=SandboxStatus(0))
    assigned_at: Optional[datetime.datetime] = _Field(default=None)
    activated_at: Optional[datetime.datetime] = _Field(default=None)
    destroyed_at: Optional[datetime.datetime] = _Field(default=None)
    agent_config: Optional[dict[str, Any]] = _Field(default=None)
    message_count: Optional[int] = _Field(default=0)
    tool_calls_count: Optional[int] = _Field(default=0)
    total_tokens: Optional[int] = _Field(default=0)
    created_at: Optional[datetime.datetime] = _Field(default=None)
    updated_at: Optional[datetime.datetime] = _Field(default=None)

    def to_protobuf(self) -> _message.Message:
        """Convert Pydantic model to protobuf message"""
        _proto = pool.FindMessageTypeByName("echomind.internal.SandboxSession")
        _cls: Type[_message.Message] = message_factory.GetMessageClass(_proto)
        return model2protobuf(self, _cls())

    @classmethod
    def from_protobuf(cls, src: _message.Message) -> "SandboxSession":
        """Convert protobuf message to Pydantic model"""
        return protobuf2model(cls, src)


class SandboxEvent(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: Optional[int] = _Field(default=0)
    sandbox_session_id: Optional[str] = _Field(default="")
    event_type: Optional[SandboxEventType] = _Field(default=SandboxEventType(0))
    event_data: Optional[dict[str, Any]] = _Field(default=None)
    created_at: Optional[datetime.datetime] = _Field(default=None)

    def to_protobuf(self) -> _message.Message:
        """Convert Pydantic model to protobuf message"""
        _proto = pool.FindMessageTypeByName("echomind.internal.SandboxEvent")
        _cls: Type[_message.Message] = message_factory.GetMessageClass(_proto)
        return model2protobuf(self, _cls())

    @classmethod
    def from_protobuf(cls, src: _message.Message) -> "SandboxEvent":
        """Convert protobuf message to Pydantic model"""
        return protobuf2model(cls, src)
