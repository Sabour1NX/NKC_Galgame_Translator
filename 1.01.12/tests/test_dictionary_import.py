# SPDX-License-Identifier: MIT
"""Pure import tests: no database, UI, network, or third-party dictionary data."""
import json
from pathlib import Path

import pytest

from nkc_galgame_translator import dictionary_import as module
from nkc_galgame_translator.dictionary_import import DictionaryImportError, parse_dictionary


def document(tmp_path, content, suffix='.csv', encoding='utf-8'):
    path = tmp_path/('dictionary'+suffix)
    path.write_bytes(content if isinstance(content, bytes) else content.encode(encoding))
    return path


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'gb18030'])
def test_csv_encodings_headers_and_quotes(tmp_path, encoding):
    source = 'source,target\r\n"Open, now","\u73b0\u5728\uff0c\u6253\u5f00"\r\n"Say ""Hello""","\u8bf4“\u4f60\u597d”"\r\n'
    path = document(tmp_path, source, encoding=encoding)
    assert parse_dictionary(path, 'en', 'zh-Hans') == [
        {'source':'Open, now','target':'\u73b0\u5728\uff0c\u6253\u5f00'},
        {'source':'Say "Hello"','target':'\u8bf4“\u4f60\u597d”'}]


def test_utf16_big_endian_bom(tmp_path):
    path = document(tmp_path, b'\xfe\xff'+'source\ttarget\nStart\t\u5f00\u59cb'.encode('utf-16-be'), '.tsv')
    assert parse_dictionary(path,'en','zh-CN') == [{'source':'Start','target':'\u5f00\u59cb'}]


def test_gb18030_supplementary_character(tmp_path):
    path = document(tmp_path,'\u539f\u6587,\u8bd1\u6587\nStar,\u661f\U00020bb7',encoding='gb18030')
    assert parse_dictionary(path,'en','zh-Hans')[0]['target']=='\u661f\U00020bb7'


@pytest.mark.parametrize('header', ['source,target', 'word,translation', '\u539f\u6587,\u8bd1\u6587', '\u6e90\u6587\u672c,\u76ee\u6807\u6587\u672c', 'EN,zh-CN'])
def test_common_headers(tmp_path, header):
    assert parse_dictionary(document(tmp_path,header+'\nSave,\u4fdd\u5b58'),'en','zh-Hans') == [{'source':'Save','target':'\u4fdd\u5b58'}]


def test_ecdict_extra_columns_select_translation_not_english_definition(tmp_path):
    data = 'word,phonetic,definition,translation,pos,collins\nkey,ki:,a key,\u94a5\u5319,n,3\n'
    assert parse_dictionary(document(tmp_path,data),'en','zh-Hans') == [{'source':'key','target':'\u94a5\u5319'}]


def test_no_header_and_multiline_text_are_preserved(tmp_path):
    data = '"First\r\nsecond","\u7b2c\u4e00\u884c\r\n\u7b2c\u4e8c\u884c"\r\nHP {n},\u751f\u547d\u503c {n}\r\n'
    assert parse_dictionary(document(tmp_path,data),'en','zh-Hans') == [
        {'source':'First\nsecond','target':'\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c'},
        {'source':'HP {n}','target':'\u751f\u547d\u503c {n}'}]


def test_tsv_and_blank_lines(tmp_path):
    path = document(tmp_path,'\nsource\ttarget\n\nStart\t\u5f00\u59cb\n\t\nExit\t\u9000\u51fa','.tsv')
    assert parse_dictionary(path,'en','zh-Hans') == [{'source':'Start','target':'\u5f00\u59cb'},{'source':'Exit','target':'\u9000\u51fa'}]


@pytest.mark.parametrize('data', ['Start,\u5f00\u59cb\nStart,\u5f00\u59cb', 'source,target\nStart,\u5f00\u59cb\nStart,\u5f00\u59cb'])
def test_exact_duplicates_collapse(tmp_path,data):
    assert len(parse_dictionary(document(tmp_path,data),'en','zh-Hans')) == 1


