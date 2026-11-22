# SPDX-License-Identifier: MIT
"""Local UI translations only. Game text, keys and HTTP payloads never enter here."""
from __future__ import annotations
import ctypes
import json
from functools import lru_cache
import re
import sys
from types import MappingProxyType

from .resource_files import read_resource

SUPPORTED = ('zh-CN', 'en', 'ja')
_names = json.loads(read_resource('language_names.json'))
NATIVE_NAMES = _names['interface']
LANGUAGE_NAMES = {name: tuple(labels) for name, labels in _names['translation'].items()}


def detect_system_language(langid=None):
    """Use the Windows user's UI language, not region, keyboard or network data."""
    if langid is None:
        if sys.platform != 'win32': return 'en'
        try:
            api = ctypes.WinDLL('kernel32', use_last_error=True).GetUserDefaultUILanguage
            api.argtypes = []; api.restype = ctypes.c_ushort
            langid = api()
        except (OSError, AttributeError): return 'en'
    if type(langid) is not int: return 'en'
    return {0x04: 'zh-CN', 0x09: 'en', 0x11: 'ja'}.get(langid & 0x3ff, 'en')


def initial_language(config, *, interactive=True):
    saved = config.get('app_language')
    if not interactive:return saved if saved in SUPPORTED else 'zh-CN'
    if saved in SUPPORTED and (config.get('app_language_selected') is True or not interactive):
        return saved
    return detect_system_language()


@lru_cache(maxsize=1)
def catalog():
    from .ui_catalog import CATALOG
    return MappingProxyType(CATALOG)


@lru_cache(maxsize=1)
def _source_labels():
    labels = {}
    ambiguous = set()
    for source, (english, _) in catalog().items():
        if english in labels:
            ambiguous.add(english)
        labels[english] = source
    for english in ambiguous:
        del labels[english]
    return labels


def ui_source(english: str) -> str:
    """Find the original label used by the locale matcher."""
    return _source_labels()[english]


@lru_cache(maxsize=2048)
def _template(value):
    parts = []; cursor = 0; names = []
    for match in re.finditer(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', value):
        parts.append(re.escape(value[cursor:match.start()]))
        name = match.group(1)
        if name in names: parts.append('(?P='+name+')')
        else: parts.append('(?P<'+name+'>.*?)');names.append(name)
        cursor = match.end()
    parts.append(re.escape(value[cursor:]))
    return re.compile(''.join(parts), re.DOTALL), names


def _render(template, values):
    return re.sub(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', lambda m: values.get(m.group(1), m.group(0)), template)


# These fields contain application-owned UI pieces, not user/game data. Every
# other template field is opaque and is copied verbatim, even if it resembles UI.
_UI_TEMPLATE_FIELDS = MappingProxyType({
    '\u5f53\u524d\u69fd\u4f4d {index} · {status}': ('status',),
    '\u69fd\u4f4d {index}\n{status}': ('status',),
    '\u69fd\u4f4d {index} \u5df2\u542f\u7528 · {mode}': ('mode',),
    '\u6b63\u5728\u7f16\u8f91\uff1a\u69fd\u4f4d {index}{suffix}': ('suffix',),
    '{label}\u987b\u4e3a {minimum} \u81f3 {maximum} \u7684\u6574\u6570\u3002': ('label',),
    '{label}\u987b\u4e3a\u5f00\u6216\u5173\u3002': ('label',),
    '\u5df2\u8fbe\u5230\u672c\u6b21\u542f\u52a8\u7684 {limit} \u6b21 API \u8bf7\u6c42\u9650\u989d\uff1b{hint}': ('hint',),
})


@lru_cache(maxsize=1)
def _translation_tables():
    """Compile immutable lookup tables once; no dynamic values are cached."""
    exact = {}; templates = []; replacements = ({}, {}, {})
    for original, translated in catalog().items():
        row = (original, *translated)
        for source in row:
            exact.setdefault(source, row)
        if '{' in original:
            for source in row:
                pattern, names = _template(source)
                if names:
                    templates.append((pattern, row, _UI_TEMPLATE_FIELDS.get(original, ())))
            continue
        for index, target in enumerate(row):
            for source in row:
                if source != target and len(source) >= 2:
                    replacements[index].setdefault(source, target)
    fragments = []
    for replacement in replacements:
        pattern = re.compile('|'.join(re.escape(k) for k in sorted(replacement, key=len, reverse=True)))
        fragments.append((pattern, MappingProxyType(replacement)))
    return MappingProxyType(exact), tuple(templates), tuple(fragments)


def _translate_fragment(value, index, exact, fragments):
    row = exact.get(value)
    if row is not None:
        return row[index]
    pattern, replacements = fragments[index]
    return pattern.sub(lambda m: replacements[m.group(0)], value)


def translate(value, language='zh-CN'):
    """Translate controlled UI strings; templates interpolate data, never evaluate it."""
    if not isinstance(value, str) or not value: return value
    language = language if language in SUPPORTED else 'zh-CN'
    index = {'zh-CN': 0, 'en': 1, 'ja': 2}[language]
    exact, templates, fragments = _translation_tables()
    row = exact.get(value)
    if row is not None: return row[index]
    # Full templates cover status lines with counts without splitting grammar.
    for pattern, row, ui_fields in templates:
        match = pattern.fullmatch(value)
        if match:
            fields = match.groupdict()
            for name in ui_fields:
                fields[name] = _translate_fragment(fields[name], index, exact, fragments)
            return _render(row[index], fields)
    # Controlled compound status text can contain several already-localized parts.
    return _translate_fragment(value, index, exact, fragments)


class LanguageLabels(dict):
    """Stable language codes with localized display aliases; iteration stays canonical."""
    def __getitem__(self, label):
        if dict.__contains__(self, label): return dict.__getitem__(self, label)
        for original, aliases in LANGUAGE_NAMES.items():
            if label in aliases: return dict.__getitem__(self, original)
        raise KeyError(label)

    def get(self, label, default=None):
        try: return self[label]
        except KeyError: return default


def localize_widgets(root, language):
    """Refresh UI chrome in place. Never touch entries, Text contents or table cells."""
    from tkinter import ttk, TclError
    pending = [root]
    while pending:
        widget = pending.pop()
        try:
            pending.extend(widget.winfo_children())
            if 'text' in widget.keys():
                value = widget.cget('text')
                if isinstance(value, str) and value:
                    widget.configure(text=translate(value, language))
            if isinstance(widget, ttk.Notebook):
                for tab in widget.tabs():widget.tab(tab, text=translate(widget.tab(tab,'text'), language))
            if isinstance(widget, ttk.Treeview):
                for column in ('#0', *widget.cget('columns')):
                    text = widget.heading(column, 'text')
                    if text:widget.heading(column, text=translate(text, language))
            if widget.winfo_toplevel() is widget:
                widget.title(translate(widget.title(), language))
        except TclError:
            continue


def agreement_text(language):
    if language == 'en':
        from .agreement_en import AGREEMENT_TEXT_EN
        return AGREEMENT_TEXT_EN
    if language == 'ja':
        from .agreement_ja import AGREEMENT_TEXT_JA
        return AGREEMENT_TEXT_JA
    from .agreement import AGREEMENT_TEXT
    return AGREEMENT_TEXT
