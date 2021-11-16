import re
from dataclasses import dataclass
from typing import List

from illumio import (
    IllumioException,
    JsonObject,
    ModifiableObject,
    POLICY_OBJECT_HREF_REGEX
)
from illumio.rules import Ruleset, EnforcementBoundary
from illumio.infrastructure import SecureConnectGateway

from . import (
    LabelGroup,
    LabelSet,
    Service,
    IPList,
    VirtualService,
    VirtualServer
)


@dataclass
class FirewallSetting(ModifiableObject):
    allow_dhcp_client: bool = None
    log_dropped_multicast: bool = None
    log_dropped_broadcast: bool = None
    allow_traceroute: bool = None
    allow_ipv6: bool = None
    ipv6_mode: str = None
    network_detection_mode: str = None
    ike_authentication_type: str = None
    static_policy_scopes: List[LabelSet] = None
    firewall_coexistence: List[LabelSet] = None
    containers_inherit_host_policy_scopes: List[LabelSet] = None
    blocked_connection_reject_scopes: List[LabelSet] = None
    loopback_interfaces_in_policy_scopes: List[LabelSet] = None

TYPE_TO_CLASS_MAP = {
    'label_groups': LabelGroup,
    'rule_sets': Ruleset,
    'ip_lists': IPList,
    'virtual_services': VirtualService,
    'services': Service,
    'firewall_settings': FirewallSetting,
    'enforcement_boundaries': EnforcementBoundary,
    'secure_connect_gateways': SecureConnectGateway,
    'virtual_servers': VirtualServer
}


@dataclass
class PolicyChangeset(JsonObject):
    label_groups: List[LabelGroup] = None
    services: List[Service] = None
    rule_sets: List[Ruleset] = None
    ip_lists: List[IPList] = None
    virtual_services: List[VirtualService] = None
    firewall_settings: List[FirewallSetting] = None
    enforcement_boundaries: List[EnforcementBoundary] = None
    secure_connect_gateways: List[SecureConnectGateway] = None
    virtual_servers: List[VirtualServer] = None

    @staticmethod
    def build(hrefs: List[str]):
        changeset = PolicyChangeset()
        for href in hrefs:
            match = re.match(POLICY_OBJECT_HREF_REGEX, href)
            if match:
                object_type = match.group('type')
                arr = getattr(changeset, object_type) or []
                arr.append(TYPE_TO_CLASS_MAP[object_type](href=href))
                setattr(changeset, object_type, arr)
            else:
                raise IllumioException('Invalid HREF in policy provision changeset: {}'.format(href))
        return changeset


@dataclass
class PolicyObjectCounts(JsonObject):
    label_groups: int = None
    services: int = None
    rule_sets: int = None
    ip_lists: int = None
    virtual_services: int = None
    firewall_settings: int = None
    enforcement_boundaries: int = None
    secure_connect_gateways: int = None
    virtual_servers: int = None


@dataclass
class PolicyVersion(ModifiableObject):
    commit_message: str = None
    version: int = None
    workloads_affected: int = None
    object_counts: PolicyObjectCounts = None

    def _decode_complex_types(self):
        super()._decode_complex_types()
        self.object_counts = PolicyObjectCounts.from_json(self.object_counts) if self.object_counts else None
