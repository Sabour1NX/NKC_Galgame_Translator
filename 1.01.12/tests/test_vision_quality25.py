"""Uncertain local anchors must be verified before any display output."""
import json
from PIL import Image
from nkc_galgame_translator.vision import parse_transcription
from nkc_galgame_translator.vision_core import _local_anchors,VisionCore
from nkc_galgame_translator.translation import TranslationError
from test_vision import factory,reply

def line(text='uncertain',**extra):
    return dict(text=text,x=2,y=3,w=100,h=16,bg=[0,0,0],fg=[255,255,255],**extra)

def test_omitted_uncertain_anchor_never_leaks_local_guess():
    original=[line(_vision_only=True),line('known',_vision_only=False)]
    result=parse_transcription(json.dumps({'lines':[{'id':1,'text':'Known'}]}),original)
    assert len(result)==1 and result[0]['text']=='Known'
    assert original[0]['_vision_only'] is True

def test_confirmed_candidate_keeps_geometry_and_drops_draw_prohibition():
    source=line(_vision_only=True)
    result=parse_transcription('{"lines":[{"id":0,"text":"Visible source"}]}',[source])[0]
    assert result['_vision_verified'] and '_vision_only' not in result
    assert all(result[k]==source[k] for k in ('x','y','w','h','bg','fg'))

def test_whole_measured_line_supersedes_contained_ocr_fragment_only():
    candidate=line('uncertain line',_vision_only=True)
    fragment={**line('fragment'),'x':15,'w':24}
    result,barriers=_local_anchors({'lines':[fragment],'vision_anchors':[candidate]},'en')
    assert result['lines']==[candidate] and not barriers
    fragment['x']=0
    result,_=_local_anchors({'lines':[fragment],'vision_anchors':[candidate]},'en')
    assert result['lines']==[fragment]

def test_candidate_does_not_cross_selected_regions():
    result,_=_local_anchors({'lines':[line('known',_selection_id=0)],
        'vision_anchors':[line(_vision_only=True,_selection_id=1)]},'en')
    assert len(result['lines'])==1 and result['lines'][0]['text']=='known'

def test_small_anchor_has_bounded_original_pixel_enlargement(factory):
    sent=[]
    def handler(request):sent.append(json.loads(request.content));return reply()
    _,recognizer=factory(handler)
    recognizer.recognize(Image.new('RGB',(128,64)),[line()])
    parts=sent[0]['messages'][1]['content']
    assert len(parts)==4 and 'anchor id 0' in parts[2]['text']
    assert parts[3]['image_url']['url'].startswith('data:image/png;base64,')

def test_failed_ai_removes_uncertain_candidate_from_fallback():
    class Bad:
        def recognize(self,*args,**kwargs):raise TranslationError('unavailable')
    instance=object.__new__(VisionCore);instance.recognizer=Bad()
    import threading
    _,_,result=instance._recognize(1,'key',Image.new('RGB',(128,64)),
        {'lines':[line(_vision_only=True),line('Known source')]},'en',threading.Event())
    assert [r['text'] for r in result['lines']]==['Known source']
    assert result['engine']=='local-fallback'
