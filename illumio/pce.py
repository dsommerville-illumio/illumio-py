# -*- coding: utf-8 -*-

"""This module provides the core PolicyComputeEngine class for communicating with the PCE.

Usage:
    >>> from illumio import PolicyComputeEngine
    >>> pce = PolicyComputeEngine('my.pce.com', port='8443', org_id='12')
    >>> pce.set_credentials('<API_KEY>', '<API_SECRET>')
    >>> workloads = pce.workloads.get(
    ...     params={
    ...         'managed': True,
    ...         'enforcement_mode': 'visibility_only'
    ...     }
    ... )
    >>> workloads
    [
        Workload(href='/orgs/12/workloads/c754a713-2bde-4427-af1f-bff145be509b', ...),
        ...
    ]

Copyright:
    (c) 2022 Illumio

License:
    Apache2, see LICENSE for more details.
"""
import json
import time
from typing import Any, List, Union

from requests import Session, Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .secpolicy import PolicyChangeset, PolicyVersion
from .exceptions import IllumioApiException
from .policyobjects import IPList
from .explorer import TrafficQuery, TrafficFlow
from .util import (
    deprecated,
    convert_active_href_to_draft,
    parse_url,
    href_from,
    Reference,
    IllumioObject,
    IllumioEncoder,
    ACTIVE,
    DRAFT,
    ANY_IP_LIST_NAME,
    BULK_CHANGE_LIMIT,
    PCE_APIS
)


