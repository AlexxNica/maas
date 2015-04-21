# Copyright 2012-2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `provisioningserver.power`.
"""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

import os
from random import randint
import re

from maastesting.factory import factory
from maastesting.matchers import MockCalledOnceWith
from maastesting.testcase import (
    MAASTestCase,
    MAASTwistedRunTest,
)
from mock import (
    ANY,
    Mock,
    sentinel,
)
from provisioningserver.drivers.power import (
    builtin_power_drivers,
    PowerDriverRegistry,
)
from provisioningserver.drivers.power.tests.test_base import (
    make_power_driver_base,
)
import provisioningserver.power.poweraction
from provisioningserver.power.poweraction import (
    is_power_driver,
    PowerAction,
    PowerActionFail,
    UnknownPowerType,
)
from provisioningserver.utils import (
    escape_py_literal,
    locate_config,
    ShellTemplate,
)
from testtools.matchers import (
    FileContains,
    IsInstance,
    MatchesException,
    Raises,
)
from twisted.internet.defer import Deferred


class TestPowerAction(MAASTestCase):
    """Tests for PowerAction."""

    run_tests_with = MAASTwistedRunTest.make_factory(timeout=5)

    def configure_templates_dir(self, path):
        """Configure POWER_TEMPLATES_DIR to `path`."""
        self.patch(PowerAction, 'get_template_basedir').return_value = path

    def test_init_raises_for_unknown_powertype(self):
        powertype = factory.make_name("powertype", sep='')
        self.assertRaises(
            UnknownPowerType,
            PowerAction, powertype)

    def test_init_stores_ether_wake_type(self):
        pa = PowerAction('ether_wake')
        self.assertEqual('ether_wake', pa.power_type)

    def test_init_stores_template_path(self):
        power_type = 'ether_wake'
        pa = PowerAction(power_type)
        path = os.path.join(
            pa.get_template_basedir(),
            power_type + ".template")
        self.assertEqual(path, pa.path)

    def test_template_basedir_defaults_to_config_dir(self):
        power_type = 'ether_wake'
        self.assertEqual(
            locate_config('templates/power'),
            PowerAction(power_type).get_template_basedir())

    def test_template_basedir_prefers_configured_value(self):
        power_type = 'ether_wake'
        template_name = '%s.template' % power_type
        template = self.make_file(name=template_name)
        template_dir = os.path.dirname(template)
        self.configure_templates_dir(template_dir)
        self.assertEqual(
            template_dir,
            PowerAction('ether_wake').get_template_basedir())

    def test_get_template_retrieves_template(self):
        pa = PowerAction('ether_wake')
        template = pa.get_template()
        self.assertIsInstance(template, ShellTemplate)
        self.assertThat(pa.path, FileContains(template.content))

    def test_get_template_looks_for_template_in_template_basedir(self):
        contents = factory.make_string()
        power_type = 'ether_wake'
        template_name = '%s.template' % power_type
        template = self.make_file(name=template_name, contents=contents)
        self.configure_templates_dir(os.path.dirname(template))
        self.assertEqual(
            contents,
            PowerAction(power_type).get_template().content)

    def test_render_template(self):
        # render_template() should take a template string and substitue
        # its variables.
        pa = PowerAction('ether_wake')
        template = ShellTemplate("template: {{mac}}")
        rendered = pa.render_template(
            template, pa.update_context({"mac": "mymac"}))
        self.assertEqual("template: mymac", rendered)

    def test_render_template_raises_PowerActionFail(self):
        # If not enough arguments are supplied to fill in template
        # variables then a PowerActionFail is raised.
        pa = PowerAction('ether_wake')
        template_name = factory.make_string()
        template = ShellTemplate("template: {{mac}}", name=template_name)
        self.assertThat(
            lambda: pa.render_template(template, pa.update_context({})),
            Raises(MatchesException(
                PowerActionFail,
                "ether_wake failed:\n"
                "name 'mac' is not defined at line \d+ column \d+ "
                "in file %s" % re.escape(template_name))))

    def test_execute_calls_execute_power_template(self):
        template = "echo working {{mac}} > {{outfile}}"
        power_action = PowerAction('ether_wake')
        power_action.path = self._create_template_file(template)
        execute_power_template = self.patch(
            power_action, "execute_power_template")
        power_action.execute(testing="test")

        self.assertThat(
            execute_power_template, MockCalledOnceWith(testing="test"))

    def test_execute_calls_execute_power_driver(self):
        power_type = factory.make_name("power_type")
        power_driver = make_power_driver_base(name=power_type)
        builtin_power_drivers.append(power_driver)
        self.addCleanup(builtin_power_drivers.remove, power_driver)
        power_action = PowerAction(power_type)
        execute_power_driver = self.patch(
            power_action, "execute_power_driver")
        power_action.execute(testing="test")

        self.expectThat(
            execute_power_driver, MockCalledOnceWith(testing="test"))
        self.expectThat(
            execute_power_driver, IsInstance(Deferred))

    def _create_template_file(self, template):
        """Create a temporary template file with the given contents."""
        return self.make_file("testscript.sh", template)

    def run_action(self, path, **kwargs):
        pa = PowerAction('ether_wake')
        pa.path = path
        return pa.execute_power_template(**kwargs)

    def test_execute_power_template(self):
        # execute_power_template() should run the template through a shell.
        output_file = self.make_file(
            name='output', contents="(Output should go here)")
        template = "echo working {{mac}} > {{outfile}}"
        path = self._create_template_file(template)

        self.run_action(path, mac="test", outfile=output_file)
        self.assertThat(output_file, FileContains("working test\n"))

    def test_execute_power_template_return_execution_result(self):
        template = "echo ' test \n'"
        path = self._create_template_file(template)
        output = self.run_action(path)
        # run_action() returns the 'stripped' output.
        self.assertEqual('test', output)

    def test_execute_power_template_raises_PowerActionFail_for_failure(self):
        path = self._create_template_file("this_is_not_valid_shell")
        self.assertThat(
            lambda: self.run_action(path),
            Raises(MatchesException(
                PowerActionFail, "ether_wake failed with return code 127")))

    def test_execute_power_template_raises_PowerActionFail_with_output(self):
        path = self._create_template_file("echo reason for failure; exit 1")
        self.assertThat(
            lambda: self.run_action(path),
            Raises(
                MatchesException(PowerActionFail, ".*:\nreason for failure")))

    def make_power_driver_scaffold(self):
        power_type = factory.make_name("power_type")
        power_driver = make_power_driver_base(name=power_type)
        builtin_power_drivers.append(power_driver)
        self.addCleanup(builtin_power_drivers.remove, power_driver)
        PowerDriverRegistry.register_item(power_driver.name, power_driver)
        self.addCleanup(PowerDriverRegistry.unregister_item, power_driver.name)
        power_action = PowerAction(power_type)
        return power_type, power_driver, power_action

    def test_execute_power_driver_calls_perform_power(self):
        power_type, power_driver, power_action = (
            self.make_power_driver_scaffold())
        perform_power = self.patch(power_driver, "perform_power")
        context = {'power_change': 'on'}
        updated_context = power_action.update_context(context)
        power_action.execute_power_driver(**context)

        self.assertThat(perform_power, MockCalledOnceWith(updated_context))

    def test_execute_power_driver_calls_query(self):
        power_type, power_driver, power_action = (
            self.make_power_driver_scaffold())
        query = self.patch(power_driver, "query")
        context = {'power_change': 'query'}
        updated_context = power_action.update_context(context)
        power_action.execute_power_driver(**context)

        self.assertThat(query, MockCalledOnceWith(updated_context))

    def test_execute_power_driver_raises_PowerActionFail_for_failure(self):
        power_type, power_driver, power_action = (
            self.make_power_driver_scaffold())
        context = {'power_change': 'error'}
        updated_context = power_action.update_context(context)

        self.assertRaises(
            PowerActionFail, power_action.execute_power_driver,
            **updated_context)

    def test_wake_on_lan_cannot_shut_down_node(self):
        pa = PowerAction('ether_wake')
        self.assertRaises(
            PowerActionFail,
            pa.execute_power_template, power_change='off',
            mac=factory.make_mac_address())

    def test_fence_cdu_checks_state(self):
        # We can't test the fence_cdu template in detail (and it may be
        # customized), but by making it use "echo" instead of a real
        # fence_cdu we can make it get a bogus answer from its status check.
        # The bogus answer is actually the rest of the fence_cdu command
        # line.  It will complain about this and fail.
        action = PowerAction("fence_cdu")
        script = action.render_template(
            action.get_template(),
            action.update_context(dict(
                power_change='on', power_address='mysystem',
                power_id='system', power_user='me', power_pass='me',
                fence_cdu='echo')),
        )
        output = action.run_shell(script)
        self.assertIn("Got unknown power state from fence_cdu", output)

    def configure_power_config_dir(self, path):
        """Configure POWER_CONFIG_DIR to `path`."""
        self.patch(PowerAction, 'get_config_basedir').return_value = path

    def test_config_basedir_defaults_to_local_dir(self):
        power_type = 'ether_wake'
        self.assertEqual(
            locate_config('templates/power'),
            PowerAction(power_type).get_config_basedir())

    def test_ipmi_script_includes_config_dir(self):
        conf_dir = factory.make_name('power_config_dir')
        self.configure_power_config_dir(conf_dir)
        action = PowerAction('ipmi')
        script = action.render_template(
            action.get_template(),
            action.update_context(dict(
                power_change='on', power_address='mystystem',
                power_user='me', power_pass='me', ipmipower='echo',
                ipmi_chassis_config='echo', config_dir='dir',
                ipmi_config='file.conf', power_driver='LAN',
                ip_address='', power_off_mode='hard')),
        )
        self.assertIn(conf_dir, script)

    def test_moonshot_checks_state(self):
        # We can't test the moonshot template in detail (and it may be
        # customized), but by making it use "echo" instead of a real
        # ipmi we can make it get a bogus answer from its status check.
        # The bogus answer is actually the rest of the ipmi command
        # line.  It will complain about this and fail.
        action = PowerAction("moonshot")
        script = action.render_template(
            action.get_template(),
            action.update_context(dict(
                power_change='on', power_address='mysystem',
                power_user='me', power_pass='me', power_hwaddress='me',
                ipmitool='echo')),
        )
        output = action.run_shell(script)
        self.assertIn("Got unknown power state from ipmipower", output)

    def test_ucsm_renders_template(self):
        # I'd like to assert that escape_py_literal is being used here,
        # but it's not obvious how to mock things in the template
        # rendering namespace so I passed on that.
        action = PowerAction('ucsm')
        script = action.render_template(
            action.get_template(),
            action.update_context(dict(
                power_address='foo', power_user='bar', power_pass='baz',
                uuid=factory.make_UUID(), power_change='on')),
        )
        self.assertIn('power_control_ucsm', script)

    def test_mscm_renders_template(self):
        context = {
            'power_address': 'foo', 'power_user': 'bar', 'power_pass': 'baz',
            'node_id': 'c1n1', 'power_change': 'on',
        }
        action = PowerAction('mscm')
        action.update_context(context)
        context['escape_py_literal'] = Mock()
        script = action.render_template(action.get_template(), context)
        self.assertIn('power_control_mscm', script)

    def test_apc_renders_template(self):
        context = {
            'power_address': 'foo', 'power_user': 'bar', 'power_pass': 'baz',
            'node_outlet': "%s" % randint(1, 16), 'power_change': 'on',
        }
        action = PowerAction('apc')
        action.update_context(context)
        context['escape_py_literal'] = Mock()
        script = action.render_template(action.get_template(), context)
        self.assertIn('power_control_apc', script)

    def test_msftocs_renders_template(self):
        context = {
            'power_address': 'foo', 'power_port': 'foz', 'power_user': 'bar',
            'power_pass': 'baz', 'blade_id': '%d' % randint(1, 24),
            'power_change': 'on',
        }
        action = PowerAction('msftocs')
        action.update_context(context)
        context['escape_py_literal'] = Mock()
        script = action.render_template(action.get_template(), context)
        self.assertIn('power_control_msftocs', script)


class TestTemplateContext(MAASTestCase):

    def make_stubbed_power_action(self):
        power_action = PowerAction("ipmi")
        render_template = self.patch(power_action, "render_template")
        render_template.return_value = "echo done"
        return power_action

    def test_basic_context(self):
        power_action = self.make_stubbed_power_action()
        result = power_action.execute_power_template()
        self.assertEqual("done", result)
        self.assertThat(
            power_action.render_template,
            MockCalledOnceWith(
                template=ANY,
                context=dict(
                    config_dir=locate_config("templates/power"),
                    escape_py_literal=escape_py_literal, ip_address=None,
                ),
            ))

    def test_ip_address_is_unmolested_if_set(self):
        power_action = self.make_stubbed_power_action()
        ip_address = factory.make_ipv6_address()
        result = power_action.execute_power_template(ip_address=ip_address)
        self.assertEqual("done", result)
        self.assertThat(
            power_action.render_template,
            MockCalledOnceWith(
                template=ANY,
                context=dict(
                    config_dir=locate_config("templates/power"),
                    escape_py_literal=escape_py_literal,
                    ip_address=ip_address,
                ),
            ))

    def test_execute_power_template_looks_up_ip_address_from_mac_address(self):
        find_ip_via_arp = self.patch(
            provisioningserver.power.poweraction, "find_ip_via_arp")
        find_ip_via_arp.return_value = sentinel.ip_address_from_mac

        power_action = self.make_stubbed_power_action()
        mac_address = factory.make_mac_address()
        result = power_action.execute_power_template(mac_address=mac_address)
        self.assertEqual("done", result)
        self.assertThat(
            power_action.render_template,
            MockCalledOnceWith(
                template=ANY,
                context=dict(
                    config_dir=locate_config("templates/power"),
                    escape_py_literal=escape_py_literal,
                    ip_address=sentinel.ip_address_from_mac,
                    mac_address=mac_address,
                ),
            ))


class TestIsPowerDriver(MAASTestCase):

    def test__finds_power_driver(self):
        power_type = factory.make_name("power_type")
        power_driver = make_power_driver_base(name=power_type)
        builtin_power_drivers.append(power_driver)
        self.addCleanup(builtin_power_drivers.remove, power_driver)
        result = is_power_driver(power_type)

        self.assertTrue(result)

    def test__does_not_find_power_driver(self):
        false_power_type = factory.make_name("power_type")
        result = is_power_driver(false_power_type)

        self.assertFalse(result)