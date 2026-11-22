# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from unittest.mock import Mock

from nkc_galgame_translator.app import App, UIValidationError, messagebox
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.translation import RetryableTranslationError
from nkc_galgame_translator.translation_quality import translation_issue
from nkc_galgame_translator.tuning import default_sampling_mode, fast_capture_interval_ms, validate_tuning
from nkc_galgame_translator.window_profiles import matching_window
from test_pipeline import finals, line, make_pipeline, start, wait_until


def test_late_result_finishes_and_is_reused_after_object_expires(make_pipeline):
    source='First scene'
    p,core,engine,events,region=make_pipeline([line(source)],persist_results=True,max_missing=0)
    gate=engine.block(source)
    start(p,region)
    wait_until(lambda: engine.calls==[source])
    core.set_scene([line('Second scene')])
    wait_until(lambda: any(event[2][2]=='Second scene' for event in finals(events)))
    gate.set()
    wait_until(lambda:any(event[0]=='late_translation' for event in events.snapshot()))
    delivery=next(event[2] for event in events.snapshot() if event[0]=='late_translation')
    assert delivery[0] is p and delivery[2]['text'] and delivery[3]==source
    core.set_scene([line(source)])
    wait_until(lambda:any(event[2][2]==source for event in finals(events)))
    assert engine.calls.count(source)==1


def test_old_view_is_held_and_late_cannot_overwrite_new_view():
    overlay=OverlayState(hold_until_next=True)
    common={'x':20,'y':20,'w':200,'h':35,'_capture_origin':(0,0)}
    old={**common,'text':'Old','_source_stamp':1.}
    new={**common,'text':'New','_source_stamp':2.}
    overlay.apply_objects([{'track_id':1,'revision':1,'line':old}])
    assert overlay.apply_translation(1,{'_revision':1,'text':'Old localized','final':True})
    overlay.apply_objects([{'track_id':1,'revision':2,'line':new}])
    assert overlay.rendered[1]['text']=='Old localized' and overlay.rendered[1]['_hold_previous']
    assert overlay.apply_translation(1,{'_revision':2,'text':'New localized','final':False})
    assert overlay.rendered[1]['text']=='New localized'
    assert not overlay.apply_late(1,{**old,'text':'Too late','_revision':1,'final':True})


def test_quality_failure_requests_one_rescan_and_second_translation(make_pipeline):
    p,core,engine,events,region=make_pipeline([line('Look carefully.')],persist_results=True)
    original=engine.translate
    attempts=[]
    def broken_once(*args,**kwargs):
        attempts.append(args[3])
        if len(attempts)==1:
            raise RetryableTranslationError('test truncated stream')
        return original(*args,**kwargs)
    engine.translate=broken_once
    start(p,region)
    wait_until(lambda:len(finals(events))==1 and core.resets>=2)
    assert attempts==['Look carefully.']*2
    assert translation_issue('\u5f7c\u306f\u3053\u3053\u306b\u3044\u307e\u3059\u3002','He are waiting here.','en')=='agreement'
    assert translation_issue('\u3057\u3070\u3089\u304f\u5f85\u3063\u3066\u304f\u3060\u3055\u3044\u3002','This is because','en')=='dangling_clause'
    assert translation_issue('\u7d9a\u3051\u308b','Continue','en') is None


def test_default_density_is_based_on_vram():
    assert default_sampling_mode(0)=='auto'
    assert default_sampling_mode(8192)=='supersample'
    assert [fast_capture_interval_ms(size) for size in (0,3800,4096,8017,12288)]==[50,50,40,33,25]
    assert validate_tuning({'toggle_hotkey':'Ctrl+Alt+Y','sampling_mode':'off'})['toggle_hotkey']=='Ctrl+Alt+Y'


def test_startup_still_registers_toggle_if_retranslate_key_is_occupied():
    retranslate=Mock()
    retranslate.update.return_value=SimpleNamespace(error='occupied',registered=False,shortcut='Ctrl+Alt+R')
    toggle=Mock()
    toggle.update.return_value=SimpleNamespace(error='',registered=True,shortcut='Ctrl+Alt+T')
    lens=Mock();lens.update.return_value=SimpleNamespace(registered=False)
    app=SimpleNamespace(config={},hotkey=retranslate,toggle_hotkey=toggle,lens_hotkey=lens,agreement_accepted=True,
                        tr=lambda value:value,hotkey_hint=Mock(),settings_panel=SimpleNamespace(hotkey_status=Mock()))
    assert not App._configure_hotkey(app)
    toggle.update.assert_called_once_with(True,'Ctrl+Alt+T')
    app.hotkey_hint.set.assert_called_once_with('Ctrl+Alt+T · \u5f00\u5173\u7ffb\u8bd1')


def test_same_executable_recommendation_requires_confirmation_for_new_pid(monkeypatch):
    prior={'pid':9,'process_path':r'E:\games\Star.exe','title':'Star Game'}
    next_window={**prior,'pid':22,'hwnd':100}
    other={'pid':39,'hwnd':102,'title':'Star Game','process_path':r'E:\tool\other.exe'}
    assert matching_window([other,next_window],'Arcade archive',prior)==next_window
    notices=[]; confirms=[]; selections=[]
    def chosen():
        if not selections:raise UIValidationError('no explicit selection')
        return next_window
    app=SimpleNamespace(chosen_window=chosen,game=SimpleNamespace(get=lambda:'Arcade archive'),
                        refresh_windows=lambda:None,window_rows=[other,next_window],
                        windows_box=SimpleNamespace(current=lambda *index:selections.append(index[0]) if index else -1),
                        config={'profile_windows':{'Arcade archive':prior}},tr=lambda value:value,
                        root=None,window_label=lambda row:row['title'])
    monkeypatch.setattr(messagebox,'askyesno',lambda *args,**kwargs: confirms.append(args) or False)
    assert App._window_for_start(app) is None and not selections and len(confirms)==1
    def confirm_after_title_update(*args,**kwargs):
        app.window_rows=[other,{**next_window,'title':'Star Game — Paused'}]
        return True
    monkeypatch.setattr(messagebox,'askyesno',confirm_after_title_update)
    assert App._window_for_start(app)==next_window and selections==[1]
    selections.clear()
    app.game.get=lambda:''
    monkeypatch.setattr(messagebox,'showinfo',lambda *args,**kwargs:notices.append(args))
    assert App._window_for_start(app) is None and notices