class PolicyComputeEngine:
    """The REST client core for the Illumio Policy Compute Engine.

    Contains request logic for API calls and handles the HTTP(S) connection to the PCE.

    Attributes:
        base_url: the base URL for API calls to the PCE. Has the form
            http[s]://<DOMAIN_NAME>:<PORT>/api/<API_VERSION>
        org_id: the PCE organization ID.
    """

    def __init__(self, url: str, port: str = '443', version: str = 'v2', org_id: str = '1') -> None:
        """Initializes the PCE REST client.

        Args:
            url (str): PCE URL. May include http:// or https:// as the protocol.
            port (str, optional): PCE http(s) port. Defaults to '443'.
            version (str, optional): The PCE API version to use. Defaults to 'v2'.
            org_id (str, optional): The PCE organization ID. Defaults to '1'.
        """
        self._apis = {}
        self._encoder = IllumioEncoder()
        self._session = Session()
        self._session.headers.update({'Accept': 'application/json'})
        protocol, url = parse_url(url)
        self.base_url = "{}://{}:{}/api/{}".format(protocol, url, port, version)
        self.org_id = org_id
        self._setup_retry()

    def _setup_retry(self):
        """Configures `requests.Session` retry defaults"""
        retry_strategy = Retry(
            total=5,  # retry up to 5 times
            # {backoff} * (2 ** ({retry count} - 1))
            # 1, 2, 4, 8, 16 (seconds)
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def set_credentials(self, username: str, password: str) -> None:
        """Sets username and password values to authenticate with the PCE.

        The provided credentials can be either user credentials or an API key/secret pair.

        Args:
            username (str): username or API key.
            password (str): password or API secret.
        """
        self._session.auth = (username, password)

    def set_proxies(self, http_proxy: str = None, https_proxy: str = None) -> None:
        """Sets proxy information in the request session.

        Args:
            http_proxy (str, optional): HTTP proxy URI. Defaults to None.
            https_proxy (str, optional): HTTPS proxy URI. Defaults to None.
        """
        self._session.proxies.update({'http': http_proxy, 'https': https_proxy})

    def _request(self, method: str, endpoint: str, include_org=True, **kwargs) -> Response:
        """Makes an API call to the PCE.

        Args:
            method (str): the HTTP request method. Supports the same verbs as `requests.request`.
            endpoint (str): the API endpoint to call.
            include_org (bool, optional): whether or not to include /orgs/{org_id} in the API call.
                Defaults to True.

        Raises:
            IllumioApiException: if the response is unsuccessful (status code >399).

        Returns:
            requests.Response: the `Response` object returned from a successful request.
        """
        try:
            response = None  # avoid reference before assignment errors in case of cxn failure
            url = self._build_url(endpoint, include_org)
            self._encode_body(kwargs)
            response = self._session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            message = str(e)
            # Response objects are falsy if the request failed so do a null check
            if response is not None and response.headers.get('Content-Type', '') == 'application/json':
                message = self._get_error_message_from_response(response)
            raise IllumioApiException(message) from e

    def _build_url(self, endpoint: str, include_org: bool):
        endpoint = endpoint.lstrip('/').replace('//', '/')
        if include_org and not endpoint.startswith('orgs/'):
            endpoint = 'orgs/{}/{}'.format(self.org_id, endpoint)
        return '{}/{}'.format(self.base_url, endpoint)

    def _encode_body(self, kwargs):
        """Encodes request body data to JSON."""
        body = kwargs.pop('data', None)
        if 'json' in kwargs:
            # json overrides data if both are provided
            body = kwargs.pop('json')
        if body is not None:
            kwargs['json'] = json.loads(self._encoder.encode(body))

    def _get_error_message_from_response(self, response: Response) -> str:
        message = "API call returned error code {}. Errors:".format(response.status_code)
        for error in response.json():
            if error and 'token' in error and 'message' in error:
                message += '\n{}: {}'.format(error['token'], error['message'])
            elif error and 'error' in error:
                message += '\n{}'.format(error['error'])
        return message

    def get(self, endpoint: str, **kwargs) -> Response:
        """Makes a GET call to a given PCE endpoint.

        Additional keyword arguments are passed to the `requests.Request` object.

        Args:
            endpoint (str): the PCE endpoint to call.

        Returns:
            requests.Response: the `Response` object returned from a successful request.
        """
        return self._request('GET', endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> Response:
        """Makes a POST call to a given PCE endpoint.

        Appends 'Content-Type: application/json' to the request headers by default.
        Additional keyword arguments are passed to the `requests.Request` object.

        Args:
            endpoint (str): the PCE endpoint to call.

        Returns:
            requests.Response: the `Response` object returned from a successful request.
        """
        headers = kwargs.get('headers', {})
        kwargs['headers'] = {**headers, **{'Content-Type': 'application/json'}}
        return self._request('POST', endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> Response:
        """Makes a PUT call to a given PCE endpoint.

        Appends 'Content-Type: application/json' to the request headers by default.
        Additional keyword arguments are passed to the `requests.Request` object.

        Args:
            endpoint (str): the PCE endpoint to call.

        Returns:
            requests.Response: the `Response` object returned from a successful request.
        """
        headers = kwargs.get('headers', {})
        kwargs['headers'] = {**headers, **{'Content-Type': 'application/json'}}
        return self._request('PUT', endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> Response:
        """Makes a DELETE call to a given PCE endpoint.

        Additional keyword arguments are passed to the `requests.Request` object.

        Args:
            endpoint (str): the PCE endpoint to call.

        Returns:
            requests.Response: the `Response` object returned from a successful request.
        """
        return self._request('DELETE', endpoint, **kwargs)

    def get_collection(self, endpoint: str, **kwargs) -> Response:
        """Uses the PCE's asynchronous job logic to retrieve a collection of objects.

        NOTE: for large collections (surpassing 10,000 objects), this function will be extremely
        slow - it is recommended that callers use query filters or the max_results parameter to limit
        the number of results in the collection.

        Args:
            endpoint (str): the PCE endpoint to call.

        Raises:
            IllumioApiException: if an error message (>399) status code is returned.

        Returns:
            requests.Response: the `Response` object returned from a successful request.
        """
        try:
            headers = kwargs.get('headers', {})
            kwargs['headers'] = {**headers, **{'Prefer': 'respond-async'}}
            response = self.get(endpoint, **kwargs)
            response.raise_for_status()
            location = response.headers['Location']
            retry_after = int(response.headers['Retry-After'])

            collection_href = self._async_poll(location, retry_after)

            response = self.get(collection_href, include_org=False)
            response.raise_for_status()
            return response
        except Exception as e:
            raise IllumioApiException from e

    def _async_poll(self, job_location: str, retry_time: Union[int, float] = 1.) -> str:
        """Polls the PCE for an async job's status until it completes or times out.

        The poll-wait loop uses the Retry-After time from the job submission  request
        or a default of 1 second, with a 1.5x backoff.

        Args:
            job_location (str): URL of the job to poll.
            retry_time (Union[int, float], optional): base Retry-After time. Defaults to 1 second.

        Raises:
            Exception: if the job returns a 'failed' status.

        Returns:
            str: the HREF path of the completed collection document.
        """
        while True:
            time.sleep(retry_time)
            retry_time *= 1.5  # slight backoff to avoid spamming the PCE for long-running jobs
            response = self.get(job_location)
            response.raise_for_status()
            poll_result = response.json()
            poll_status = poll_result['status']

            if poll_status == 'failed':
                raise Exception('Async collection job failed: ' + poll_result['result']['message'])
            elif poll_status == 'completed':
                # traffic flow async jobs
                collection_href = poll_result['result']
                break
            elif poll_status == 'done':
                # policy object collection jobs
                collection_href = poll_result['result']['href']
                break
        return collection_href

    def check_connection(self, **kwargs) -> bool:
        """Makes a GET request to the PCE /health endpoint.

        Additional keyword arguments are passed to the requests call.

        Returns:
            bool: True if the call is successful, otherwise False.
        """
        try:
            self.get('/health', include_org=False, **kwargs)
            return True
        except IllumioApiException:
            return False

    class _PCEObjectAPI:
        """Generic API for registered PCE objects."""
        def __init__(self, pce: 'PolicyComputeEngine', api_data: object) -> None:
            self.name = api_data.name
            self.endpoint = api_data.endpoint
            self.object_cls = api_data.object_class
            self.is_sec_policy = api_data.is_sec_policy
            self.is_global = api_data.is_global
            self.pce = pce

        def _build_endpoint(self, policy_version: str, parent: Union[Reference, str]) -> str:
            """Builds the PCE request endpoint."""
            endpoint = self.endpoint

            if parent:  # e.g. /sec_policy/active/rulesets/1/sec_rules
                parent_href = parent if type(parent) is str else parent.href
                parent_draft_href = convert_active_href_to_draft(parent_href)
                endpoint = '{}/{}'.format(parent_draft_href, endpoint)
            # mutually exclusive as the parent HREF will have the sec_policy prefix already
            elif self.is_sec_policy:
                if policy_version not in [ACTIVE, DRAFT]:
                    raise IllumioApiException("Invalid policy_version passed to get: {}".format(policy_version))
                endpoint = '/sec_policy/{}/{}'.format(policy_version, endpoint)

            if not self.is_global:
                endpoint = '/orgs/{}/{}'.format(self.pce.org_id, endpoint)
            return endpoint

        def get_by_reference(self, reference: Union[str, Reference, dict], **kwargs) -> IllumioObject:
            """Retrieves an object from the PCE using its HREF.

            Usage:
                >>> ip_list = pce.ip_lists.get_by_reference('/orgs/1/sec_policy/active/ip_lists/1')
                >>> ip_list
                IPList(
                    name='Any (0.0.0.0/0 and ::/0)',
                    ...
                )

            Args:
                href (str): the HREF of the object to fetch.

            Returns:
                IllumioObject: the object json, decoded to its IllumioObject equivalent.
            """
            response = self.pce.get(href_from(reference), include_org=False, **kwargs)
            return self.object_cls.from_json(response.json())

        def get(self, policy_version: str = DRAFT, parent_href: Union[Reference, str] = None, **kwargs) -> List[IllumioObject]:
            """Retrieves objects from the PCE based on the given parameters.

            Keyword arguments to this function are passed to the `requests.get` call.
            See https://docs.illumio.com/core/21.5/API-Reference/index.html
            for details on filter parameters for collection queries.

            Usage:
                >>> virtual_services = pce.virtual_services.get(
                ...     policy_version='active',
                ...     params={
                ...         'name': 'VS-'
                ...     }
                ... )
                >>> virtual_services
                [
                    VirtualService(
                        href='/orgs/1/sec_policy/active/virtual_services/9177c75f-7b21-4bf0-8c16-2c47c1ca3252',
                        name='VS-LAB-SERVICES'
                        ...
                    ),
                    ...
                ]

            Args:
                policy_version (str, optional): if fetching security policy objects, specifies
                    whether to fetch 'draft' or 'active' objects. Defaults to 'draft'.
                parent_href (Union[Reference, str], optional): HREF of the created
                    object's parent object. Required for some object types, such
                    as Security Rules which must be created as children of
                    existing RuleSets.

            Returns:
                List[IllumioObject]: the returned list of decoded objects.
            """
            params = kwargs.get('params', {})
            endpoint = self._build_endpoint(policy_version, parent_href)

            if 'max_results' not in params:
                kwargs['params'] = {**params, **{'max_results': 0}}
                response = self.pce.get(endpoint, **kwargs)
                filtered_object_count = response.headers['X-Total-Count']
                kwargs['params'] = {**params, **{'max_results': int(filtered_object_count)}}

            response = self.pce.get(endpoint, include_org=False, **kwargs)
            return [self.object_cls.from_json(o) for o in response.json()]

        def get_async(self, policy_version: str = DRAFT, parent_href: Union[Reference, str] = None, **kwargs) -> List[IllumioObject]:
            """Retrieves objects asynchronously from the PCE based on the given parameters.

            Args:
                policy_version (str, optional): if fetching security policy objects, specifies
                    whether to fetch 'draft' or 'active' objects. Defaults to 'draft'.
                parent_href (Union[Reference, str], optional): HREF of the created
                    object's parent object. Required for some object types, such
                    as Security Rules which must be created as children of
                    existing RuleSets.

            Returns:
                List[IllumioObject]: the returned list of decoded objects.
            """
            endpoint = self._build_endpoint(policy_version, parent_href)
            response = self.pce.get_collection(endpoint, **kwargs)
            return [self.object_cls.from_json(o) for o in response.json()]

        def create(self, body: Any, parent_href: Union[Reference, str] = None, **kwargs) -> Any:
            """Creates a virtual service object in the PCE.

            See https://docs.illumio.com/core/21.5/API-Reference/index.html
            for details on POST body parameters when creating objects.

            Usage:
                >>> from illumio.policyobjects import Label
                >>> label = Label(key='role', value='R-DB')
                >>> label = pce.labels.create(label)
                >>> label
                Label(
                    'href': '/orgs/1/labels/14',
                    'key': 'role',
                    'value': 'R-DB
                )

            Args:
                body (Any): the parameters for the newly created object.
                parent_href (Union[Reference, str], optional): HREF of the created
                    object's parent object. Required for some object types, such
                    as Security Rules which must be created as children of
                    existing RuleSets.

            Returns:
                IllumioObject: the created object.
            """
            kwargs['json'] = body
            endpoint = self._build_endpoint(DRAFT, parent_href)
            response = self.pce.post(endpoint, include_org=False, **kwargs)
            return self._parse_response_body(response.json())

        def _parse_response_body(self, json_response):
            # XXX: workaround for Service Bindings. Multiple bindings
            #   can be created in the same POST, so we need to accommodate
            #   this case by checking the response body type
            if type(json_response) is list:
                results = {self.name: [], 'errors': []}
                for o in json_response:
                    if 'href' in o:
                        results[self.name].append(self.object_cls.from_json(o))
                    else:
                        results['errors'].append(o)
                return results
            return self.object_cls.from_json(json_response)

        def update(self, reference: Union[str, Reference, dict], body: Any, **kwargs) -> None:
            """Updates an object in the PCE.

            Successful PUT requests return a 204 No Content response.

            Usage:
                >>> from illumio.workloads import PairingProfile
                >>> pairing_profiles = pce.pairing_profile.get(
                ...     params={'name': 'PP-DATABASE', 'max_results': 1}
                ... )
                >>> existing_profile = pairing_profiles[0]
                >>> update = PairingProfile(
                ...     name='PP-DATABASE-VENS',
                ...     enabled=False  # disable this profile
                ... )
                >>> pce.pairing_profile.update(existing_profile['href'], update)

            Args:
                reference (Union[str, Reference, dict]): the HREF of the pairing profile to update.
                body (Any): the update data.
            """
            kwargs['json'] = body
            self.pce.put(href_from(reference), include_org=False, **kwargs)

        def delete(self, reference: Union[str, Reference, dict], **kwargs) -> None:
            """Deletes an object in the PCE.

            Successful DELETE requests return a 204 No Content response.

            Args:
                reference (Union[str, Reference, dict]): the HREF of the object to delete.
            """
            self.pce.delete(href_from(reference), include_org=False, **kwargs)

        def _bulk_change(self, objects: List[IllumioObject], method: str, success_status: str, **kwargs) -> List[dict]:
            results = []
            while objects:
                kwargs['json'] = objects[:BULK_CHANGE_LIMIT]
                objects = objects[BULK_CHANGE_LIMIT:]
                endpoint = self._build_endpoint(DRAFT, None)
                response = self.pce.put('{}/{}'.format(endpoint, method), include_org=False, **kwargs)
                for result in response.json():
                    errors = result.get('errors', [])
                    if success_status and result['status'] != success_status:
                        errors.append({'token': result['token'], 'message': result['message']})
                    results.append({'href': result['href'], 'errors': errors})
            return results

        def bulk_create(self, objects_to_create: List[IllumioObject], **kwargs) -> List[dict]:
            """Creates a set of objects in the PCE.

            NOTE: Bulk creation can currently only be applied for Security Principals,
                Virtual Services and Workloads.

            Args:
                objects_to_create (List[IllumioObject]): list of objects to update.

            Returns:
                List[dict]: a list containing HREFs of created objects
                    as well as any errors returned from the PCE.
                    Has the following form:

                    [
                        {
                            'href': {object_href},
                            'errors': [
                                {
                                    'token': {error_type},
                                    'message': {error_message}
                                }
                            ]
                        }
                    ]
            """
            return self._bulk_change(objects_to_create, method='bulk_create', success_status='created', **kwargs)

        def bulk_update(self, objects_to_update: List[IllumioObject], **kwargs) -> List[dict]:
            """Updates a set of objects in the PCE.

            NOTE: Bulk updates can currently only be applied for Virtual Services and Workloads.

            Args:
                objects_to_update (List[IllumioObject]): list of objects to update.

            Returns:
                List[dict]: a list containing HREFs of updated objects
                    as well as any errors returned from the PCE.
                    Has the following form:

                    [
                        {
                            'href': {object_href},
                            'errors': [
                                {
                                    'token': {error_type},
                                    'message': {error_message}
                                }
                            ]
                        }
                    ]
            """
            return self._bulk_change(objects_to_update, method='bulk_update', success_status='updated', **kwargs)

        def bulk_delete(self, refs: List[Union[str, Reference, dict]], **kwargs) -> List[dict]:
            """Deletes a set of objects in the PCE.

            NOTE: Bulk updates can currently only be applied for Workloads.

            Args:
                hrefs (List[Union[str, Reference, dict]]): list of references to objects to delete.

            Returns:
                List[dict]: a list containing any errors that occurred during
                    the bulk operation. Has the following form:

                    [
                        {
                            'href': {object_href},
                            'errors': [
                                {
                                    'token': {error_type},
                                    'message': {error_message}
                                }
                            ]
                        }
                    ]
            """
            objects_to_delete = [Reference(href=href_from(reference)) for reference in refs]
            return self._bulk_change(objects_to_delete, method='bulk_delete', success_status=None, **kwargs)

    def __getattr__(self, name: str) -> _PCEObjectAPI:
        """Instantiates a generic API for registered PCE objects.

        Inspired by the Zabbix API: https://pypi.org/project/zabbix-api/
        """
        if name in self._apis:
            return self._apis[name]
        if name not in PCE_APIS:
            raise AttributeError("No such PCE API object: {}".format(name))
        api = self._PCEObjectAPI(pce=self, api_data=PCE_APIS[name])
        self._apis[name] = api
        return api

    def get_default_ip_list(self, **kwargs) -> IPList:
        """Retrieves the "Any (0.0.0.0/0 and ::/0)" default global IP list.

        Returns:
            IPList: decoded object representing the default global IP list.
        """
        params = kwargs.get('params', {})
        # retrieve by name as each org will use a different ID
        kwargs['params'] = {**params, **{'name': ANY_IP_LIST_NAME}}
        response = self.get('/sec_policy/active/ip_lists', **kwargs)
        return IPList.from_json(response.json()[0])

    def generate_pairing_key(self, pairing_profile_href: str, **kwargs) -> str:
        """Generates a pairing key using a pairing profile.

        Args:
            pairing_profile_href (str): the HREF of the pairing profile to use.

        Returns:
            str: the pairing key value.
        """
        kwargs['json'] = {}
        response = self.post('{}/pairing_key'.format(pairing_profile_href), include_org=False, **kwargs)
        return response.json().get('activation_code')

    @deprecated(deprecated_in='1.0.0')
    def get_traffic_flows(self, traffic_query: TrafficQuery, **kwargs) -> List[TrafficFlow]:
        """DEPRECATED (v1.0.0). Use `get_traffic_flows_async` instead.

        Retrieves Explorer traffic flows using the provided query.

        NOTE: this function is deprecated in the Illumio REST API, and is
        only provided for compatibility. The Illumio Explorer REST API
        documentation recommends using the async traffic flow query instead,
        provided here as `PolicyComputeEngine.get_traffic_flows_async`.

        See https://docs.illumio.com/core/21.5/Content/Guides/rest-api/visualization/explorer.htm#TrafficAnalysisQueries
        for details on traffic query parameters.

        Args:
            traffic_query (TrafficQuery): `TrafficQuery` object representing
                the query parameters.

        Returns:
            List[TrafficFlow]: list of `TrafficFlow` objects found using the
                provided query.
        """
        kwargs['json'] = traffic_query
        response = self.post('/traffic_flows/traffic_analysis_queries', **kwargs)
        return [TrafficFlow.from_json(flow) for flow in response.json()]

    def get_traffic_flows_async(self, query_name: str, traffic_query: TrafficQuery, **kwargs) -> List[TrafficFlow]:
        """Retrieves Explorer traffic flows using the provided query.

        See https://docs.illumio.com/core/21.5/Content/Guides/rest-api/visualization/explorer.htm#AsynchronousQueriesforTrafficFlows
        for details on async traffic query parameters.

        Usage:
            >>> from illumio.explorer import TrafficQuery
            >>> traffic_query = TrafficQuery.build(
            ...     start_date="2022-02-01T00:00:00Z",
            ...     end_date="2022-03-01T00:00:00Z",
            ...     include_services=[
            ...         {'port': 3389, 'proto': 'tcp'}
            ...     ],
            ...     policy_decisions=['potentially_blocked', 'unknown']
            ... )
            >>> traffic_query
            TrafficQuery(
                start_date='2022-02-01T00:00:00Z',
                end_date='2022-03-01T00:00:00Z',
                sources=TrafficQueryFilterBlock(
                    include=[],
                    exclude=[]
                ),
                destinations=TrafficQueryFilterBlock(
                    include=[],
                    exclude=[]
                ),
                services=TrafficQueryServiceBlock(
                    include=[
                        ServicePort(
                            port=3389,
                            proto=6,
                            ...
                        )
                    ],
                    exclude=[]
                ),
                policy_decisions=[
                    'potentially_blocked',
                    'unknown'
                ],
                ...
            )
            >>> traffic_flows = pce.get_traffic_flows_async(
            ...     query_name='rdp-traffic-feb-22',
            ...     traffic_query=traffic_query
            ... )
            >>> traffic_flows
            [
                TrafficFlow(
                    src=TrafficNode(
                        ip='10.0.9.14',
                        "ip_lists": [
                            {
                                "name": "IPL-INTERNAL",
                                "href": "/orgs/1/sec_policy/active/ip_lists/5",
                                ...
                            }
                        ],
                        ...
                    ),
                    dst=TrafficNode(
                        ip='10.0.6.63',
                        workload=Workload(
                            href='/orgs/1/workloads/6567900a-b49f-43cc-93a7-c892da39aad1',
                            name='WIN-JUMPBOX',
                            ...
                        ),
                        ...
                    ),
                    service=ServicePort(port=3389, proto=6),
                    num_connections=44,
                    state='closed',
                    timestamp_range=TimestampRange(
                        first_detected='2022-02-19T09:50:17Z',
                        last_detected='2022-02-19T10:12:36Z'
                    ),
                    policy_decision='potentially_blocked',
                    flow_direction='inbound',
                    ...
                ),
                ...
            ]

        Args:
            query_name (str): name for the async query job.
            traffic_query (TrafficQuery): `TrafficQuery` object representing
                the query parameters.

        Raises:
            IllumioApiException: if there is an error retrieving the async job
                results.

        Returns:
            List[TrafficFlow]: list of `TrafficFlow` objects found using the
                provided query.
        """
        try:
            traffic_query.query_name = query_name
            kwargs['json'] = traffic_query
            headers = kwargs.get('headers', {})
            kwargs['headers'] = {**headers, **{'Content-Type': 'application/json', 'Prefer': 'respond-async'}}
            response = self.post('/traffic_flows/async_queries', **kwargs)
            response.raise_for_status()
            query_status = response.json()
            location = query_status['href']

            collection_href = self._async_poll(location)

            response = self.get(collection_href, include_org=False)
            response.raise_for_status()
            return [TrafficFlow.from_json(flow) for flow in response.json()]
        except Exception as e:
            raise IllumioApiException from e

    def provision_policy_changes(self, change_description: str, hrefs: List[str], **kwargs) -> PolicyVersion:
        """Provisions policy changes for draft objects with the given HREFs.

        Usage:
            >>> from illumio.rules import RuleSet
            >>> rule_set = pce.rule_sets.create(
            ...     RuleSet(name='RS-RINGFENCE')
            ... )
            >>> changeset = pce.provision_policy_changes(
            ...     change_description='Provision ring-fence rule set',
            ...     hrefs=[rule_set.href]
            ... )
            >>> changeset
            PolicyVersion(
                href='/orgs/1/sec_policy/110',
                commit_message='Provision ring-fence rule set',
                version=110,
                workloads_affected=0,
                object_counts=PolicyObjectCounts(
                    label_groups=17,
                    services=8,
                    ...
                )
            )

        Args:
            change_description (str): the policy change description.
            hrefs (List[str]): the HREFs of the draft policy objects to provision.

        Raises:
            IllumioException: if an invalid HREF is provided.

        Returns:
            PolicyVersion: the decoded policy version object including the changeset.
        """
        policy_changeset = PolicyChangeset.build(hrefs)
        kwargs['json'] = {'update_description': change_description, 'change_subset': policy_changeset}
        response = self.post('/sec_policy', **kwargs)
        return PolicyVersion.from_json(response.json())


__all__ = ['PolicyComputeEngine']