def test_canonical_equivalent_sources_deduplicate(tmp_path):
    data = [{'source':'Cafe\u0301','target':'\u5496\u5561'},{'source':'Café','target':'\u5496\u5561'}]
    assert parse_dictionary(document(tmp_path,json.dumps(data),'.json'),'en','zh-Hans') == [{'source':'Café','target':'\u5496\u5561'}]


@pytest.mark.parametrize('content,suffix', [
    ('source,target\nStart,\u5f00\u59cb\nStart,\u51fa\u53d1','.csv'),
    ('{"Start":"\u5f00\u59cb","Start":"\u51fa\u53d1"}','.json'),
    ('[{"source":"Start","target":"\u5f00\u59cb"},{"source":"Start","target":"\u51fa\u53d1"}]','.json'),
])
def test_conflicting_translations_fail_atomically(tmp_path,content,suffix):
    with pytest.raises(DictionaryImportError,match='\u51b2\u7a81|\u4e0d\u540c'):
        parse_dictionary(document(tmp_path,content,suffix),'en','zh-Hans')


@pytest.mark.parametrize('content', [
    '{"Start":"\u5f00\u59cb","Exit":"\u9000\u51fa"}',
    '[{"source":"Start","target":"\u5f00\u59cb"},{"source":"Exit","target":"\u9000\u51fa","extra":"ignored"}]',
])
def test_json_mapping_or_records(tmp_path,content):
    assert parse_dictionary(document(tmp_path,content,'.json'),'en','zh-Hans') == [{'source':'Start','target':'\u5f00\u59cb'},{'source':'Exit','target':'\u9000\u51fa'}]


def test_json_identical_duplicate_keys_collapse(tmp_path):
    assert parse_dictionary(document(tmp_path,'{"Start":"\u5f00\u59cb","Start":"\u5f00\u59cb"}','.json'),'en','zh-Hans') == [{'source':'Start','target':'\u5f00\u59cb'}]


@pytest.mark.parametrize('content,suffix', [
    ('source,target\nStart,','.csv'),
    ('source,target\n,\u5f00\u59cb','.csv'),
    ('source,target\nStart,\u5f00\u59cb,extra','.csv'),
    ('source,target\nStart','.csv'),
    ('source,missing\nStart,\u5f00\u59cb','.csv'),
    ('source,source,target\nStart,Begin,\u5f00\u59cb','.csv'),
    ('a,b,c\nx,y,z','.csv'),
    ('source,target\n"Start,\u5f00\u59cb','.csv'),
    ('{"Start":42}','.json'),
    ('{"Start":null}','.json'),
    ('[{"source":"Start"}]','.json'),
    ('[true]','.json'),
    ('42','.json'),
    ('{"Start":NaN}','.json'),
    ('{"Start":Infinity}','.json'),
    ('{"Start":"\u5f00\u59cb",}','.json'),
    ('{}','.json'),
    ('[]','.json'),
    ('source,target\n','.csv'),
    ('source,target\nStart,\u0001\u5f00\u59cb','.csv'),
])
def test_invalid_rows_reject_whole_file(tmp_path,content,suffix):
    with pytest.raises(DictionaryImportError):parse_dictionary(document(tmp_path,content,suffix),'en','zh-Hans')


def tmx(*units):
    return '<?xml version="1.0" encoding="UTF-8"?><tmx version="1.4"><header/><body>'+''.join(units)+'</body></tmx>'


def unit(*values):
    return '<tu>'+''.join(f'<tuv xml:lang="{language}"><seg>{text}</seg></tuv>' for language,text in values)+'</tu>'


def test_tmx_language_selection_inline_text_and_skip_other_pairs(tmp_path):
    data = tmx(unit(('en-US','Open &amp; <hi>close</hi>'),('zh-CN','\u6253\u5f00\u548c\u5173\u95ed'),('ja','\u958b\u9589')),
               unit(('de','Tür'),('fr','porte')),
               unit(('en','HP {n}'),('zh-Hans','\u751f\u547d\u503c {n}')))
    assert parse_dictionary(document(tmp_path,data,'.tmx'),'en','zh-Hans') == [
        {'source':'Open & close','target':'\u6253\u5f00\u548c\u5173\u95ed'}, {'source':'HP {n}','target':'\u751f\u547d\u503c {n}'}]


