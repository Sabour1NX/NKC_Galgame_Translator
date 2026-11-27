import pytest

from nkc_galgame_translator.presentation import OverlayState


def obj(identity=1, revision=1, x=10, text='Start'):
    return {'track_id': identity, 'revision': revision,
            'line': {'text': text, 'x': x, 'y': 20, 'w': 100, 'h': 30,
                     'bg': [17,17,17], 'fg': [255,255,255]}}


def result(revision=1, text='\u5f00\u59cb', final=False, x=999):
    return {'text': text, '_revision': revision, 'final': final, 'x': x}


def test_scroll_dropout_follows_neighbor_expires_on_idle_and_clears_on_cut(monkeypatch):
    clock=[1.]
    monkeypatch.setattr('nkc_galgame_translator.presentation.monotonic',lambda:clock[0])
    for cut in (False,True):
        state=OverlayState(hold_until_next=True)
        first,second=obj(1),obj(2)
        second['line']['y']=70
        state.apply_objects([first,second])
        state.apply_translation(1,result(final=True))
        state.apply_translation(2,result(final=True))
        moving={**first,'line':{**first['line'],'y':16,'_content_motion':(0,-4)}}
        state.apply_objects([moving])
        assert state.rendered[2]['y']==66
        clock[0]+=.05
        state.apply_objects([moving])
        assert state.rendered[2]['y']==66
        if cut:
            state.clear()
            assert not state.rendered and not state.apply_late(2,result(final=True))
        else:
            clock[0]+=.11
            assert state.expire_held() and set(state.rendered)=={1}


def test_static_dropout_holds_until_local_replacement_or_deadline(monkeypatch):
    clock = [5.]
    monkeypatch.setattr('nkc_galgame_translator.presentation.monotonic', lambda: clock[0])
    state = OverlayState(hold_until_next=True, hold_seconds=.75)
    first, second = obj(1), obj(2, x=300)
    state.apply_objects([first, second])
    state.apply_translation(1, result(final=True))
    state.apply_translation(2, result(text='\u8bbe\u7f6e', final=True))

    state.apply_objects([])
    clock[0] += .4
    newcomer = obj(3, text='Continue')
    state.apply_objects([newcomer])
    assert not state.apply_translation(3, result(text=''))
    assert state.apply_translation(3, result(text='\u7ee7\u7eed'))
    assert set(state.rendered) == {2, 3}
    assert state.rendered[2]['_hold_deadline'] == 5.75
    clock[0] = 5.75
    assert state.expire_held() and set(state.rendered) == {3}


def test_zero_hold_and_scene_clear_remove_previous_result():
    for hold in (0, 10):
        state = OverlayState(hold_until_next=True, hold_seconds=hold)
        state.apply_objects([obj()])
        state.apply_translation(1, result(final=True))
        state.apply_objects([])
        if hold:
            assert state.rendered[1]['text'] == '\u5f00\u59cb'
        else:
            assert not state.rendered
        state.clear()
        assert not state.display_regions()
        assert not state.apply_late(1, result(final=True))


def test_stream_uses_latest_position_and_completion_fills_region():
    state=OverlayState()
    state.apply_objects([obj()])
    assert state.apply_translation(1,result())
    state.apply_objects([obj(x=60)])
    assert state.rendered[1]['x']==60
    assert state.rendered[1]['text']=='\u5f00\u59cb'
    assert state.apply_translation(1,result(final=True))
    assert state.rendered[1]['x']==60
    assert state.rendered[1]['final']


def test_one_revised_object_preserves_other_translation():
    state=OverlayState()
    state.apply_objects([obj(1),obj(2,x=200)])
    state.apply_translation(1,result(final=True))
    state.apply_translation(2,result(text='\u8bbe\u7f6e',final=True))
    state.apply_objects([obj(1,revision=2,text='Continue'),obj(2,x=210)])
    assert 1 not in state.rendered
    assert state.rendered[2]['text']=='\u8bbe\u7f6e'
    assert state.rendered[2]['x']==210
    assert not state.apply_translation(1,result(revision=1,text='\u65e7\u7ed3\u679c',final=True))
    assert state.apply_translation(1,result(revision=2,text='\u7ee7\u7eed',final=True))


