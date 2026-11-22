import pytest
from PIL import Image
from nkc_galgame_translator.selection_regions import capture_plan, client_selections, mask_regions, scope_lines
from nkc_galgame_translator.pipeline import _quality_lines
from nkc_galgame_translator.vision_core import _local_anchors
from nkc_galgame_translator.tracking import ObjectTracker


def test_two_regions_keep_screen_origin_and_mask_every_gap():
    plan=capture_plan([(-100,80,60,40),(20,100,80,40)])
    assert plan.bounds==(-100,80,200,60)
    assert plan.regions==((0,0,60,40),(120,20,80,40))
    with Image.new('RGB',(200,60),'red') as source, mask_regions(source,plan.regions) as masked:
        for y in range(60):
            for x in range(200):
                selected=(x<60 and y<40) or (x>=120 and y>=20)
                assert masked.getpixel((x,y))==((255,0,0) if selected else (0,0,0))
        assert source.getpixel((80,10))==(255,0,0)


@pytest.mark.parametrize('bad',[[],[(0,0,30,30)]*2,[(0,0,20,20),(4090,0,20,20)],[(0,0,0,4)],[(0,0,True,2)],[(i*30,0,20,20) for i in range(9)]])
def test_invalid_selection_sets_rejected(bad):
    with pytest.raises(ValueError):capture_plan(bad)


def test_client_clips_resized_game_without_capturing_outside():
    assert client_selections([(-5,10,30,40),(80,0,40,10)],(400,200,100,30))==((400,210,25,20),(480,200,20,10))
    assert client_selections([(200,0,20,20)],(400,200,100,30)) is None


def test_no_recognition_or_grouping_across_region_boundaries():
    lines=[dict(text='Welcome back',x=0,y=0,w=100,h=20),dict(text='Start game',x=110,y=0,w=100,h=20),dict(text='Hidden',x=90,y=0,w=40,h=20)]
    scoped=scope_lines(lines,((0,0,100,20),(110,0,100,20)))
    assert len(scoped)==2
    assert len(_quality_lines(scoped,'en',(0,0),True))==2
    local,_=_local_anchors({'lines':scoped},'en')
    assert len(local['lines'])==2
    with ObjectTracker() as tracker:
        one=tracker.update([{**scoped[0],'_selection_id':0}]).tracks[0]
        two=tracker.update([{**scoped[0],'_selection_id':1}]).tracks[0]
        assert one.track_id!=two.track_id
