# SPDX-License-Identifier: MIT
"""Real helper integration under ASCII, space and shell-metacharacter paths."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from PIL import Image,ImageDraw,ImageFont
from nkc_galgame_translator.ocr import validate_response

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'tools/ocr_helper.py'
FONT=Path('C:/Windows/Fonts/msgothic.ttc')


@pytest.fixture
def special_path_workspace(tmp_path):
    source=ROOT/'models/tessdata'
    if not FONT.is_file() or not all((source/(lang+'.traineddata')).is_file() for lang in ('eng','jpn')):
        pytest.skip('Local OCR models and fixture font required')
    base=tmp_path/'release-check & spaces %'
    models=base/'language-models';inputs=base/'input-frames'
    models.mkdir(parents=True);inputs.mkdir()
    for language in ('eng','jpn'):
        shutil.copy2(source/(language+'.traineddata'),models)
    image=Image.new('RGB',(960,250),'white')
    draw=ImageDraw.Draw(image);font=ImageFont.truetype(str(FONT),38)
    draw.text((32,30),'\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002',font=font,fill='black')
    draw.text((32,110),'\u30b2\u30fc\u30e0\u3092\u958b\u59cb\u3059\u308b',font=font,fill='black')
    image.save(inputs/'frame.bmp')
    return base,models,inputs


@pytest.mark.parametrize('relative_cli',[False,True])
def test_helper_reads_japanese_with_ascii_model_and_frame_paths(special_path_workspace,relative_cli):
    base,models,inputs=special_path_workspace
    originals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in models.iterdir()}
    path_arg=lambda path:str(path.relative_to(base) if relative_cli else path)
    command=[sys.executable,'-I','-u',str(HELPER),'--packages',str(ROOT/'vendor/ocr'),
             '--tessdata',path_arg(models),'--input-root',path_arg(inputs)]
    frame=path_arg(inputs/'frame.bmp')
    request={'image_path':frame,'language':'jpn+eng'}
    stdin='\n'.join(json.dumps(value,ensure_ascii=False) for value in (request,request,{'quit':True}))+'\n'
    result=subprocess.run(command,cwd=base,input=stdin,capture_output=True,encoding='utf-8',
        errors='replace',timeout=30,creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ,'OMP_THREAD_LIMIT':'2','PYTHONIOENCODING':'utf-8'})
    assert result.returncode==0,result.stderr
    values=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(values)==2,result.stdout
    for value in values:
        validate_response(value,960,250)
        text=''.join(row['text'] for row in value['lines'])
        assert '\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d' in text and '\u30b2\u30fc\u30e0\u3092\u958b\u59cb\u3059\u308b' in text
    assert [r['text'] for r in values[0]['lines']]==[r['text'] for r in values[1]['lines']]
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in models.iterdir()}==originals


def test_missing_working_directory_is_sanitized(tmp_path):
    result=subprocess.run([sys.executable,'-I',str(HELPER),'--tessdata',str(tmp_path/'private-sentinel'),
        '--input-root',str(tmp_path)],capture_output=True,encoding='utf-8',errors='replace',timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==2
    assert json.loads(result.stdout)=={'error':'OCR working directories are unavailable'}
    assert 'private-sentinel' not in result.stdout+result.stderr