def test_lost_object_rejects_queued_result_and_keeps_other():
    state=OverlayState()
    state.apply_objects([obj(1),obj(2)])
    state.apply_translation(2,result(final=True))
    state.apply_objects([obj(2)])
    assert not state.apply_translation(1,result(final=True))
    assert 2 in state.rendered


def test_late_error_or_partial_cannot_erase_new_or_complete_result():
    state=OverlayState()
    state.apply_objects([obj(revision=2)])
    state.apply_translation(1,result(revision=2,final=True))
    assert not state.remove_error(1,1)
    assert not state.apply_translation(1,result(revision=2,text='\u5f00',final=False))
    assert state.rendered[1]['text']=='\u5f00\u59cb'
    assert state.remove_error(1,2)


def test_clear_and_snapshot_do_not_alias_input():
    state=OverlayState(); source=obj()
    state.apply_objects([source]);source['line']['x']=1234
    assert state.objects[1]['line']['x']==10
    state.clear()
    assert state.objects=={} and state.rendered=={}


def sized_obj(width=100, height=30, font_size=24, **kwargs):
    item = obj(**kwargs)
    item['line'].update(w=width,h=height,font_size=font_size)
    return item


def test_alternating_one_and_two_pixel_ocr_noise_does_not_resize_or_redraw():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    for delta in (1,-1,2,-2,1,2,-1):
        assert not state.apply_objects([sized_obj(100+delta,30+delta,24+delta)])
        shown = state.rendered[1]
        assert (shown['w'],shown['h'],shown['font_size']) == (100,30,24)
        assert shown['text'] == '\u5f00\u59cb'


def test_cumulative_resize_uses_accepted_anchor_and_requires_three_confirmations():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    for delta in (1,2):
        state.apply_objects([sized_obj(100+delta,30+delta,24+delta)])
    for _ in range(2):
        assert not state.apply_objects([sized_obj(103,33,27)])
        assert (state.rendered[1]['w'],state.rendered[1]['h'],state.rendered[1]['font_size']) == (100,30,24)
    assert state.apply_objects([sized_obj(103,33,27)])
    assert (state.rendered[1]['w'],state.rendered[1]['h'],state.rendered[1]['font_size']) == (103,33,27)
    assert not state.apply_objects([sized_obj(104,34,28)])
    for _ in range(2):
        assert not state.apply_objects([sized_obj(106,36,30)])
    assert state.apply_objects([sized_obj(106,36,30)])
    assert (state.rendered[1]['w'],state.rendered[1]['h'],state.rendered[1]['font_size']) == (106,36,30)


def test_tiny_position_noise_is_filtered_but_color_and_large_moves_update():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    moved = sized_obj(101,31,25,x=11)
    moved['line'].update(y=21,bg=[33,44,55])
    assert state.apply_objects([moved])
    shown = state.rendered[1]
    assert (shown['x'],shown['y'],shown['bg']) == (10,20,[33,44,55])
    assert (shown['w'],shown['h'],shown['font_size']) == (100,30,24)
    moved['line'].update(x=411,y=321)
    state.apply_objects([moved])
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (411,321)


def test_content_revision_resets_dimension_anchor_immediately():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    revised = sized_obj(101,31,25,revision=2,text='Continue',x=11)
    revised['line']['y'] = 21
    state.apply_objects([revised])
    assert 1 not in state.rendered
    state.apply_translation(1,result(revision=2,text='\u7ee7\u7eed',final=True))
    assert (state.rendered[1]['w'],state.rendered[1]['h'],state.rendered[1]['font_size']) == (101,31,25)
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (11,21)
    assert not state.apply_translation(1,result(revision=1,final=True))


