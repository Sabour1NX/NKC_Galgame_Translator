# SPDX-License-Identifier: MIT
from copy import deepcopy
from nkc_galgame_translator.layout import merge_dialogue_lines


def row(text,x=10,y=10,w=280,h=24,**extra):
    return dict(text=text,x=x,y=y,w=w,h=h,bg=[0,0,0],fg=[255,255,255],source_lang='en',**extra)


def columns():
    lines=[]
    for i in range(3):
        lines.extend([row(f'The left narrative continues here {i}',y=10+i*30,_layout_cell=True),
                      row(f'The right narrative continues here {i}',x=400,y=10+i*30,_layout_cell=True)])
    return lines


def test_two_interleaved_narrative_columns_form_two_contexts_with_exact_source_rows():
    source=columns();before=deepcopy(source)
    result=merge_dialogue_lines(source)
    assert len(result)==2
    for item,side,x in zip(result,['left','right'],[10,400]):
        assert item['text']=='\n'.join(f'The {side} narrative continues here {i}' for i in range(3))
        assert item['x']==x and item['w']==280
        assert [(r['x'],r['y'],r['w'],r['h']) for r in item['_source_rows']]==[(0,i*30,280,24) for i in range(3)]
    assert source==before


def test_unrelated_picture_text_does_not_split_a_left_paragraph():
    source=[row(f'The ongoing narrative continues here {i}',y=10+i*30) for i in range(4)]
    source.append(row('picture noise',x=430,y=45,w=140))
    result=merge_dialogue_lines(source)
    paragraph=next(item for item in result if item['x']==10)
    assert len(paragraph['_source_rows'])==4 and paragraph['w']==280
    assert len(result)==2 and all('picture' not in line['text'] for line in result if line['x']==10)


def test_overlapping_barrier_cannot_be_crossed_to_complete_column_chain():
    source=columns()
    source.append(row('status 99',x=220,y=35,w=100,h=8,_preserve_source=True))
    result=merge_dialogue_lines(source)
    for item in result:
        if item['x']==10:assert len(item.get('_source_rows',[]))<3


def test_short_sentence_end_followed_by_new_full_width_sentence_starts_new_paragraph():
    source=[row('The first paragraph is almost'),row('complete.',y=40,w=90),
            row('Another paragraph begins here.',y=70)]
    result=merge_dialogue_lines(source)
    assert [item['text'] for item in result]==['The first paragraph is almost\ncomplete.','Another paragraph begins here.']


def test_captured_origins_cannot_share_context_even_with_identical_screen_bounds():
    source=[row('This belongs to the old capture',_capture_origin=(0,0)),
            row('This belongs to a new capture',y=40,_capture_origin=(0,1))]
    assert merge_dialogue_lines(source)==source


def test_provider_column_flags_do_not_allow_two_table_cells_to_merge():
    source=[row('A separate long table item',y=10,_layout_cell=True,_column_evidence='local_narrative_column',_column_id=7),
            row('Another separate long item',y=40,_layout_cell=True,_column_evidence='local_narrative_column',_column_id=7)]
    result=merge_dialogue_lines(source)
    assert len(result)==2 and all('_source_rows' not in item for item in result)
