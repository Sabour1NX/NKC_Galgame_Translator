from pathlib import Path
import time
import pytest
from PIL import Image, ImageDraw, ImageFont
from nkc_galgame_translator.font_style import SourceStyleMatcher, TargetFontSelector
from nkc_galgame_translator.native import NativeCore


def test_target_font_requires_target_script_and_actual_translation():
    calls=[]
    def supports(face,text):
        calls.append((face,text));return face=='SimSun' and '\u4e2d' in text and '\u8bd1' in text
    selector=TargetFontSelector(supports,'zh-Hans')
    assert selector.choose('serif','Welcome / \u6b22\u8fce')==('SimSun',False)
    count=len(calls)
    assert selector.choose('serif','Welcome / \u6b22\u8fce')==('SimSun',False) and len(calls)==count
    assert selector.choose('pixel','\U0001f680') is None
    assert TargetFontSelector(lambda *a:False,'ja').choose('sans','\u3053\u3093\u306b\u3061\u306f') is None


@pytest.mark.parametrize('filename,style',[('arial.ttf','sans'),('times.ttf','serif'),('consola.ttf','mono')])
def test_style_matches_rendered_source_evidence(filename,style):
    path=Path('C:/Windows/Fonts')/filename
    if not path.exists():pytest.skip('font unavailable')
    text='Welcome aboard the ship'
    font=ImageFont.truetype(str(path),36);box=font.getbbox(text)
    with Image.new('RGB',(box[2]+20,70),'black') as image:
        ImageDraw.Draw(image).text((10,10-box[1]),text,font=font,fill='white')
        line=dict(text=text,x=10,y=10,w=box[2],h=box[3]-box[1],fg=[255]*3,bg=[0]*3)
        matcher=SourceStyleMatcher()
        assert matcher.classify(image,line)==style
        assert matcher.classify(image,line)==style and len(matcher.cache)==1


def test_native_glyph_coverage_and_independent_fonts():
    with NativeCore() as core:
        assert core.font_supports('Arial','Welcome')
        assert not core.font_supports('Definitely Missing Font','Welcome')
        assert not core.font_supports('Arial','\u4e2d\u6587')
        assert core.font_supports('SimSun','\u4e2d\u6587\u8bd1\u6587')
        core.set_auto_font_style(True,'zh-Hans')
        core.show_overlay([dict(x=20,y=30,w=300,h=60,text='\u6b22\u8fce\u56de\u6765',_source_font_style='serif',_track_id=1),
                           dict(x=20,y=100,w=300,h=60,text='\u5f00\u59cb\u6e38\u620f',_source_font_style='sans',_track_id=2)])
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            snap=core.overlay_snapshot()
            if len(snap.get('regions',[]))==2:break
            time.sleep(.02)
        regions=snap.get('regions',[])
        assert len(regions)==2
        assert regions[0]['font_face']!=regions[1]['font_face']