def test_dimensions_remain_stable_during_stream_and_short_missing_retains_anchor():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(text='\u5f00'))
    shifted = sized_obj(102,32,26,x=12)
    shifted['line']['y'] = 22
    state.apply_objects([shifted])
    state.apply_translation(1,result(text='\u5f00\u59cb',final=True))
    assert (state.rendered[1]['w'],state.rendered[1]['h']) == (100,30)
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (10,20)
    state.apply_objects([])
    assert not state.rendered  # Retained history is never itself displayed.
    assert not state.apply_translation(1,result(final=True))
    state.apply_objects([shifted])
    state.apply_translation(1,result(final=True))
    assert (state.rendered[1]['w'],state.rendered[1]['h']) == (100,30)
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (10,20)


def test_zero_and_negative_screen_coordinates_hold_alternating_pixel_noise():
    state = OverlayState()
    initial = sized_obj(x=0)
    initial['line']['y'] = -20
    state.apply_objects([initial])
    state.apply_translation(1,result(final=True))
    for delta in (1,-1,2,-2,1,-2):
        observed = sized_obj(x=delta)
        observed['line']['y'] = -20+delta
        assert not state.apply_objects([observed])
        assert (state.rendered[1]['x'],state.rendered[1]['y']) == (0,-20)
        # Only presentation copies are stabilized; incoming tracking stays raw.
        assert (observed['line']['x'],observed['line']['y']) == (delta,-20+delta)


def test_position_drift_requires_three_observations_beyond_accepted_anchor():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    for delta in (1,2):
        moving = sized_obj(x=10+delta)
        moving['line']['y'] = 20-delta
        assert not state.apply_objects([moving])
    moving = sized_obj(x=13)
    moving['line']['y'] = 17
    for _ in range(2):
        assert not state.apply_objects([moving])
        assert (state.rendered[1]['x'],state.rendered[1]['y']) == (10,20)
    assert state.apply_objects([moving])
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (13,17)
    moving['line'].update(x=15,y=15)
    assert not state.apply_objects([moving])
    moving['line'].update(x=16,y=14)
    for _ in range(2):
        assert not state.apply_objects([moving])
    assert state.apply_objects([moving])
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (16,14)


def test_clear_drops_position_anchor_for_next_session():
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    state.clear()
    shifted = sized_obj(x=12)
    shifted['line']['y'] = 22
    state.apply_objects([shifted])
    state.apply_translation(1,result(final=True))
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (12,22)


def game_box(box):
    """Replay geometry from .04/reports/live-overlay-before-position-fix.json."""
    x,y,width,height = box
    observed = sized_obj(width,height,30,x=x,text='\u9375\u3092 5 \u3064\u96c6\u3081\u3066\u30b4\u30fc\u30eb\u3078\u5411\u304b\u3046')
    observed['line']['y'] = y
    return observed


def test_recorded_game_height_spikes_do_not_resize_or_move_translation():
    state = OverlayState()
    state.apply_objects([game_box((622,368,541,40))])
    state.apply_translation(1,result(final=True))
    # The recorded 39px fluctuation and isolated 71/73px OCR boxes must not
    # alter the accepted dialogue rectangle or force a new text layout.
    for box in ((622,369,541,39),(622,364,541,71),(622,368,541,40),
                (622,364,541,73),(622,369,541,39)):
        assert not state.apply_objects([game_box(box)])
        shown = state.rendered[1]
        assert tuple(shown[k] for k in ('x','y','w','h')) == (622,368,541,40)
        assert shown['text'] == '\u5f00\u59cb' and shown['final']


def test_three_consistent_real_resizes_eventually_follow_latest_size():
    state = OverlayState()
    state.apply_objects([game_box((622,368,541,40))])
    state.apply_translation(1,result(final=True))
    for height in (71,73):
        assert not state.apply_objects([game_box((622,364,541,height))])
        assert state.rendered[1]['h'] == 40
    assert state.apply_objects([game_box((622,364,541,72))])
    shown = state.rendered[1]
    assert tuple(shown[k] for k in ('x','y','w','h')) == (622,364,541,72)