@pytest.mark.parametrize('tag', ['zh-CN','zh-SG','zh-Hans','zh-Hans-CN'])
def test_tmx_simplified_aliases(tmp_path,tag):
    data=tmx(unit(('ja-JP','\u958b\u59cb'),(tag,'\u5f00\u59cb')))
    assert parse_dictionary(document(tmp_path,data,'.tmx'),'ja','zh-Hans')[0]['target']=='\u5f00\u59cb'


@pytest.mark.parametrize('tag', ['zh-TW','zh-HK','zh-Hant','zh-Hant-TW'])
def test_tmx_traditional_aliases(tmp_path,tag):
    data=tmx(unit(('en','Start'),(tag,'\u958b\u59cb')))
    assert parse_dictionary(document(tmp_path,data,'.tmx'),'en','zh-Hant')[0]['target']=='\u958b\u59cb'


@pytest.mark.parametrize('tag', ['zh','zh-TW','zh-Hant'])
def test_tmx_never_guesses_generic_or_traditional_as_simplified(tmp_path,tag):
    with pytest.raises(DictionaryImportError,match='\u672a\u627e\u5230'):
        parse_dictionary(document(tmp_path,tmx(unit(('en','Start'),(tag,'\u5f00\u59cb'))),'.tmx'),'en','zh-Hans')


def test_tmx_explicit_region_beats_generic_and_rejects_ambiguous_generic(tmp_path):
    data=tmx(unit(('en','fallback'),('en-US','color'),('en-GB','colour'),('zh-CN','\u989c\u8272')))
    path=document(tmp_path,data,'.tmx')
    assert parse_dictionary(path,'en-US','zh-Hans')[0]['source']=='color'
    assert parse_dictionary(path,'en','zh-Hans')[0]['source']=='fallback'
    path=document(tmp_path,tmx(unit(('en-US','color'),('en-GB','colour'),('zh-CN','\u989c\u8272'))),'.tmx')
    with pytest.raises(DictionaryImportError,match='\u51b2\u7a81\u8bed\u8a00\u7248\u672c'):parse_dictionary(path,'en','zh-Hans')


@pytest.mark.parametrize('data', [
    '<tmx>', '<other><body/></other>', '<tmx/>', '<tmx><body/></tmx>',
    '<tmx><body/><body/></tmx>',
    '<tmx><tu/></tmx>',
    tmx('<tu><tuv xml:lang="en"/><tuv xml:lang="zh-CN"><seg>\u5f00\u59cb</seg></tuv></tu>'),
    tmx('<tu><tuv><seg>Start</seg></tuv><tuv xml:lang="zh-CN"><seg>\u5f00\u59cb</seg></tuv></tu>'),
    tmx(unit(('en',''),('zh-CN','\u5f00\u59cb'))),
    '<!DOCTYPE tmx SYSTEM "file:///private.txt">'+tmx(unit(('en','Start'),('zh-CN','\u5f00\u59cb'))),
    '<!DOCTYPE tmx [<!ENTITY x SYSTEM "https://invalid.test/">]>'+tmx(unit(('en','&x;'),('zh-CN','\u5f00\u59cb'))),
])
def test_bad_or_entity_tmx_is_rejected(tmp_path,data):
    with pytest.raises(DictionaryImportError):parse_dictionary(document(tmp_path,data,'.tmx'),'en','zh-Hans')


def test_tmx_namespace_and_utf16(tmp_path):
    data='<tmx xmlns="urn:tmx"><body>'+unit(('en','Start'),('zh-CN','\u5f00\u59cb'))+'</body></tmx>'
    assert parse_dictionary(document(tmp_path,data,'.tmx',encoding='utf-16'),'en','zh-Hans') == [{'source':'Start','target':'\u5f00\u59cb'}]


