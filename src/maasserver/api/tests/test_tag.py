# Copyright 2013-2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Tags API."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

import httplib
import json

from django.core.urlresolvers import reverse
from maasserver.enum import NODE_STATUS
from maasserver.models import Tag
from maasserver.models.node import generate_node_system_id
from maasserver.testing.api import (
    APITestCase,
    make_worker_client,
)
from maasserver.testing.factory import factory
from maasserver.testing.oauthclient import OAuthAuthenticatedClient
from maasserver.testing.orm import reload_object
from maastesting.matchers import (
    MockCalledOnceWith,
    MockCallsMatch,
)
from metadataserver.models.commissioningscript import inject_lshw_result
from mock import (
    ANY,
    call,
)
from testtools.matchers import MatchesStructure


def patch_populate_tags(test):
    from maasserver import populate_tags
    return test.patch_autospec(populate_tags, "populate_tags")


class TestTagAPI(APITestCase):
    """Tests for /api/1.0/tags/<tagname>/."""

    def test_handler_path(self):
        self.assertEqual(
            '/api/1.0/tags/tag-name/',
            reverse('tag_handler', args=['tag-name']))

    def get_tag_uri(self, tag):
        """Get the API URI for `tag`."""
        return reverse('tag_handler', args=[tag.name])

    def test_DELETE_requires_admin(self):
        tag = factory.make_Tag()
        response = self.client.delete(self.get_tag_uri(tag))
        self.assertEqual(httplib.FORBIDDEN, response.status_code)
        self.assertItemsEqual([tag], Tag.objects.filter(id=tag.id))

    def test_DELETE_removes_tag(self):
        self.become_admin()
        tag = factory.make_Tag()
        response = self.client.delete(self.get_tag_uri(tag))
        self.assertEqual(httplib.NO_CONTENT, response.status_code)
        self.assertFalse(Tag.objects.filter(id=tag.id).exists())

    def test_DELETE_404(self):
        self.become_admin()
        url = reverse('tag_handler', args=['no-tag'])
        response = self.client.delete(url)
        self.assertEqual(httplib.NOT_FOUND, response.status_code)

    def test_GET_returns_tag(self):
        # The api allows for fetching a single Node (using system_id).
        tag = factory.make_Tag('tag-name')
        url = reverse('tag_handler', args=['tag-name'])
        response = self.client.get(url)

        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual(tag.name, parsed_result['name'])
        self.assertEqual(tag.definition, parsed_result['definition'])
        self.assertEqual(tag.comment, parsed_result['comment'])

    def test_GET_refuses_to_access_nonexistent_node(self):
        # When fetching a Tag, the api returns a 'Not Found' (404) error
        # if no tag is found.
        url = reverse('tag_handler', args=['no-such-tag'])
        response = self.client.get(url)
        self.assertEqual(httplib.NOT_FOUND, response.status_code)

    def test_PUT_refuses_non_superuser(self):
        tag = factory.make_Tag()
        response = self.client.put(
            self.get_tag_uri(tag), {'comment': 'A special comment'})
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_PUT_updates_tag(self):
        self.become_admin()
        tag = factory.make_Tag()
        # Note that 'definition' is not being sent
        response = self.client.put(
            self.get_tag_uri(tag),
            {'name': 'new-tag-name', 'comment': 'A random comment'})

        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual('new-tag-name', parsed_result['name'])
        self.assertEqual('A random comment', parsed_result['comment'])
        self.assertEqual(tag.definition, parsed_result['definition'])
        self.assertFalse(Tag.objects.filter(name=tag.name).exists())
        self.assertTrue(Tag.objects.filter(name='new-tag-name').exists())

    def test_PUT_updates_node_associations(self):
        populate_tags = patch_populate_tags(self)
        tag = factory.make_Tag(definition='//node/foo')
        self.expectThat(populate_tags, MockCalledOnceWith(tag))
        self.become_admin()
        response = self.client.put(
            self.get_tag_uri(tag),
            {'definition': '//node/bar'})
        self.assertEqual(httplib.OK, response.status_code)
        self.expectThat(populate_tags, MockCallsMatch(call(tag), call(tag)))

    def test_GET_nodes_with_no_nodes(self):
        tag = factory.make_Tag()
        response = self.client.get(self.get_tag_uri(tag), {'op': 'nodes'})

        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual([], parsed_result)

    def test_GET_nodes_returns_nodes(self):
        tag = factory.make_Tag()
        node1 = factory.make_Node()
        # Create a second node that isn't tagged.
        factory.make_Node()
        node1.tags.add(tag)
        response = self.client.get(self.get_tag_uri(tag), {'op': 'nodes'})

        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual([node1.system_id],
                         [r['system_id'] for r in parsed_result])

    def test_GET_nodes_hides_invisible_nodes(self):
        user2 = factory.make_User()
        node1 = factory.make_Node()
        node2 = factory.make_Node(status=NODE_STATUS.ALLOCATED, owner=user2)
        tag = factory.make_Tag()
        node1.tags.add(tag)
        node2.tags.add(tag)

        response = self.client.get(self.get_tag_uri(tag), {'op': 'nodes'})

        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual([node1.system_id],
                         [r['system_id'] for r in parsed_result])
        # However, for the other user, they should see the result
        client2 = OAuthAuthenticatedClient(user2)
        response = client2.get(self.get_tag_uri(tag), {'op': 'nodes'})
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertItemsEqual([node1.system_id, node2.system_id],
                              [r['system_id'] for r in parsed_result])

    def test_PUT_invalid_definition(self):
        self.become_admin()
        node = factory.make_Node()
        inject_lshw_result(node, b'<node ><child/></node>')
        tag = factory.make_Tag(definition='//child')
        node.tags.add(tag)
        self.assertItemsEqual([tag.name], node.tag_names())
        response = self.client.put(
            self.get_tag_uri(tag), {'definition': 'invalid::tag'})

        self.assertEqual(httplib.BAD_REQUEST, response.status_code)
        # The tag should not be modified
        tag = reload_object(tag)
        self.assertItemsEqual([tag.name], node.tag_names())
        self.assertEqual('//child', tag.definition)

    def test_POST_update_nodes_unknown_tag(self):
        self.become_admin()
        name = factory.make_name()
        response = self.client.post(
            reverse('tag_handler', args=[name]),
            {'op': 'update_nodes'})
        self.assertEqual(httplib.NOT_FOUND, response.status_code)

    def test_POST_update_nodes_changes_associations(self):
        tag = factory.make_Tag()
        self.become_admin()
        node_first = factory.make_Node()
        node_second = factory.make_Node()
        node_first.tags.add(tag)
        self.assertItemsEqual([node_first], tag.node_set.all())
        response = self.client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node_second.system_id],
                'remove': [node_first.system_id],
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertItemsEqual([node_second], tag.node_set.all())
        self.assertEqual({'added': 1, 'removed': 1}, parsed_result)

    def test_POST_update_nodes_ignores_unknown_nodes(self):
        tag = factory.make_Tag()
        self.become_admin()
        unknown_add_system_id = generate_node_system_id()
        unknown_remove_system_id = generate_node_system_id()
        self.assertItemsEqual([], tag.node_set.all())
        response = self.client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [unknown_add_system_id],
                'remove': [unknown_remove_system_id],
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertItemsEqual([], tag.node_set.all())
        self.assertEqual({'added': 0, 'removed': 0}, parsed_result)

    def test_POST_update_nodes_doesnt_require_add_or_remove(self):
        tag = factory.make_Tag()
        node = factory.make_Node()
        self.become_admin()
        self.assertItemsEqual([], tag.node_set.all())
        response = self.client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node.system_id],
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual({'added': 1, 'removed': 0}, parsed_result)
        response = self.client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'remove': [node.system_id],
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual({'added': 0, 'removed': 1}, parsed_result)

    def test_POST_update_nodes_rejects_normal_user(self):
        tag = factory.make_Tag()
        node = factory.make_Node()
        response = self.client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node.system_id],
            })
        self.assertEqual(httplib.FORBIDDEN, response.status_code)
        self.assertItemsEqual([], tag.node_set.all())

    def test_POST_update_nodes_allows_nodegroup_worker(self):
        tag = factory.make_Tag()
        nodegroup = factory.make_NodeGroup()
        node = factory.make_Node(nodegroup=nodegroup)
        client = make_worker_client(nodegroup)
        response = client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node.system_id],
                'nodegroup': nodegroup.uuid,
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual({'added': 1, 'removed': 0}, parsed_result)
        self.assertItemsEqual([node], tag.node_set.all())

    def test_POST_update_nodes_refuses_unidentified_nodegroup_worker(self):
        tag = factory.make_Tag()
        nodegroup = factory.make_NodeGroup()
        node = factory.make_Node(nodegroup=nodegroup)
        client = make_worker_client(nodegroup)
        # We don't pass nodegroup:uuid so we get refused
        response = client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node.system_id],
            })
        self.assertEqual(httplib.FORBIDDEN, response.status_code)
        self.assertItemsEqual([], tag.node_set.all())

    def test_POST_update_nodes_refuses_non_nodegroup_worker(self):
        tag = factory.make_Tag()
        nodegroup = factory.make_NodeGroup()
        node = factory.make_Node(nodegroup=nodegroup)
        response = self.client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node.system_id],
                'nodegroup': nodegroup.uuid,
            })
        self.assertEqual(httplib.FORBIDDEN, response.status_code)
        self.assertItemsEqual([], tag.node_set.all())

    def test_POST_update_nodes_doesnt_modify_other_nodegroup_nodes(self):
        tag = factory.make_Tag()
        nodegroup_mine = factory.make_NodeGroup()
        nodegroup_theirs = factory.make_NodeGroup()
        node_theirs = factory.make_Node(nodegroup=nodegroup_theirs)
        client = make_worker_client(nodegroup_mine)
        response = client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node_theirs.system_id],
                'nodegroup': nodegroup_mine.uuid,
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual({'added': 0, 'removed': 0}, parsed_result)
        self.assertItemsEqual([], tag.node_set.all())

    def test_POST_update_nodes_ignores_incorrect_definition(self):
        tag = factory.make_Tag()
        orig_def = tag.definition
        nodegroup = factory.make_NodeGroup()
        node = factory.make_Node(nodegroup=nodegroup)
        client = make_worker_client(nodegroup)
        tag.definition = '//new/node/definition'
        tag.save()
        response = client.post(
            self.get_tag_uri(tag), {
                'op': 'update_nodes',
                'add': [node.system_id],
                'nodegroup': nodegroup.uuid,
                'definition': orig_def,
            })
        self.assertEqual(httplib.CONFLICT, response.status_code)
        self.assertItemsEqual([], tag.node_set.all())
        self.assertItemsEqual([], node.tags.all())

    def test_POST_rebuild_rebuilds_node_mapping(self):
        populate_tags = patch_populate_tags(self)
        tag = factory.make_Tag(definition='//foo/bar')
        self.become_admin()
        self.assertThat(populate_tags, MockCalledOnceWith(tag))
        response = self.client.post(self.get_tag_uri(tag), {'op': 'rebuild'})
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual({'rebuilding': tag.name}, parsed_result)
        self.assertThat(populate_tags, MockCallsMatch(call(tag), call(tag)))

    def test_POST_rebuild_leaves_manual_tags(self):
        tag = factory.make_Tag(definition='')
        node = factory.make_Node()
        node.tags.add(tag)
        self.assertItemsEqual([node], tag.node_set.all())
        self.become_admin()
        response = self.client.post(self.get_tag_uri(tag), {'op': 'rebuild'})
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual({'rebuilding': tag.name}, parsed_result)
        self.assertItemsEqual([node], tag.node_set.all())

    def test_POST_rebuild_unknown_404(self):
        self.become_admin()
        response = self.client.post(
            reverse('tag_handler', args=['unknown-tag']),
            {'op': 'rebuild'})
        self.assertEqual(httplib.NOT_FOUND, response.status_code)

    def test_POST_rebuild_requires_admin(self):
        tag = factory.make_Tag(definition='/foo/bar')
        response = self.client.post(
            self.get_tag_uri(tag), {'op': 'rebuild'})
        self.assertEqual(httplib.FORBIDDEN, response.status_code)


