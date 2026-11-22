# SPDX-License-Identifier: MIT
"""Load source strings with their English and Japanese labels."""

import json

from .resource_files import read_resource

CATALOG = {source: tuple(labels) for source, labels in
           json.loads(read_resource('ui_catalog.json')).items()}