@pytest.mark.parametrize('delta', [3,4,6,-3,-6])
def test_small_position_change_requires_three_consistent_observations(delta):
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    observed = sized_obj(x=10+delta)
    observed['line']['y'] = 20-delta
    for _ in range(2):
        assert not state.apply_objects([observed])
        assert (state.rendered[1]['x'],state.rendered[1]['y']) == (10,20)
    assert state.apply_objects([observed])
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (10+delta,20-delta)


@pytest.mark.parametrize('delta', [7,-7,120,-120])
def test_large_position_change_without_size_spike_follows_immediately(delta):
    state = OverlayState()
    state.apply_objects([sized_obj()])
    state.apply_translation(1,result(final=True))
    observed = sized_obj(x=10+delta)
    observed['line']['y'] = 20-delta
    assert state.apply_objects([observed])
    assert (state.rendered[1]['x'],state.rendered[1]['y']) == (10+delta,20-delta)


@pytest.mark.parametrize('origin', [(4,-5),(-500,300),(1200,-900)])
def test_capture_origin_movement_follows_immediately_even_with_size_spike(origin):
    state = OverlayState()
    initial = game_box((622,368,541,40))
    initial['line']['_capture_origin'] = (0,0)
    state.apply_objects([initial]);state.apply_translation(1,result(final=True))
    moved = game_box((622+origin[0],368+origin[1],541,71))
    moved['line']['_capture_origin'] = origin
    assert state.apply_objects([moved])
    shown = state.rendered[1]
    assert (shown['x'],shown['y'],shown['h']) == (622+origin[0],368+origin[1],40)
    assert shown['_capture_origin'] == origin


def test_unconfirmed_size_spike_still_updates_colors():
    state = OverlayState()
    state.apply_objects([game_box((622,368,541,40))])
    state.apply_translation(1,result(final=True))
    observed = game_box((622,364,541,73))
    observed['line'].update(bg=[30,40,50],fg=[210,220,230])
    assert state.apply_objects([observed])
    shown = state.rendered[1]
    assert (shown['y'],shown['h']) == (368,40)
    assert (shown['bg'],shown['fg']) == ([30,40,50],[210,220,230])


@pytest.mark.parametrize('reset', ['missing','revision','clear'])
def test_candidate_history_does_not_survive_missing_revision_or_clear(reset):
    state = OverlayState()
    state.apply_objects([sized_obj()]);state.apply_translation(1,result(final=True))
    for _ in range(2):
        assert not state.apply_objects([sized_obj(130,60,30,x=14)])
    revision = 1
    if reset == 'missing':
        state.apply_objects([])
    elif reset == 'clear':
        state.clear()
    else:
        revision = 2
    state.apply_objects([sized_obj(revision=revision)])
    state.apply_translation(1,result(revision=revision,final=True))
    observed = sized_obj(130,60,30,x=14,revision=revision)
    for _ in range(2):
        assert not state.apply_objects([observed])
        shown = state.rendered[1]
        assert (shown['x'],shown['w'],shown['h'],shown['font_size']) == (10,100,30,24)
    assert state.apply_objects([observed])
    assert (state.rendered[1]['x'],state.rendered[1]['h']) == (14,60)


def test_inconsistent_candidate_resets_confirmation_count():
    state = OverlayState()
    state.apply_objects([sized_obj()]);state.apply_translation(1,result(final=True))
    for width in (150,150,170,150,150):
        assert not state.apply_objects([sized_obj(width=width)])
        assert state.rendered[1]['w'] == 100
    assert state.apply_objects([sized_obj(width=150)])
    assert state.rendered[1]['w'] == 150


