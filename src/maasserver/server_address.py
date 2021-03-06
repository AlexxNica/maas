# Copyright 2012-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Helper to obtain the MAAS server's address."""

__all__ = [
    'get_maas_facing_server_address',
    'get_maas_facing_server_addresses',
    'get_maas_facing_server_host',
    ]


from urllib.parse import urlparse

from maasserver.config import RegionConfiguration
from maasserver.enum import NODE_TYPE
from maasserver.exceptions import UnresolvableHost
from provisioningserver.utils.env import get_maas_id
from provisioningserver.utils.network import resolve_hostname


def get_maas_facing_server_host(rack_controller=None, default_region_ip=None):
    """Return configured MAAS server hostname, for use by nodes or workers.

    :param rack_controller: The `RackController` from the point of view of
        which the server host should be computed.
    :param default_region_ip: The default source IP address to be used, if a
        specific URL is not defined.
    :return: Hostname or IP address, as configured in the MAAS URL config
        setting or as configured on rack_controller.url.
    """
    if rack_controller is None or not rack_controller.url:
        if default_region_ip is not None:
            return default_region_ip
        with RegionConfiguration.open() as config:
            maas_url = config.maas_url
    else:
        maas_url = rack_controller.url
    return urlparse(maas_url).hostname


def get_maas_facing_server_address(rack_controller=None, ipv4=True, ipv6=True):
    """Return address where nodes and workers can reach the MAAS server.

    The address is taken from the configured MAAS URL or `controller.url`.
    Consult the 'maas-region local_config_set' command for details on
    how to set the MAAS URL.

    If there is more than one IP address for the host, the addresses
    will be sorted and the first IP address in the sorted set will be
    returned.  IPv4 addresses will be sorted before IPv6 addresses, so
    this prefers IPv4 addresses over IPv6 addresses.  It also prefers global
    IPv6 addresses over link-local IPv6 addresses.  Note, this is sorted:
        105.181.232.64
        ::ffff:101.1.1.1
        2001:db8::1
        fdd7:30::3
        fe80::1

    :param rack_controller: The rack controller from the point of view of
        which the server address should be computed.
    :param ipv4: Include IPv4 addresses?  Defaults to `True`.
    :param ipv6: Include IPv6 addresses?  Defaults to `True`.
    :return: An IP addresses as a unicode string.  If the configured URL
        uses a hostname, this function will resolve that hostname.
    :raise UnresolvableHost: if no IP addresses could be found for
        the hostname.

    """
    addresses = get_maas_facing_server_addresses(
        rack_controller, ipv4=ipv4, ipv6=ipv6, link_local=True)
    return min(addresses).format()


def get_maas_facing_server_addresses(
        rack_controller=None, ipv4=True, ipv6=True, link_local=False,
        include_alternates=False):
    """Return addresses for the MAAS server.

    The address is taken from the configured MAAS URL or `controller.url`.
    Consult the 'maas-region local_config_set' command for details on
    how to set the MAAS URL.

    If there is more than one IP address for the host, all of the addresses for
    the appropriate family will be returned.  (If link_local is False, then
    only non-link-local addresses are returned.

    To get the "best" address, see get_maas_facing_server_address().

    :param rack_controller: The rack controller from the point of view of
        which the server address should be computed.
    :param ipv4: Include IPv4 addresses?  Defaults to `True`.
    :param ipv6: Include IPv6 addresses?  Defaults to `True`.
    :param link_local: Include link-local addresses?   Defaults to `False`.
    :param include_alternates: Include secondary region controllers on the same
        subnet?  Defaults to `False`.
    :return: IP addresses as a list: [IPAddress, ...]  If the configured URL
        uses a hostname, this function will resolve that hostname.
    :raise UnresolvableHost: if no IP addresses could be found for
        the hostname.

    """
    hostname = get_maas_facing_server_host(rack_controller)
    if ipv6 or ipv4:
        addresses = resolve_hostname(
            hostname, 0 if (ipv6 and ipv4) else 4 if ipv4 else 6)
    else:
        addresses = set()
    if len(addresses) == 0:
        raise UnresolvableHost("No address found for host %s." % hostname)
    if not link_local:
        addresses = [ip for ip in addresses if not ip.is_link_local()]
    if include_alternates:
        maas_id = get_maas_id()
        if maas_id is not None:
            # Circular imports
            from maasserver.models import Subnet
            from maasserver.models import StaticIPAddress
            # Keep track of the regions already represented.
            regions = set()
            alternate_ips = []
            for ip in addresses:
                regions.add(maas_id + str(ip.version))
                if not ip.is_link_local():
                    # Since we only know that the IP address given in the MAAS
                    # URL is reachable, alternates must be pulled from the same
                    # subnet (until we know the "full mesh" of connectivity.)
                    subnet = Subnet.objects.get_best_subnet_for_ip(ip)
                    region_ips = StaticIPAddress.objects.filter(
                        subnet=subnet,
                        interface__node__node_type__in=(
                            NODE_TYPE.REGION_AND_RACK_CONTROLLER,
                            NODE_TYPE.REGION_CONTROLLER))
                    region_ips = region_ips.prefetch_related(
                        'interface_set__node')
                    region_ips = region_ips.order_by('ip')
                    for region_ip in region_ips:
                        for iface in region_ip.interface_set.all():
                            ipa = region_ip.get_ipaddress()
                            if ipa is None:
                                continue
                            # Pick at most one alternate IP address for each
                            # region, per address family.
                            id_plus_family = (
                                iface.node.system_id + str(ipa.version)
                            )
                            if id_plus_family in regions:
                                continue
                            else:
                                regions.add(id_plus_family)
                                alternate_ips.append(ipa)
            addresses.extend(alternate_ips)
    return addresses