class TestTagsAPI(APITestCase):

    def test_handler_path(self):
        self.assertEqual(
            '/api/1.0/tags/', reverse('tags_handler'))

    def test_GET_list_without_tags_returns_empty_list(self):
        response = self.client.get(reverse('tags_handler'), {'op': 'list'})
        self.assertItemsEqual([], json.loads(response.content))

    def test_POST_new_refuses_non_admin(self):
        name = factory.make_string()
        response = self.client.post(
            reverse('tags_handler'),
            {
                'op': 'new',
                'name': name,
                'comment': factory.make_string(),
                'definition': factory.make_string(),
            })
        self.assertEqual(httplib.FORBIDDEN, response.status_code)
        self.assertFalse(Tag.objects.filter(name=name).exists())

    def test_POST_new_creates_tag(self):
        self.become_admin()
        name = factory.make_string()
        definition = '//node'
        comment = factory.make_string()
        response = self.client.post(
            reverse('tags_handler'),
            {
                'op': 'new',
                'name': name,
                'comment': comment,
                'definition': definition,
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual(name, parsed_result['name'])
        self.assertEqual(comment, parsed_result['comment'])
        self.assertEqual(definition, parsed_result['definition'])
        self.assertTrue(Tag.objects.filter(name=name).exists())

    def test_POST_new_without_definition_creates_tag(self):
        self.become_admin()
        name = factory.make_string()
        comment = factory.make_string()
        response = self.client.post(
            reverse('tags_handler'),
            {
                'op': 'new',
                'name': name,
                'comment': comment,
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual(name, parsed_result['name'])
        self.assertEqual(comment, parsed_result['comment'])
        self.assertEqual("", parsed_result['definition'])
        self.assertTrue(Tag.objects.filter(name=name).exists())

    def test_POST_new_invalid_tag_name(self):
        self.become_admin()
        # We do not check the full possible set of invalid names here, a more
        # thorough check is done in test_tag, we just check that we get a
        # reasonable error here.
        invalid = 'invalid:name'
        definition = '//node'
        comment = factory.make_string()
        response = self.client.post(
            reverse('tags_handler'),
            {
                'op': 'new',
                'name': invalid,
                'comment': comment,
                'definition': definition,
            })
        self.assertEqual(
            httplib.BAD_REQUEST, response.status_code,
            'We did not get BAD_REQUEST for an invalid tag name: %r'
            % (invalid,))
        self.assertFalse(Tag.objects.filter(name=invalid).exists())

    def test_POST_new_kernel_opts(self):
        self.become_admin()
        name = factory.make_string()
        definition = '//node'
        comment = factory.make_string()
        extra_kernel_opts = factory.make_string()
        response = self.client.post(
            reverse('tags_handler'),
            {
                'op': 'new',
                'name': name,
                'comment': comment,
                'definition': definition,
                'kernel_opts': extra_kernel_opts,
            })
        self.assertEqual(httplib.OK, response.status_code)
        parsed_result = json.loads(response.content)
        self.assertEqual(name, parsed_result['name'])
        self.assertEqual(comment, parsed_result['comment'])
        self.assertEqual(definition, parsed_result['definition'])
        self.assertEqual(extra_kernel_opts, parsed_result['kernel_opts'])
        self.assertEqual(
            extra_kernel_opts, Tag.objects.filter(name=name)[0].kernel_opts)

    def test_POST_new_populates_nodes(self):
        populate_tags = patch_populate_tags(self)
        self.become_admin()
        name = factory.make_string()
        definition = '//node/child'
        comment = factory.make_string()
        response = self.client.post(
            reverse('tags_handler'),
            {
                'op': 'new',
                'name': name,
                'comment': comment,
                'definition': definition,
            })
        self.assertEqual(httplib.OK, response.status_code)
        self.assertThat(populate_tags, MockCalledOnceWith(ANY))
        # The tag passed to populate_tags() is the one created above.
        [tag], _ = populate_tags.call_args
        self.assertThat(tag, MatchesStructure.byEquality(
            name=name, comment=comment, definition=definition))