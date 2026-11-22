# SPDX-License-Identifier: MIT
"""Conservative signals of a result that was cut off or is obviously malformed."""
import re


def translation_issue(source, translated, language):
    value=translated.strip()
    original=source.strip()
    if len(value)<8 or len(original)<8:
        return None
    if language.lower().split('-')[0]=='zh':
        # A copied Japanese connective followed by Chinese prose is an
        # unfinished localization. Quoted Japanese titles may legitimately remain.
        clause=re.match('^([^\u300c\u300e\u201c"\u3001\uff0c\u3002\uff01\uff1f\\n]{0,40}(?:\u3060\u3063\u305f\u308a|\u3057\u305f\u308a|\u306a\u306e\u306b|\u3060\u3051\u3069|\u3067\u3059\u304b\u3089))[\u3001\uff0c]',value)
        if clause and clause[1] in original and re.search('[\u4e00-\u9fff]{2}',value[clause.end():]):
            return 'untranslated_clause'
    # Empty/unfinished streams are checked by the request parser. Here only
    # compare visible boundaries; fragments in the source may be deliberate.
    closed=original.endswith(('.', '!', '?', '\u3002', '\uff01', '\uff1f', '\u300d', '”'))
    if not closed:
        return None
    group=language.lower().split('-')[0]
    if group=='zh' and re.search('(\u56e0\u4e3a|\u4ee5\u53ca|\u5982\u679c|\u7531\u4e8e|\u4e3a\u4e86|\u4e0d\u4f46|\u9664\u975e|\u5c3d\u7ba1)$',value) and len(value)>=12:
        return 'dangling_clause'
    if group=='en':
        if re.search(r'[ \t](?:because|although|unless|and|or|either)$',value,re.I):
            return 'dangling_clause'
        if re.match(r'^(?:(?:I|We|You|They) is|I are|(?:He|She|It) are)[ \t]+',value,re.I):
            return 'agreement'
    if not original.endswith(('...', '…')) and value.endswith(('...', '…')):
        return 'unexpected_truncation'
    return None
