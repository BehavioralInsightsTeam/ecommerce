from django.conf import settings

from urlparse import urljoin

from threadlocals.threadlocals import get_current_request

from edx_rest_api_client.client import EdxRestApiClient

from ecommerce.core.exceptions import MissingRequestError


def get_ecommerce_url(path=''):
    """
    Returns path joined with the appropriate ecommerce URL root for the current site

    Raises:
        MissingRequestError: If the current ecommerce site is not in threadlocal storage
    """
    request = get_current_request()
    if request:
        ecommerce_url_root = "{}://{}".format(request.scheme, request.site.domain)
        return urljoin(ecommerce_url_root, path)
    raise MissingRequestError


def get_lms_commerce_api_url():
    return get_lms_url('/api/commerce/v1/')


def get_lms_dashboard_url():
    return get_lms_url('/dashboard')


def get_lms_enrollment_api_url():
    return get_lms_url('/api/enrollment/v1/enrollment')


def get_lms_heartbeat_url():
    return get_lms_url('/heartbeat')


def get_lms_url(path=''):
    """
    Returns path joined with the appropriate LMS URL root for the current site

    Raises:
        MissingRequestError: If the current ecommerce site is not in threadlocal storage
    """
    request = get_current_request()
    if request:
        return urljoin(request.site.siteconfiguration.lms_url_root, path)
    raise MissingRequestError


def get_oauth2_provider_url():
    return get_lms_url('/oauth2')


def get_course_discovery_client():

    request = get_current_request()

    # TODO: Cache the access_token for as long as it is valid.
    access_token, __ = EdxRestApiClient.get_oauth_access_token(
                '{root}/access_token'.format(root=get_oauth2_provider_url()),
                request.site.siteconfiguration.oauth_settings['SOCIAL_AUTH_EDX_OIDC_KEY'],
                request.site.siteconfiguration.oauth_settings['SOCIAL_AUTH_EDX_OIDC_SECRET']
            )
    course_discovery_client = EdxRestApiClient(
        settings.COURSE_DISCOVERY_ROOT,
        oauth_access_token=access_token
    )
    return course_discovery_client
