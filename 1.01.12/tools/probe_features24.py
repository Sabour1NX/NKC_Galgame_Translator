# SPDX-License-Identifier: MIT
"""Actual game-image OCR with two selected regions; no API or game writes."""
from pathlib import Path
import json,sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from nkc_galgame_translator.ocr import OcrCore
from nkc_galgame_translator.font_style import TargetFontSelector
from nkc_galgame_translator.pipeline import _quality_lines
from nkc_galgame_translator.selection_regions import capture_plan

with Image.open(ROOT/'reports/ocr-private/spacerogue-game.png') as image,OcrCore(mode='pixel',refine_workers=4) as core:
    regions=((0,70,450,370),(0,550,image.width,image.height-550))
    core.set_capture_regions(regions);core.set_auto_font_style(True,'zh-Hans')
    with core.prepare_capture_image(image) as masked:
        assert masked.getpixel((600,100))==(0,0,0)
        assert masked.getpixel((30,100))==image.convert('RGB').getpixel((30,100))
    result=core.recognize_image(image,'en')
    assert len(result['lines'])==15
    assert {line['_selection_id'] for line in result['lines']}=={0,1}
    grouped=_quality_lines(result['lines'],'en',(0,0),True)
    assert len(grouped)==2 and {line['_selection_id'] for line in grouped}=={0,1}
    assert all(line['_source_font_style']=='pixel' for line in result['lines'])
    choices={}
    for target,text in [('zh-Hans','\u6b22\u8fce\u6765\u5230\u98de\u8239'),('en','Welcome aboard'),('ja','\u5b87\u5b99\u3078\u3088\u3046\u3053\u305d')]:
        choice=TargetFontSelector(core.native.font_supports,target).choose('pixel',text)
        assert choice and core.native.font_supports(choice[0],text)
        choices[target]=dict(font=choice[0],pixel=choice[1],text=text)
    evidence=dict(version='0.01.24',passed=True,source='SpaceRogue Classic original screenshot replay',
                  selections=regions,actual_lines=len(result['lines']),isolated_paragraphs=len(grouped),
                  gap_pixels_masked=True,source_styles=sorted({l['_source_font_style'] for l in result['lines']}),
                  supported_target_examples=choices,network_requests=0)
    (ROOT/'reports/feature24-probe.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))
