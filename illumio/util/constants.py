# -*- coding: utf-8 -*-

"""This module provides constant values and enumerations used by the PCE REST API.

Copyright:
    © 2022 Illumio

License:
    Apache2, see LICENSE for more details.
"""
import re
from enum import Enum, EnumMeta

#: Active policy version path literal.
ACTIVE = 'active'

#: Draft policy version path literal.
DRAFT = 'draft'

#: Constant used in rules and enforcement boundaries to denote that all
#: workloads should be affected.
AMS = 'ams'

#: Name of the default global IP list.
ANY_IP_LIST_NAME = 'Any (0.0.0.0/0 and ::/0)'

PORT_MAX = 65535

FQDN_REGEX = re.compile('(?=^.{4,253}$)(^((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63}$)')
HREF_REGEX = re.compile('^\/orgs\/\d+\/(?:sec_policy\/(?:active|draft)\/)?(?P<type>[a-zA-Z_]+)\/(?P<uid>[a-zA-Z0-9-]+)$')

#: Upper limit on the number of objects that can be sent to PCE bulk change
#: endpoints in a single request.
BULK_CHANGE_LIMIT = 1000

PCE_APIS = {}


class IllumioEnumMeta(EnumMeta):

    def __contains__(cls, value):
        if value is None:
            return False
        if type(value) is str:
            value = value.lower()
        if isinstance(type(value), IllumioEnumMeta):
            value = value.value
        return value in cls._value2member_map_


class LinkState(str, Enum, metaclass=IllumioEnumMeta):
    UP = 'up'
    DOWN = 'down'
    UNKNOWN = 'unknown'


class EnforcementMode(str, Enum, metaclass=IllumioEnumMeta):
    IDLE = 'idle'
    VISIBILITY_ONLY = 'visibility_only'
    FULL = 'full'
    SELECTIVE = 'selective'


class VisibilityLevel(str, Enum, metaclass=IllumioEnumMeta):
    FLOW_FULL_DETAIL = 'flow_full_detail'
    FLOW_SUMMARY = 'flow_summary'
    FLOW_DROPS = 'flow_drops'
    FLOW_OFF = 'flow_off'
    ENHANCED_DATA_COLLECTION = 'enhanced_data_collection'


class PolicyDecision(str, Enum, metaclass=IllumioEnumMeta):
    ALLOWED = 'allowed'
    BLOCKED = 'blocked'
    POTENTIALLY_BLOCKED = 'potentially_blocked'
    UNKNOWN = 'unknown'


class Transmission(str, Enum, metaclass=IllumioEnumMeta):
    BROADCAST = 'broadcast'
    MULTICAST = 'multicast'
    UNICAST = 'unicast'


class FlowDirection(str, Enum, metaclass=IllumioEnumMeta):
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'


class TrafficState(str, Enum, metaclass=IllumioEnumMeta):
    ACTIVE = 'active'
    CLOSED = 'closed'
    TIMED_OUT = 'timed out'
    SNAPSHOT = 'snapshot'
    NEW = 'new'
    UNKNOWN = 'unknown'
    INCOMPLETE = 'incomplete'


__all__ = [
    'ACTIVE',
    'DRAFT',
    'AMS',
    'ANY_IP_LIST_NAME',
    'FQDN_REGEX',
    'HREF_REGEX',
    'BULK_CHANGE_LIMIT',
    'PCE_APIS',
    'EnforcementMode',
    'LinkState',
    'EnforcementMode',
    'VisibilityLevel',
    'PolicyDecision',
    'Transmission',
    'FlowDirection',
    'TrafficState',
]
