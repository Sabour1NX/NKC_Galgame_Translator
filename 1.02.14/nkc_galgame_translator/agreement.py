# SPDX-License-Identifier: MIT
"""User terms and the license displayed in the application."""

from .i18n import ui_source

from .resource_files import read_resource

AGREEMENT_VERSION = "2026-11-21-r5"
AGREEMENT_TITLE = ui_source('User terms and MIT license')
MIT_LICENSE = read_resource('license.mit.txt')
AGREEMENT_TEXT = read_resource('agreement.zh-CN.txt').rstrip() + '\n\n' + MIT_LICENSE
