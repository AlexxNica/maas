# Copyright 2012-2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for :class:`NodeGroupInterface`."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from django.core.exceptions import ValidationError
from maasserver.enum import (
    NODEGROUP_STATUS,
    NODEGROUPINTERFACE_MANAGEMENT,
    NODEGROUPINTERFACE_MANAGEMENT_CHOICES_DICT,
    )
from maasserver.models import (
    NodeGroup,
    NodeGroupInterface,
    )
from maasserver.models.nodegroupinterface import MINIMUM_NETMASK_BITS
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.utils.network import make_network
from netaddr import IPNetwork


def make_interface(network=None):
    nodegroup = factory.make_node_group(
        status=NODEGROUP_STATUS.ACCEPTED,
        management=NODEGROUPINTERFACE_MANAGEMENT.DHCP_AND_DNS,
        network=network)
    [interface] = nodegroup.get_managed_interfaces()
    return interface


class TestNodeGroupInterface(MAASServerTestCase):

    def test_network(self):
        network = IPNetwork("10.0.0.3/24")
        interface = make_interface(network=network)
        self.assertEqual(IPNetwork("10.0.0.0/24"), interface.network)

    def test_network_is_defined_when_netmask_is(self):
        interface = make_interface()
        interface.ip = "10.0.0.9"
        interface.subnet_mask = "255.255.255.0"
        self.assertIsInstance(interface.network, IPNetwork)

    def test_network_does_not_require_broadcast_address(self):
        interface = make_interface()
        interface.broadcast_ip = None
        self.assertIsInstance(interface.network, IPNetwork)

    def test_network_does_not_require_nonempty_broadcast_address(self):
        interface = make_interface()
        interface.broadcast_ip = ""
        self.assertIsInstance(interface.network, IPNetwork)

    def test_network_is_undefined_when_subnet_mask_is_None(self):
        interface = make_interface()
        interface.subnet_mask = None
        self.assertIsNone(interface.network)

    def test_network_is_undefined_when_subnet_mask_is_empty(self):
        interface = make_interface()
        interface.subnet_mask = ""
        self.assertIsNone(interface.network)

    def test_display_management_display_management(self):
        interface = make_interface()
        self.assertEqual(
            NODEGROUPINTERFACE_MANAGEMENT_CHOICES_DICT[interface.management],
            interface.display_management())

    def test_clean_ips_in_network_validates_IP(self):
        network = IPNetwork('192.168.0.3/24')
        ip_outside_network = '192.168.2.1'
        checked_fields = [
            'broadcast_ip',
            'router_ip',
            'ip_range_low',
            'ip_range_high',
            ]
        for field in checked_fields:
            nodegroup = factory.make_node_group(network=network)
            [interface] = nodegroup.get_managed_interfaces()
            setattr(interface, field, ip_outside_network)
            message = "%s not in the %s network" % (
                ip_outside_network,
                '192.168.0.0/24',
                )
            exception = self.assertRaises(
                ValidationError, interface.full_clean)
            self.assertEqual({field: [message]}, exception.message_dict)

    def test_clean_network(self):
        nodegroup = factory.make_node_group(
            network=IPNetwork('192.168.0.3/24'))
        [interface] = nodegroup.get_managed_interfaces()
        # Set a bogus subnet mask.
        interface.subnet_mask = '0.9.0.4'
        message = "invalid IPNetwork %s/0.9.0.4" % interface.ip
        exception = self.assertRaises(ValidationError, interface.full_clean)
        self.assertEqual(
            {'subnet_mask': [message]},
            exception.message_dict)

    def test_clean_network_rejects_huge_network(self):
        big_network = make_network('1.2.3.4', MINIMUM_NETMASK_BITS - 1)
        exception = self.assertRaises(
            ValidationError, factory.make_node_group, network=big_network)
        message = (
            "Cannot create an address space bigger than a /%d network.  "
            "This network is a /%d network." % (
                MINIMUM_NETMASK_BITS, MINIMUM_NETMASK_BITS - 1))
        self.assertEqual(
            {'subnet_mask': [message]},
            exception.message_dict)

    def test_clean_network_accepts_network_if_not_too_big(self):
        network = make_network('1.2.3.4', MINIMUM_NETMASK_BITS)
        self.assertIsInstance(
            factory.make_node_group(network=network), NodeGroup)

    def test_clean_network_accepts_big_network_if_unmanaged(self):
        network = make_network('1.2.3.4', MINIMUM_NETMASK_BITS - 1)
        nodegroup = factory.make_node_group(
            network=network,
            management=NODEGROUPINTERFACE_MANAGEMENT.UNMANAGED)
        self.assertIsInstance(nodegroup, NodeGroup)

    def test_clean_network_config_if_managed(self):
        network = IPNetwork('192.168.0.3/24')
        checked_fields = [
            'interface',
            'subnet_mask',
            'router_ip',
            'ip_range_low',
            'ip_range_high',
            ]
        for field in checked_fields:
            nodegroup = factory.make_node_group(
                network=network,
                management=NODEGROUPINTERFACE_MANAGEMENT.DHCP_AND_DNS)
            [interface] = nodegroup.get_managed_interfaces()
            setattr(interface, field, '')
            exception = self.assertRaises(
                ValidationError, interface.full_clean)
            message = (
                "That field cannot be empty (unless that interface is "
                "'unmanaged')")
            self.assertEqual({field: [message]}, exception.message_dict)

    def test_clean_network_config_sets_default_if_netmask_not_given(self):
        network = factory.getRandomNetwork()
        nodegroup = factory.make_node_group(
            network=network,
            management=NODEGROUPINTERFACE_MANAGEMENT.DHCP_AND_DNS)
        [interface] = nodegroup.get_managed_interfaces()
        interface.full_clean()
        self.assertEqual(unicode(network.broadcast), interface.broadcast_ip)

    def test_clean_network_config_sets_no_broadcast_without_netmask(self):
        network = factory.getRandomNetwork()
        nodegroup = factory.make_node_group(
            network=network,
            management=NODEGROUPINTERFACE_MANAGEMENT.UNMANAGED)
        interface = NodeGroupInterface.objects.get(nodegroup=nodegroup)
        interface.subnet_mask = None
        interface.broadcast_ip = None
        interface.full_clean()
        self.assertIsNone(interface.broadcast_ip)
