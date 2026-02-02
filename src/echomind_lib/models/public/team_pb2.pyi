from google.protobuf import timestamp_pb2 as _timestamp_pb2
import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TeamMemberRole(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TEAM_MEMBER_ROLE_UNSPECIFIED: _ClassVar[TeamMemberRole]
    TEAM_MEMBER_ROLE_MEMBER: _ClassVar[TeamMemberRole]
    TEAM_MEMBER_ROLE_LEAD: _ClassVar[TeamMemberRole]
TEAM_MEMBER_ROLE_UNSPECIFIED: TeamMemberRole
TEAM_MEMBER_ROLE_MEMBER: TeamMemberRole
TEAM_MEMBER_ROLE_LEAD: TeamMemberRole

class Team(_message.Message):
    __slots__ = ("id", "name", "description", "leader_id", "created_by", "member_count", "creation_date", "last_update")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_BY_FIELD_NUMBER: _ClassVar[int]
    MEMBER_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATION_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_FIELD_NUMBER: _ClassVar[int]
    id: int
    name: str
    description: str
    leader_id: int
    created_by: int
    member_count: int
    creation_date: _timestamp_pb2.Timestamp
    last_update: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., leader_id: _Optional[int] = ..., created_by: _Optional[int] = ..., member_count: _Optional[int] = ..., creation_date: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_update: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class TeamMember(_message.Message):
    __slots__ = ("team_id", "user_id", "role", "added_at", "added_by")
    TEAM_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    ADDED_AT_FIELD_NUMBER: _ClassVar[int]
    ADDED_BY_FIELD_NUMBER: _ClassVar[int]
    team_id: int
    user_id: int
    role: TeamMemberRole
    added_at: _timestamp_pb2.Timestamp
    added_by: int
    def __init__(self, team_id: _Optional[int] = ..., user_id: _Optional[int] = ..., role: _Optional[_Union[TeamMemberRole, str]] = ..., added_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., added_by: _Optional[int] = ...) -> None: ...

class TeamMemberWithUser(_message.Message):
    __slots__ = ("user_id", "user_name", "email", "first_name", "last_name", "role", "added_at")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    USER_NAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    FIRST_NAME_FIELD_NUMBER: _ClassVar[int]
    LAST_NAME_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    ADDED_AT_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    user_name: str
    email: str
    first_name: str
    last_name: str
    role: TeamMemberRole
    added_at: _timestamp_pb2.Timestamp
    def __init__(self, user_id: _Optional[int] = ..., user_name: _Optional[str] = ..., email: _Optional[str] = ..., first_name: _Optional[str] = ..., last_name: _Optional[str] = ..., role: _Optional[_Union[TeamMemberRole, str]] = ..., added_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateTeamRequest(_message.Message):
    __slots__ = ("name", "description", "leader_id")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    leader_id: int
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., leader_id: _Optional[int] = ...) -> None: ...

class UpdateTeamRequest(_message.Message):
    __slots__ = ("id", "name", "description", "leader_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    name: str
    description: str
    leader_id: int
    def __init__(self, id: _Optional[int] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., leader_id: _Optional[int] = ...) -> None: ...

class ListTeamsRequest(_message.Message):
    __slots__ = ("pagination", "include_member_count")
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_MEMBER_COUNT_FIELD_NUMBER: _ClassVar[int]
    pagination: _common_pb2.PaginationRequest
    include_member_count: bool
    def __init__(self, pagination: _Optional[_Union[_common_pb2.PaginationRequest, _Mapping]] = ..., include_member_count: bool = ...) -> None: ...

class ListTeamsResponse(_message.Message):
    __slots__ = ("teams", "pagination")
    TEAMS_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    teams: _containers.RepeatedCompositeFieldContainer[Team]
    pagination: _common_pb2.PaginationResponse
    def __init__(self, teams: _Optional[_Iterable[_Union[Team, _Mapping]]] = ..., pagination: _Optional[_Union[_common_pb2.PaginationResponse, _Mapping]] = ...) -> None: ...

class GetTeamResponse(_message.Message):
    __slots__ = ("team", "members")
    TEAM_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    team: Team
    members: _containers.RepeatedCompositeFieldContainer[TeamMemberWithUser]
    def __init__(self, team: _Optional[_Union[Team, _Mapping]] = ..., members: _Optional[_Iterable[_Union[TeamMemberWithUser, _Mapping]]] = ...) -> None: ...

class AddTeamMemberRequest(_message.Message):
    __slots__ = ("team_id", "user_id", "role")
    TEAM_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    team_id: int
    user_id: int
    role: TeamMemberRole
    def __init__(self, team_id: _Optional[int] = ..., user_id: _Optional[int] = ..., role: _Optional[_Union[TeamMemberRole, str]] = ...) -> None: ...

class RemoveTeamMemberRequest(_message.Message):
    __slots__ = ("team_id", "user_id")
    TEAM_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    team_id: int
    user_id: int
    def __init__(self, team_id: _Optional[int] = ..., user_id: _Optional[int] = ...) -> None: ...

class UpdateTeamMemberRoleRequest(_message.Message):
    __slots__ = ("team_id", "user_id", "role")
    TEAM_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    team_id: int
    user_id: int
    role: TeamMemberRole
    def __init__(self, team_id: _Optional[int] = ..., user_id: _Optional[int] = ..., role: _Optional[_Union[TeamMemberRole, str]] = ...) -> None: ...

class ListUserTeamsRequest(_message.Message):
    __slots__ = ("pagination",)
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    pagination: _common_pb2.PaginationRequest
    def __init__(self, pagination: _Optional[_Union[_common_pb2.PaginationRequest, _Mapping]] = ...) -> None: ...

class ListUserTeamsResponse(_message.Message):
    __slots__ = ("teams", "pagination")
    TEAMS_FIELD_NUMBER: _ClassVar[int]
    PAGINATION_FIELD_NUMBER: _ClassVar[int]
    teams: _containers.RepeatedCompositeFieldContainer[Team]
    pagination: _common_pb2.PaginationResponse
    def __init__(self, teams: _Optional[_Iterable[_Union[Team, _Mapping]]] = ..., pagination: _Optional[_Union[_common_pb2.PaginationResponse, _Mapping]] = ...) -> None: ...
