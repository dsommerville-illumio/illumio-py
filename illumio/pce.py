import time
from typing import List

from requests import Session, Response

from .secpolicy import PolicyChangeset, PolicyVersion
from .exceptions import IllumioApiException
from .policyobjects import (
    IPList,
    ServiceBinding,
    VirtualService
)
from .explorer import TrafficQuery, TrafficFlow
from .rules import Ruleset, Rule
from .util import ANY_IP_LIST_NAME
from .workloads import Workload


class PolicyComputeEngine:

    def __init__(self, domain_name, org_id='1', port='443', version='v2') -> None:
        self._session = Session()
        self._session.headers.update({'Accept': 'application/json'})
        self.base_url = "https://{}:{}/api/{}".format(domain_name, port, version)
        self.org_id = org_id

    def set_credentials(self, username: str, password: str) -> None:
        self._session.auth = (username, password)

    def _request(self, method: str, endpoint: str, include_org=True, **kwargs) -> Response:
        try:
            response = None  # avoid reference before assignment errors in case of cxn failure
            self._set_request_headers(**kwargs)
            url = self._build_url(endpoint, include_org)
            response = self._session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            message = str(e)
            # Response objects are falsy if the request failed so do a null check
            if response is not None and response.content:
                message = "API call returned error code {}. Errors:".format(response.status_code)
                for error in response.json():
                    if error and 'token' in error and 'message' in error:
                        message += '\n{}: {}'.format(error['token'], error['message'])
                    elif error and 'error' in error:
                        message += '\n{}'.format(error['error'])
            raise IllumioApiException(message) from e

    def _set_request_headers(self, is_async=False, **kwargs):
        headers = kwargs.get('headers', {})
        if 'data' in kwargs or 'json' in kwargs:
            kwargs['headers'] = {**headers, **{'Content-Type': 'application/json'}}
        if is_async:
            kwargs['headers'] = {**headers, **{'Prefer': 'respond-async'}}

    def _build_url(self, endpoint: str, include_org=True) -> str:
        org_str = '/orgs/{}'.format(self.org_id) if include_org else ''
        return '{}{}{}'.format(self.base_url, org_str, endpoint)

    def get_collection(self, endpoint: str, **kwargs) -> Response:
        try:
            self._set_request_headers(is_async=True, **kwargs)
            response = self._session.get(self._build_url(endpoint), **kwargs)
            response.raise_for_status()
            location = response.headers['Location']
            retry_after = int(response.headers['Retry-After'])

            while True:
                time.sleep(retry_after)
                response = self.get(location, include_org=False)
                response.raise_for_status()
                poll_result = response.json()
                poll_status = poll_result['status']

                if poll_status == 'failed':
                    raise Exception('Async collection job failed: ' + poll_result['result']['message'])
                elif poll_status == 'done':
                    collection_href = poll_result['result']['href']
                    break

            response = self.get(collection_href, include_org=False)
            response.raise_for_status()
            return response
        except Exception as e:
            raise IllumioApiException from e

    def get(self, endpoint: str, **kwargs) -> Response:
        return self._request('GET', endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> Response:
        return self._request('POST', endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> Response:
        return self._request('PUT', endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> Response:
        return self._request('DELETE', endpoint, **kwargs)

    def get_virtual_service(self, href: str, **kwargs) -> VirtualService:
        response = self.get(href, include_org=False, **kwargs)
        return VirtualService.from_json(response.json())

    def create_virtual_service(self, virtual_service: VirtualService, **kwargs) -> VirtualService:
        kwargs['json'] = virtual_service.to_json()
        response = self.post('/sec_policy/draft/virtual_services', **kwargs)
        return VirtualService.from_json(response.json())

    def create_service_binding(self, service_binding: ServiceBinding, **kwargs) -> ServiceBinding:
        kwargs['json'] = [service_binding.to_json()]
        response = self.post('/service_bindings', **kwargs)
        binding = response.json()[0]
        service_binding.href = binding['href']
        return service_binding

    def create_service_bindings(self, service_bindings: List[ServiceBinding], **kwargs) -> List[ServiceBinding]:
        kwargs['json'] = [service_binding.to_json() for service_binding in service_bindings]
        response = self.post('/service_bindings', **kwargs)
        # we don't need to worry about checking for individual creation errors, as a single failure will cause the entire POST to fail:
        # https://docs.illumio.com/core/21.3/Content/Guides/rest-api/security-policy-objects/virtual-services.htm#CreateaServiceBinding
        return [ServiceBinding(href=binding['href']) for binding in response.json()]

    def get_ip_list(self, href: str, **kwargs) -> IPList:
        response = self.get(href, include_org=False, **kwargs)
        return IPList.from_json(response.json())

    def get_ip_lists_by_name(self, name: str, **kwargs) -> IPList:
        kwargs['params'] = {'name': name}
        ip_lists = []
        for policy_version in {'draft', 'active'}:
            response = self.get('/sec_policy/{}/ip_lists'.format(policy_version), **kwargs)
            ip_lists += response.json()
        return [IPList.from_json(o) for o in ip_lists]

    def get_default_ip_list(self, **kwargs) -> IPList:
        kwargs['params'] = {'name': ANY_IP_LIST_NAME}
        response = self.get('/sec_policy/active/ip_lists', **kwargs)
        return IPList.from_json(response.json()[0])

    def create_ruleset(self, ruleset: Ruleset, **kwargs) -> Ruleset:
        if ruleset.scopes is None:
            ruleset.scopes = []
        kwargs['json'] = ruleset.to_json()
        response = self.post('/sec_policy/draft/rule_sets', **kwargs)
        return Ruleset.from_json(response.json())

    def create_rule(self, ruleset_href, rule: Rule, **kwargs) -> Rule:
        kwargs['json'] = rule.to_json()
        endpoint = '{}/sec_rules'.format(ruleset_href)
        response = self.post(endpoint, include_org=False, **kwargs)
        return Rule.from_json(response.json())

    def get_workload(self, href: str, **kwargs) -> Workload:
        response = self.get(href, include_org=False, **kwargs)
        return Workload.from_json(response.json())

    def get_traffic_flows(self, traffic_query: TrafficQuery, **kwargs) -> List[TrafficFlow]:
        kwargs['json'] = traffic_query.to_json()
        response = self.post('/traffic_flows/traffic_analysis_queries', **kwargs)
        return [TrafficFlow.from_json(flow) for flow in response.json()]

    def get_traffic_flows_async(self, query_name: str, traffic_query: TrafficQuery, **kwargs) -> List[TrafficFlow]:
        # the redundancy/reuse between this function and get_collection is unfortunately necessary due
        # to the completely different request & response structure for the async calls. note how
        # location is pulled from the initial response HREF rather than a header, retry-after is missing,
        # the success status is 'completed' rather than 'done', and the 'result' value of the response
        # contains the HREF directly rather than an object
        try:
            traffic_query.query_name = query_name
            kwargs['json'] = traffic_query.to_json()
            self._set_request_headers(is_async=True, **kwargs)
            response = self._session.post(self._build_url('/traffic_flows/async_queries'), **kwargs)
            response.raise_for_status()
            query_status = response.json()
            location = query_status['href']
            backoff = 0.1

            while True:
                backoff *= 2
                time.sleep(backoff)
                response = self.get(location, include_org=False)
                response.raise_for_status()
                poll_result = response.json()
                poll_status = poll_result['status']

                if poll_status == 'failed':
                    raise Exception('Async collection job failed: ' + poll_result['result']['message'])
                elif poll_status == 'completed':
                    collection_href = poll_result['result']
                    break

            response = self.get(collection_href, include_org=False)
            response.raise_for_status()
            return [TrafficFlow.from_json(flow) for flow in response.json()]
        except Exception as e:
            raise IllumioApiException from e

    def provision_policy_changes(self, change_description: str, hrefs: List[str], **kwargs) -> None:
        policy_changeset = PolicyChangeset.build(hrefs)
        kwargs['json'] = {'update_description': change_description, 'change_subset': policy_changeset.to_json()}
        response = self.post('/sec_policy', **kwargs)
        return PolicyVersion.from_json(response.json())


__all__ = ['PolicyComputeEngine']