def test_geometry_history_is_bounded_to_64_recent_ids_and_eviction_reanchors():
    state = OverlayState()
    for identity in range(1,65):
        state.apply_objects([sized_obj(identity=identity)])
        assert len(state._history) <= 64
    state.apply_objects([])
    # Touch ID 1 again: ID 2, rather than ID 1, is now least recently seen.
    state.apply_objects([sized_obj(identity=1,width=102)])
    assert state.objects[1]['line']['w'] == 100
    state.apply_objects([sized_obj(identity=65)])
    assert len(state._history) == 64
    assert 1 in state._history and 2 not in state._history
    state.apply_objects([])
    state.apply_objects([sized_obj(identity=1,width=102)])
    state.apply_translation(1,result(final=True))
    assert state.rendered[1]['w'] == 100
    state.apply_objects([])
    state.apply_objects([sized_obj(identity=2,width=102)])
    state.apply_translation(2,result(final=True))
    assert state.rendered[2]['w'] == 102
    assert len(state._history) == 64


@pytest.mark.parametrize('reset', ['clear','revision'])
def test_reappearing_object_after_clear_or_new_revision_uses_new_geometry(reset):
    state = OverlayState()
    state.apply_objects([sized_obj()]);state.apply_translation(1,result(final=True))
    state.apply_objects([])
    assert not state.rendered
    revision = 1
    if reset == 'clear':
        state.clear()
        assert not state._history
    else:
        revision = 2
    observed = sized_obj(102,32,26,x=12,revision=revision)
    observed['line']['y'] = 22
    state.apply_objects([observed])
    state.apply_translation(1,result(revision=revision,final=True))
    shown = state.rendered[1]
    assert tuple(shown[k] for k in ('x','y','w','h','font_size')) == (12,22,102,32,26)


def test_preserve_source_immediately_removes_translation_even_at_same_revision():
    state=OverlayState();first=obj();state.apply_objects([first]);state.apply_translation(1,result(final=True))
    rejected=obj(text='Neu or Id gane?');rejected['line']['_preserve_source']=True
    assert state.apply_objects([rejected]) and not state.rendered
    assert not state.apply_translation(1,result())
    assert not state.apply_translation(1,result(final=True))
    recovered=obj(revision=2);state.apply_objects([recovered])
    assert state.apply_translation(1,result(revision=2,final=True))


def test_geometry_debounce_cannot_extend_neighbor_into_rejected_pixels():
    state=OverlayState();initial=sized_obj(height=60)
    state.apply_objects([initial]);state.apply_translation(1,result(final=True))
    current=sized_obj(height=30)
    rejected=obj(identity=2,text='Neu or Id gane?');rejected['line'].update(y=55,_preserve_source=True)
    state.apply_objects([current,rejected])
    assert state.rendered[1]['h']==30 and state.rendered[1]['y']+state.rendered[1]['h']<55
    # A source rectangle that itself overlaps remains suppressed.
    current['line']['h']=50
    state.apply_objects([current,rejected])
    assert not state.rendered and not state.apply_translation(1,result(final=True))


@pytest.mark.parametrize('delta', [-2, -1, 1, 2])
def test_consistent_subpixel_sized_drift_eventually_covers_observed_bounds(delta):
    state=OverlayState();state.apply_objects([sized_obj()]);state.apply_translation(1,result(final=True))
    moved=sized_obj(width=100+delta,height=30+delta,x=10+delta)
    moved['line']['y']=20+delta
    for _ in range(2):
        assert not state.apply_objects([moved])
    assert state.apply_objects([moved])
    assert tuple(state.rendered[1][key] for key in ('x','y','w','h')) == (10+delta,20+delta,100+delta,30+delta)
    assert state.rendered[1]['font_size']==24


def test_large_displacement_with_size_spike_never_builds_a_hybrid_rectangle():
    state=OverlayState();state.apply_objects([sized_obj()]);state.apply_translation(1,result(final=True))
    noise=sized_obj(width=180,height=60,x=60)
    noise['line']['y']=70
    for observed in (noise,sized_obj(),noise,sized_obj()):
        assert not state.apply_objects([observed])
        assert tuple(state.rendered[1][key] for key in ('x','y','w','h'))==(10,20,100,30)
    for _ in range(2):
        assert not state.apply_objects([noise])
    assert state.apply_objects([noise])
    assert tuple(state.rendered[1][key] for key in ('x','y','w','h'))==(60,70,180,60)


