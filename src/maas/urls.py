# Copyright 2012-2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""URL configuration for the maas project."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from django.conf import settings
from django.conf.urls import (
    include,
    patterns,
    url,
)
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


urlpatterns = patterns(
    '',
    url(r'^', include('maasserver.urls')),
    url(r'^metadata/', include('metadataserver.urls')),
)

if settings.STATIC_LOCAL_SERVE:
    urlpatterns += patterns(
        '',
        (r'^media/(?P<path>.*)$', 'django.views.static.serve',
         {'document_root': settings.MEDIA_ROOT}),
    )

    urlpatterns += staticfiles_urlpatterns(settings.STATIC_URL_PATTERN)

if settings.DEBUG:
    # Enable an admin site at root "admin", where all model objects can be
    # viewed and edited.
    from django.contrib import admin
    # Auto-discovery of the admin site will be enabled by default as of
    # Django 1.7.  For older versions, automatic discovery is manual:
    admin.autodiscover()

    urlpatterns += patterns(
        '',
        (r'^admin/', include(admin.site.urls)),
    )