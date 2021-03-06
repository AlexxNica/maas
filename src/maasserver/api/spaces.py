# Copyright 2015-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""API handlers: `Space`."""

from django.db.models.query import QuerySet
from maasserver.api.support import (
    admin_method,
    OperationsHandler,
)
from maasserver.enum import NODE_PERMISSION
from maasserver.exceptions import (
    MAASAPIBadRequest,
    MAASAPIValidationError,
)
from maasserver.forms.space import SpaceForm
from maasserver.models import (
    Space,
    Subnet,
    VLAN,
)
from piston3.utils import rc


DISPLAYED_SPACE_FIELDS = (
    'resource_uri',
    'id',
    'name',
    'vlans',
    'subnets',
)


def _has_undefined_space():
    """Returns True if the undefined space contains at least one VLAN."""
    return VLAN.objects.filter(space__isnull=True).exists()


# Placeholder Space-like object for backward compatibility.
UNDEFINED_SPACE = Space(
    id=-1, name=Space.UNDEFINED,
    description="Backward compatibility object to ensure objects not "
                "associated with a space can be found.")

UNDEFINED_SPACE.save = None


class SpacesQuerySet(QuerySet):

    def __iter__(self):
        """Custom iterator which also includes a dummy "undefined" space."""
        yield from super().__iter__()
        # This space will be related to any VLANs and subnets not associated
        # with a space. (For backward compatibility with Juju 2.0.)
        if _has_undefined_space():
            yield UNDEFINED_SPACE


class SpacesHandler(OperationsHandler):
    """Manage spaces."""
    api_doc_section_name = "Spaces"
    update = delete = None
    fields = DISPLAYED_SPACE_FIELDS

    @classmethod
    def resource_uri(cls, *args, **kwargs):
        # See the comment in NodeHandler.resource_uri.
        return ('spaces_handler', [])

    def read(self, request):
        """List all spaces."""
        spaces_query = Space.objects.all()
        # The .all() method will return a QuerySet, but we need to coerce it to
        # a SpacesQuerySet to get our custom iterator. This must be an instance
        # of a QuerySet, or the API framework will return it as-is.
        spaces_query.__class__ = SpacesQuerySet
        return spaces_query

    @admin_method
    def create(self, request):
        """Create a space.

        :param name: Name of the space.
        :param description: Description of the space.
        """
        form = SpaceForm(data=request.data)
        if form.is_valid():
            return form.save()
        else:
            raise MAASAPIValidationError(form.errors)


class SpaceHandler(OperationsHandler):
    """Manage space."""
    api_doc_section_name = "Space"
    create = None
    model = Space
    fields = DISPLAYED_SPACE_FIELDS

    @classmethod
    def resource_uri(cls, space=None):
        # See the comment in NodeHandler.resource_uri.
        space_id = "id"
        if space is not None:
            if space.id == -1:
                space_id = Space.UNDEFINED
            else:
                space_id = space.id
        return ('space_handler', (space_id,))

    @classmethod
    def name(cls, space):
        """Return the name of the space."""
        if space is None:
            return None
        return space.get_name()

    @classmethod
    def subnets(cls, space):
        # Backward compatibility for Juju 2.0.
        if space.id == -1:
                return Subnet.objects.filter(vlan__space__isnull=True)
        return Subnet.objects.filter(vlan__space=space)

    @classmethod
    def vlans(cls, space):
        # Backward compatibility for Juju 2.0.
        if space.id == -1:
            return VLAN.objects.filter(space__isnull=True)
        return space.vlan_set.all()

    def read(self, request, id):
        """Read space.

        Returns 404 if the space is not found.
        """
        # Backward compatibility for Juju 2.0. This is a special case to check
        # if the user requested to read the undefined space.
        if id == "-1" or id == Space.UNDEFINED and _has_undefined_space():
            return UNDEFINED_SPACE
        return Space.objects.get_space_or_404(
            id, request.user, NODE_PERMISSION.VIEW)

    def update(self, request, id):
        """Update space.

        :param name: Name of the space.
        :param description: Description of the space.

        Returns 404 if the space is not found.
        """
        if id == "-1" or id == Space.UNDEFINED:
            raise MAASAPIBadRequest(
                "Space cannot be modified: %s" % Space.UNDEFINED)
        space = Space.objects.get_space_or_404(
            id, request.user, NODE_PERMISSION.ADMIN)
        form = SpaceForm(instance=space, data=request.data)
        if form.is_valid():
            return form.save()
        else:
            raise MAASAPIValidationError(form.errors)

    def delete(self, request, id):
        """Delete space.

        Returns 404 if the space is not found.
        """
        if id == "-1" or id == Space.UNDEFINED:
            raise MAASAPIBadRequest(
                "Space cannot be deleted: %s" % Space.UNDEFINED)
        space = Space.objects.get_space_or_404(
            id, request.user, NODE_PERMISSION.ADMIN)
        space.delete()
        return rc.DELETED