@pytest.mark.parametrize('suffix,content', [('.csv','source,target\nA,\u4e00\nB,\u4e8c\nC,\u4e09'),
    ('.json','{"A":"\u4e00","B":"\u4e8c","C":"\u4e09"}'),
    ('.tmx',tmx(unit(('en','A'),('zh-CN','\u4e00')),unit(('de','B'),('fr','b')),unit(('en','C'),('zh-CN','\u4e09'))))])
def test_entry_count_limits(tmp_path,monkeypatch,suffix,content):
    monkeypatch.setattr(module,'MAX_ENTRIES',2)
    with pytest.raises(DictionaryImportError,match='\u4e0a\u9650'):parse_dictionary(document(tmp_path,content,suffix),'en','zh-Hans')


def test_byte_and_field_limits(tmp_path,monkeypatch):
    path=document(tmp_path,'source,target\nStart,\u5f00\u59cb')
    monkeypatch.setattr(module,'MAX_FILE_BYTES',4)
    with pytest.raises(DictionaryImportError,match='20 MiB'):parse_dictionary(path,'en','zh-Hans')
    monkeypatch.setattr(module,'MAX_FILE_BYTES',1024)
    monkeypatch.setattr(module,'MAX_FIELD_CHARS',4)
    with pytest.raises(DictionaryImportError,match='4096'):parse_dictionary(path,'en','zh-Hans')


@pytest.mark.parametrize('content', [b'', b'\xff', 'source,target\nStart,\u5f00\u59cb'.encode('utf-16-le'),
    'source,target\nStart,\u5f00\u59cb'.encode('utf-32')])
def test_invalid_or_unsupported_encoding(tmp_path,content):
    with pytest.raises(DictionaryImportError):parse_dictionary(document(tmp_path,content),'en','zh-Hans')


@pytest.mark.parametrize('src,dst', [('', 'zh-Hans'),('en',''),('en','en-US-???'),('zh-CN','zh-Hans'),(None,'ja')])
def test_invalid_or_equivalent_languages(tmp_path,src,dst):
    with pytest.raises(DictionaryImportError):parse_dictionary(document(tmp_path,'A,\u4e00'),src,dst)


def test_unknown_extension_and_missing_path_do_not_echo_path_or_contents(tmp_path):
    private_name=tmp_path/'private-credential-sentinel.csv'
    with pytest.raises(DictionaryImportError) as error:parse_dictionary(private_name,'en','zh-Hans')
    assert 'private-credential-sentinel' not in str(error.value)
    with pytest.raises(DictionaryImportError,match='\u652f\u6301'):parse_dictionary(tmp_path/'x.exe','en','zh-Hans')
    with pytest.raises(DictionaryImportError) as error:
        parse_dictionary(document(tmp_path,'{"Start":"private-credential-sentinel",INVALID}','.json'),'en','zh-Hans')
    assert 'private-credential-sentinel' not in str(error.value)


def test_only_read_operation_and_file_unchanged(tmp_path):
    path=document(tmp_path,'source,target\nStart,\u5f00\u59cb')
    before=path.read_bytes()
    result=parse_dictionary(path,'en','zh-Hans')
    assert result and path.read_bytes()==before
    assert list(tmp_path.iterdir())==[path]


def test_deep_tmx_rejected_without_recursion_error(tmp_path):
    data='<tmx><body>'+('<nested>'*65)+('</nested>'*65)+'</body></tmx>'
    with pytest.raises(DictionaryImportError,match='\u7ed3\u6784\u8fc7\u6df1'):parse_dictionary(document(tmp_path,data,'.tmx'),'en','zh-Hans')


@pytest.mark.parametrize('content', ['{"Start":"\\ud800"}', '{"\\udfff":"\u5f00\u59cb"}'])
def test_json_unpaired_surrogates_rejected_before_database_commit(tmp_path,content):
    with pytest.raises(DictionaryImportError,match='Unicode'):
        parse_dictionary(document(tmp_path,content,'.json'),'en','zh-Hans')