def test_different_shape_candidates_cannot_confirm_individual_edges():
    state=OverlayState();state.apply_objects([sized_obj()]);state.apply_translation(1,result(final=True))
    # An x coordinate recurring across incompatible widths is not evidence for
    # a new rectangle. Previous independent filters moved x after three reads.
    for width in (170,230,170,230,170,230):
        assert not state.apply_objects([sized_obj(width=width,x=14)])
        assert tuple(state.rendered[1][key] for key in ('x','w'))==(10,100)


def test_stabilized_rectangle_cannot_intrude_on_a_new_readable_neighbor():
    state=OverlayState();state.apply_objects([sized_obj(width=180)]);state.apply_translation(1,result(final=True))
    narrower=sized_obj(width=100)
    neighbor=sized_obj(identity=2,x=130,text='Exit')
    state.apply_objects([narrower,neighbor])
    assert state.rendered[1]['w']==100
    assert state.rendered[1]['x']+state.rendered[1]['w']<neighbor['line']['x']


def unchanged_result(revision=1, final=True):
    return {'_revision':revision,'final':final,'text':'','_translation_unchanged':True}


def test_unchanged_final_keeps_original_pixels_without_empty_cover_or_late_partial():
    state=OverlayState();state.apply_objects([obj()])
    assert not state.apply_translation(1,unchanged_result())
    assert not state.rendered
    assert not state.apply_translation(1,result(text='\u8fdf\u5230\u7247\u6bb5'))
    assert not state.rendered
    assert state._unchanged=={1:1}


def test_unchanged_final_removes_streamed_cover_and_survives_geometry_updates():
    state=OverlayState();state.apply_objects([obj()]);state.apply_translation(1,result(text='Start'))
    assert state.apply_translation(1,unchanged_result())
    assert not state.rendered
    state.apply_objects([obj(x=90)])
    assert not state.apply_translation(1,result(text='\u8fdf\u5230\u7247\u6bb5'))
    assert not state.rendered


def test_partial_or_stale_unchanged_marker_cannot_erase_current_translation():
    state=OverlayState();state.apply_objects([obj(revision=2)]);state.apply_translation(1,result(revision=2))
    assert not state.apply_translation(1,unchanged_result(revision=1))
    assert not state.apply_translation(1,unchanged_result(revision=2,final=False))
    assert state.rendered[1]['text']=='\u5f00\u59cb'
    assert not state._unchanged


@pytest.mark.parametrize('reset',['missing','revision','clear','preserved'])
def test_unchanged_completion_is_bounded_to_current_object_revision(reset):
    state=OverlayState();state.apply_objects([obj()]);state.apply_translation(1,unchanged_result())
    if reset=='missing':state.apply_objects([])
    elif reset=='revision':state.apply_objects([obj(revision=2)])
    elif reset=='clear':state.clear()
    else:
        rejected=obj();rejected['line']['_preserve_source']=True
        state.apply_objects([rejected])
    assert not state._unchanged
    assert not state.rendered


def test_final_corrected_output_can_replace_unchanged_final_but_partial_cannot():
    state=OverlayState();state.apply_objects([obj()]);state.apply_translation(1,unchanged_result())
    assert state.apply_translation(1,result(final=True))
    assert state.rendered[1]['text']=='\u5f00\u59cb'
    assert not state._unchanged
    assert not state.apply_translation(1,result(text='\u8fdf\u5230\u7247\u6bb5'))

def test_confirmed_japanese_keeps_source_mask_when_model_echoes_input():
    state = OverlayState()
    item = obj(text='\u3067\u306a\u3044\u3068')
    item['line']['_cover_source'] = True
    state.apply_objects([item])
    state.apply_translation(1, unchanged_result())
    assert [r['text'] for r in state.display_regions()] == ['']
    state.apply_translation(1, result(text='\u5426\u5219', final=True))
    assert [r['text'] for r in state.display_regions()] == ['\u5426\u5219']
