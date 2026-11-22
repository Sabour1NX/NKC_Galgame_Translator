from PIL import Image,ImageDraw
from nkc_galgame_translator.pointer_attention import CursorLens,nearby
from nkc_galgame_translator.live_capture import merge_cloud_rows
from nkc_galgame_translator.vision_core import VisionCore
from nkc_galgame_translator.tracking import ObjectTracker

def test_lens_stays_within_selected_game_and_moves_between_groups():
    lens=CursorLens()
    game=(-100,24,900,600)
    a=lens.region((0,160),game)
    assert a==lens.region((6,168),game)
    b=lens.region((650,480),game)
    assert a!=b and b[0]>=game[0] and b[0]+b[2]<=game[0]+game[2]
    assert not nearby(dict(x=100,y=100,w=60,h=20),(650,480))
    assert lens.region((1000,800),game) is None
    assert lens.region((50,50),[(0,0,20,20),(80,0,20,20)]) is None

def test_cloud_recognition_carries_original_blue_through_merge():
    with Image.new('RGB',(140,60),(204,228,252)) as im:
        d=ImageDraw.Draw(im)
        for x in range(20,100,8):d.rectangle((x,20,x+3,30),fill=(79,28,207))
        item=dict(text='\u65e5\u672c\u8a9e',x=18,y=17,w=90,h=17)
        cloud=VisionCore._cloud_regions(None,im,[item],())[0]
        assert cloud['fg']==[79,28,207]
        local=dict(item,fg=[20,20,20],bg=[204,228,252])
        assert merge_cloud_rows([local],[cloud])[0]['fg']==[79,28,207]

def test_dense_screen_tracks_beyond_previous_32_box_ceiling():
    rows=[dict(x=15+(i%8)*180,y=12+(i//8)*60,w=100,h=22,text=f'Option {i}',source_lang='en') for i in range(80)]
    with ObjectTracker(max_tracks=96) as tracker:
        assert len(tracker.update(rows).tracks)==80
