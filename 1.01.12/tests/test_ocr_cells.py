# SPDX-License-Identifier: MIT
"""Physical column boundaries and source-ink geometry; no live capture/API."""
import importlib.util
from pathlib import Path
from copy import deepcopy

from PIL import Image
import pytest

from nkc_galgame_translator.ocr import OcrCore, PortableOcr, _row_background, place_image_result, validate_response

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('independent_cell_helper',ROOT/'tools/ocr_helper.py')
HELPER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


def word(text,x,y=30,w=50,h=20):
    return dict(text=text,x=x,y=y,w=w,h=h)


def test_wide_gap_splits_actual_word_bounds_without_expanding_or_mutating():
    source=dict(text='Forged parts 188',x=10,y=30,w=480,h=20,confidence=92)
    words=[word('Forged',10,w=70),word('parts',92,w=60),word('188',450,w=40)]
    before=deepcopy((source,words))
    cells=HELPER.split_word_cells(source,words,'eng')
    assert [(item['text'],item['x'],item['w']) for item in cells]==[
        ('Forged parts',10,142),('188',450,40)]
    assert all(item['separated_cell'] is True for item in cells)
    assert (source,words)==before


def test_normal_word_spaces_and_names_keep_original_physical_row():
    source=dict(text='PRINCESS BLUE remains in orbit.',x=10,y=30,w=400,h=24,confidence=93)
    words=[word('PRINCESS',10,w=120,h=24),word('BLUE',148,w=60,h=24),
           word('remains',226,w=90,h=24),word('in',334,w=18,h=24),word('orbit.',370,w=40,h=24)]
    assert HELPER.split_word_cells(source,words,'eng')==[source]


def test_three_columns_and_short_japanese_cell_text_keep_their_own_bounds():
    source=dict(text='\u8ca8 \u7269 10 \u91d1',x=5,y=20,w=500,h=20,confidence=94)
    words=[word('\u8ca8',5,y=20,w=20),word('\u7269',28,y=20,w=20),
           word('10',220,y=20,w=30),word('\u91d1',480,y=20,w=20)]
    cells=HELPER.split_word_cells(source,words,'jpn')
    assert [(item['text'],item['x'],item['w']) for item in cells]==[('\u8ca8\u7269',5,43),('10',220,30),('\u91d1',480,20)]


@pytest.mark.parametrize('gap,split',[(59,False),(60,True)])
def test_column_gap_uses_source_height_not_character_count(gap,split):
    source=dict(text='wide label price',x=5,y=30,w=1000,h=20,confidence=90)
    words=[word('a very long label with arbitrary text length',5,w=50),word('X',55+gap,w=20)]
    assert (len(HELPER.split_word_cells(source,words,'eng'))==2) is split


@pytest.mark.parametrize('flag',['true',1,None,[],{}])
def test_ipc_rejects_nonboolean_cell_metadata(flag):
    line=dict(text='Cargo',x=2,y=3,w=30,h=20,confidence=90,separated_cell=flag)
    with pytest.raises(RuntimeError,match='cell boundary'):
        validate_response({'lines':[line],'ocr_ms':1},100,100)


def test_source_ink_is_offset_once_with_window_origin():
    original={'lines':[dict(text='Cargo',x=8,y=18,w=34,h=24,_source_ink=[10,20,30,20],_layout_cell=True)]}
    before=deepcopy(original)
    moved=place_image_result(original,-500,200)['lines'][0]
    assert (moved['x'],moved['y'])==(-492,218)
    assert moved['_source_ink']==[-490,220,30,20]
    assert moved['_layout_cell'] is True
    assert original==before


def test_background_does_not_leak_from_selected_row_above():
    image=Image.new('RGB',(200,100),'black')
    image.paste('white',(0,0,200,29))
    # Source row starts at 32. Previous top-only sampling saw the white row at28.
    assert _row_background(image,(20,32,140,20),(18,30,163,55))==[0,0,0]
    image.paste('white',(0,32,200,56))
    assert _row_background(image,(20,32,140,20),(18,30,163,55))==[255,255,255]


def test_background_at_image_edge_uses_bounded_row_fallback():
    image=Image.new('RGB',(20,20),(16,32,48))
    assert _row_background(image,(0,0,20,20),(0,0,20,20))==[16,32,48]


def test_private_cargo_cells_never_cover_the_price_gap():
    fixture=ROOT/'reports/ocr-private/cargo.png'
    if not fixture.exists() or not PortableOcr(ROOT).available():
        pytest.skip('private provided image or optional OCR model absent')
    with Image.open(fixture) as image,OcrCore(mode='pixel') as core:
        result=core.recognize_image(image,'en')
    lines=result['lines']
    assert any(item['text']=='Cargo' and item['x']+item['w']<200 for item in lines)
    assert any(item['text']=='Cost' and item['x']>440 for item in lines)
    assert all(item['x']+item['w']<400 or item['x']>440 for item in lines)
    assert all('_source_ink' in item for item in lines)
    label=next(item for item in lines if item['text']=='antibiotics')
    assert label['_layout_cell'] is True and label['bg']==[0,0,0]
