import re
from dataclasses import dataclass
from enum import Enum

from .jsonutils import JsonObject

FQDN_REGEX = re.compile('(?=^.{4,253}$)(^((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63}$)')


@dataclass
class IllumioObject(JsonObject):
    href: str = None
    name: str = None
    description: str = None
    external_data_set: str = None
    external_data_reference: str = None


class IllumioEnum(Enum):

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_


class LinkState(IllumioEnum):
    UP = 'up'
    DOWN = 'down'
    UNKNOWN = 'unknown'


class Mode(IllumioEnum):
    IDLE = 'idle'
    ILLUMINATED = 'illuminated'
    ENFORCED = 'enforced'


class EnforcementMode(IllumioEnum):
    IDLE = 'idle'
    VISIBILITY_ONLY = 'visibility_only'
    FULL = 'full'
    SELECTIVE = 'selective'


class PolicyDecision(IllumioEnum):
    ALLOWED = 'allowed'
    BLOCKED = 'blocked'
    POTENTIALLY_BLOCKED = 'potentially_blocked'
    UNKNOWN = 'unknown'


class Transmission(IllumioEnum):
    BROADCAST = 'broadcast'
    MULTICAST = 'multicast'
    UNICAST = 'unicast'


class FlowDirection(IllumioEnum):
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'


class TrafficState(IllumioEnum):
    ACTIVE = 'active'
    CLOSED = 'closed'
    TIMED_OUT = 'timed_out'
    SNAPSHOT = 'snapshot'
    NEW = 'new'
    UNKNOWN = 'unknown'
    INCOMPLETE = 'incomplete'
