# !usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2017-12-05 12:01:21
# @Last modified by:   Brian Cherinka
# @Last Modified time: 2017-12-05 12:19:32

from __future__ import print_function, division, absolute_import


class ValisError(Exception):
    """A custom core Valis exception"""

    def __init__(self, message=None):

        message = 'There has been an error' \
            if not message else message

        super(ValisError, self).__init__(message)


class ValisNotImplemented(ValisError):
    """A custom exception for not yet implemented features."""

    def __init__(self, message=None):

        message = 'This feature is not implemented yet.' \
            if not message else message

        super(ValisNotImplemented, self).__init__(message)


class ValisAPIError(ValisError):
    """A custom exception for API errors"""

    def __init__(self, message=None):
        if not message:
            message = 'Error with Http Response from Valis API'
        else:
            message = 'Http response error from Valis API. {0}'.format(message)

        super(ValisAPIError, self).__init__(message)


class ValisApiAuthError(ValisAPIError):
    """A custom exception for API authentication errors"""
    pass


class ValisMissingDependency(ValisError):
    """A custom exception for missing dependencies."""
    pass


class ValisWarning(Warning):
    """Base warning for Valis."""


class ValisUserWarning(UserWarning, ValisWarning):
    """The primary warning class."""
    pass


class ValisSkippedTestWarning(ValisUserWarning):
    """A warning for when a test is skipped."""
    pass


class ValisDeprecationWarning(ValisUserWarning):
    """A warning for deprecated features."""
    pass
