# SPDX-License-Identifier: MIT
"""Japanese user terms and the complete license."""
from .agreement import AGREEMENT_VERSION, MIT_LICENSE
from .resource_files import read_resource

DISCLAIMER_JA = read_resource('agreement.ja.txt')
AGREEMENT_TEXT_JA = DISCLAIMER_JA.rstrip() + '\n\n' + MIT_LICENSE
