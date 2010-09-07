"""
XMP-RPC API
"""

import xmlrpclib

from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.db.models import Q

from launch_control.dashboard_app import __version__ as dashboard_version
from launch_control.dashboard_app.dispatcher import xml_rpc_signature

from launch_control.dashboard_app.models import (
        Bundle,
        BundleStream,
        )


class errors:
    """
    A namespace for error codes that may be returned by various XML-RPC
    methods. Where applicable existing status codes from HTTP protocol
    are reused
    """
    AUTH_FAILED = 100
    AUTH_BLOCKED = 101
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501


class DashboardAPI(object):
    """
    Dashboard API object.

    All public methods are automatically exposed as XML-RPC methods
    """

    @xml_rpc_signature('str')
    def version(self):
        """
        Return dashboard server version.
        """
        return ".".join(map(str, dashboard_version))

    def put(self, content, content_filename, pathname):
        """
        Upload a bundle to the server.

        The pathname MUST designate a pre-existing bundle stream or a
        Fault(404, "...") will be raised. The content SHOULD be a valid
        JSON document matching the "Dashboard Bundle Format 1.0" schema.
        The content_filename is arbitrary and will be stored along with
        the content for reference.

        The SHA1 of the content MUST be unique or a Fault(409, "...")
        will be raised. This is used to protect from simple duplicate
        submissions.

        The user MUST have access to the bundle stream or a Fault(403,
        "...") will be raised. The following access rules are defined
        for bundle streams:
            - all anonymous streams are accessible
            - personal streams are accessible by owners
            - team streams are accessible by team members

        If all goes well this function returns the SHA1 of the content.
        """
        user = None
        try:
            bundle_stream = BundleStream.objects.get(pathname=pathname)
        except BundleStream.DoesNotExist:
            raise xmlrpclib.Fault(errors.NOT_FOUND,
                    "Bundle stream not found")
        if not bundle_stream.can_upload(user):
            raise xmlrpclib.Fault(errors.FORBIDDEN,
                    "Uploading to specified stream is not permitted")
        try:
            bundle = Bundle.objects.create(
                    bundle_stream=bundle_stream,
                    uploaded_by=user,
                    content_filename=content_filename)
            bundle.save()
            bundle.content.save("bundle-{0}".format(bundle.pk),
                    ContentFile(content))
            bundle.save()
        except IntegrityError:
            bundle.delete()
            raise xmlrpclib.Fault(errors.CONFLICT,
                    "Duplicate bundle detected")
        return bundle.content_sha1

    def get(self, content_sha1):
        user = None
        try:
            bundle = Bundle.objects.get(content_sha1=content_sha1)
        except Bundle.DoesNotExist:
            raise xmlrpclib.Fault(errors.NOT_FOUND,
                    "Bundle not found")
        if not bundle.bundle_stream.can_download(user):
            raise xmlrpclib.Fault(errors.FORBIDDEN,
                    "Downloading from specified stream is not permitted")
        else:
            return {"content": bundle.content.read(),
                    "content_filename": bundle.content_filename}

    def streams(self):
        user = None
        if user is not None:
            bundle_streams = BundleStream.objects.filter(
                    Q(user = user) | Q(group in user.groups))
        else:
            bundle_streams = BundleStream.objects.filter(
                    user = None, group = None)
        return [{
            'pathname': bundle_stream.pathname,
            'name': bundle_stream.name,
            'user': bundle_stream.user.username if bundle_stream.user else "",
            'group': bundle_stream.group.name if bundle_stream.group else "",
            'bundle_count': bundle_stream.bundles.count(),
            } for bundle_stream in bundle_streams]

    def bundles(self, pathname):
        user = None
        bundles = Bundle.objects.filter(
                bundle_stream__pathname = pathname)
        return [{
            'uploaded_by': bundle.uploaded_by.username if bundle.uploaded_by else "",
            'uploaded_on': bundle.uploaded_on,
            'content_filename': bundle.content_filename,
            'content_sha1': bundle.content_sha1,
            'is_deserialized': bundle.is_deserialized
            } for bundle in bundles]
