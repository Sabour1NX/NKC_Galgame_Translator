# SPDX-License-Identifier: MIT
"""Conservative English/Japanese box routing and display-only source labels.

This is script detection within an English/Japanese OCR session, not a general
language classifier. Han-only names and ambiguous text keep the selected source.
No label is sent to the API or included in a translation-memory cache value.
"""

from .i18n import ui_source, translate
import unicodedata
from statistics import median


_LABELS = {'en': ui_source('English'), 'ja': ui_source('Japanese'), 'zh': '\u4e2d\u6587', 'zh-hans': ui_source('Simplified Chinese'),
           'zh-hant': ui_source('Traditional Chinese'), 'ko': ui_source('Korean'), 'fr': ui_source('French'), 'de': ui_source('German'),
           'es': ui_source('Spanish')}


def language_group(language: str) -> str:
    """Group region/script variants for visibility counting only, not API/cache keys."""
    return str(language or '').strip().lower().replace('_', '-').split('-')[0]


def foreign_language_groups(sources, target: str) -> frozenset[str]:
    """Count distinct currently visible foreign source languages, excluding target."""
    target_group = language_group(target)
    return frozenset(group for source in sources
                     if (group := language_group(source)) and group != target_group)


def coherent_language_groups(lines, target):
    """Display-only languages for adjacent rows of one coherent text block.

    A remote menu/button is not evidence that a paragraph is multilingual.
    Conservative geometry/style grouping never changes OCR or API routing.
    """
    lines=list(lines);parents=list(range(len(lines)))
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    def height(row):
        physical=row.get('_source_rows',())
        values=[r.get('h',0) for r in physical if r.get('h',0)>0]
        return max(1.,median(values) if values else row.get('font_size') or row['h'])
    for i,a in enumerate(lines):
        if a.get('_preserve_source'):continue
        for j in range(i):
            b=lines[j]
            if b.get('_preserve_source') or a.get('_selection_id',0)!=b.get('_selection_id',0):continue
            ah,bh=height(a),height(b);scale=max(ah,bh)
            if min(ah,bh)/scale<.80:continue
            if any(max(abs(x-y) for x,y in zip(a.get(color,(0,0,0)),b.get(color,(0,0,0))))>48
                   for color in ('bg','fg')):continue
            vertical_gap=max(a['y'],b['y'])-min(a['y']+a['h'],b['y']+b['h'])
            horizontal_gap=max(a['x'],b['x'])-min(a['x']+a['w'],b['x']+b['w'])
            aligned=abs(a['x']-b['x'])<=max(8.,scale*.6)
            same_row=abs(a['y']-b['y'])<=scale*.3 and horizontal_gap<=scale
            neighboring=aligned and -.25*scale<=vertical_gap<=.9*scale
            if same_row or neighboring:parents[find(i)]=find(j)
    groups={}
    for i,row in enumerate(lines):
        if not row.get('_preserve_source'):groups.setdefault(find(i),[]).append(row.get('source_lang',''))
    return [foreign_language_groups(groups.get(find(i),()),target) for i in range(len(lines))]


def source_label(source: str) -> str:
    key = str(source).lower().replace('_', '-')
    return _LABELS.get(key, _LABELS.get(key.split('-')[0], str(source)))


def detect_source_language(text: str, selected: str) -> str:
    """Route visibly English/Japanese boxes; preserve all other selections.

    Kana is Japanese evidence. Latin-only words within ja/en sessions use en.
    Pure Han, other scripts, and ambiguous non-Latin text keep the user's source.
    The selected OCR engine must still support the visible script: this function
    does not make the English Windows OCR engine recognize Japanese glyphs.
    """
    if str(selected).lower().split('-')[0] not in {'en', 'ja'}:
        return selected
    normalized = unicodedata.normalize('NFKC', str(text))
    letters = [c for c in normalized if c.isalpha()]
    if any('\u3041' <= c <= '\u3096' or '\u30a1' <= c <= '\u30fa'
           or '\u31f0' <= c <= '\u31ff' for c in letters):
        return 'ja'
    if letters and all('a' <= c <= 'z' or 'A' <= c <= 'Z' for c in letters):
        return 'en'
    return selected


def label_translation(text: str, source: str, final: bool = True, *,
                      show_source_label: bool = True, show_translation_brackets: bool = True,
                      label_language: str = 'zh-CN') -> str:
    """Add a stable streaming prefix; close its bracket only on completion.

    Empty partial output remains empty, so it does not conceal source pixels.
    Hard newlines are kept and native rendering lays out the entire labeled text.
    """
    if type(show_source_label) is not bool or type(show_translation_brackets) is not bool:
        raise ValueError('Display switches must be boolean')
    if not text:
        return ''
    prefix = ''
    if show_source_label:
        separator = ': ' if label_language == 'en' else '\uff1a'
        prefix = translate(source_label(source), label_language) + separator
    content = prefix + text
    if show_translation_brackets:
        content = '[' + content + (']' if final else '')
    return content
