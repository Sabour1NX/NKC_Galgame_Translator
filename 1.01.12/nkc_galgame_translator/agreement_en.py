# SPDX-License-Identifier: MIT
"""English user terms and the complete license."""
from .agreement import AGREEMENT_VERSION, MIT_LICENSE
from .resource_files import read_resource

AGREEMENT_TITLE_EN = 'User terms and MIT license'
DISCLAIMER_EN = read_resource('agreement.en.txt')

AGREEMENT_TEXT_EN = DISCLAIMER_EN.rstrip() + '\n\n' + MIT_LICENSE


def get_agreement_text_en() -> str:
    """Return the complete English reading without changing consent/version state."""
    return AGREEMENT_TEXT_EN
