# SPDX-License-Identifier: MIT
"""Pure geometry tests: no game activation, capture, API or display changes."""
import pytest
from nkc_galgame_translator import windows
from nkc_galgame_translator.selection_regions import capture_plan


@pytest.mark.parametrize('client,desktop,expected',[
    ((0,30,1920,1080),(0,0,1920,1080),(0,30,1920,1050)),
    ((-30,-40,1000,800),(0,0,1920,1080),(0,0,970,760)),
    ((1900,1000,1000,800),(0,0,1920,1080),(1900,1000,20,80)),
    ((100,200,800,500),(0,0,1920,1080),(100,200,800,500)),
    ((-1950,20,1000,800),(-1920,0,3840,1080),(-1920,20,970,800)),
    ((-1800,-1100,1000,800),(-1920,-1080,3840,2160),(-1800,-1080,1000,780)),
    ((-900,30,1800,900),(-1920,0,3840,1080),(-900,30,1800,900)),
    ((1920,0,100,100),(0,0,1920,1080),None),
    ((-100,0,100,100),(0,0,1920,1080),None),
    ((0,-100,100,100),(0,0,1920,1080),None),
    ((0,0,0,100),(0,0,1920,1080),None),
    (None,(0,0,1920,1080),None),
])
def test_visible_client_geometry(client,desktop,expected,monkeypatch):
    monkeypatch.setattr(windows,'client_rect',lambda hwnd:client)
    monkeypatch.setattr(windows,'virtual_screen',lambda:desktop)
    assert windows.visible_client_rect(123)==expected
    assert windows.visible_client_selections(None,client)==expected


def test_manual_offsets_are_based_on_full_client_not_clipped_origin():
    relative=((80,50,150,40),(400,200,100,80))
    desktop=(0,0,1920,1080)
    assert windows.visible_client_selections(relative,(-60,-20,800,600),desktop)==(
        (20,30,150,40),(340,180,100,80))
    assert relative==((80,50,150,40),(400,200,100,80))
    # Moving the game moves these objects by exactly the client displacement.
    assert windows.visible_client_selections(relative,(-40,-10,800,600),desktop)==(
        (40,40,150,40),(360,190,100,80))


def test_partial_manual_selection_stays_at_actual_visible_source_pixels():
    relative=((20,10,200,100),(600,400,100,100))
    visible=windows.visible_client_selections(relative,(-100,-40,800,600),(0,0,1920,1080))
    assert visible==((0,0,120,70),(500,360,100,100))
    plan=capture_plan(visible)
    assert plan.bounds==(0,0,600,460)
    assert plan.regions==((0,0,120,70),(500,360,100,100))


@pytest.mark.parametrize('relative',[(0,0,100,100),((0,0,100,100),)])
def test_legacy_single_and_multi_forms_clip_equally(relative):
    assert windows.visible_client_selections(relative,(-50,100,800,600),(0,0,1920,1080))==((0,100,50,100),)


def test_offscreen_selection_disappears_then_reappears_without_changing_saved_offsets():
    relative=((0,0,50,40),(100,100,100,40))
    desktop=(0,0,1920,1080)
    assert windows.visible_client_selections(relative,(-100,-50,500,400),desktop)==((0,50,100,40),)
    assert windows.visible_client_selections(relative,(-600,-500,500,400),desktop) is None
    assert windows.visible_client_selections(relative,(20,30,500,400),desktop)==((20,30,50,40),(120,130,100,40))


def test_manual_selections_are_first_clipped_to_game_then_to_desktop():
    # Oversized saved offsets can never capture adjacent applications.
    assert windows.visible_client_selections((80,70,200,200),(300,200,100,90),(0,0,1920,1080))==((380,270,20,20),)
    assert windows.visible_client_selections((200,70,200,200),(300,200,100,90),(0,0,1920,1080)) is None


def test_app_start_provider_keeps_game_pid_gate_and_original_selection_offsets(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import nkc_galgame_translator.app as module
    from nkc_galgame_translator.tuning import TUNING_DEFAULTS
    app=object.__new__(module.App)
    app.profile_dialog=None  # .28 starts with no context manager open.
    app._require_agreement=Mock(return_value=True);app.stop=Mock()
    app.pipeline=None;app.config=dict(TUNING_DEFAULTS);app.ui_language='en'
    app.source=SimpleNamespace(get=lambda:'\u82f1\u8bed');app.target=SimpleNamespace(get=lambda:'\u7b80\u4f53\u4e2d\u6587')
    app.chosen_window=Mock(return_value={'hwnd':501,'pid':701})
    app.remember_translation_languages=Mock();app.remember_profile=Mock();app._remember_window=Mock()
    app.core=Mock();app.core.languages.return_value=['en-US']
    app.offline_only=SimpleNamespace(get=lambda:False);app.has_api_key=True
    app.capture_region=((80,50,150,40),(400,200,100,80));app.capture_region_target=(501,701)
    app.current_warmup_scope=Mock(return_value='test-fixture')
    app.get_engine=Mock(return_value=object());app.events=Mock()
    app.game=SimpleNamespace(get=lambda:'test');app.context=SimpleNamespace(get=lambda:'')
    app.start_button=Mock();app._refresh_mode_control=Mock();app.status=Mock()
    app.tr=lambda text:text;app._mode_name=lambda:'test'
    pipeline=Mock();monkeypatch.setattr(module,'Pipeline',Mock(return_value=pipeline))
    raw=[(-60,-20,800,600)];foreground=[True]
    monkeypatch.setattr(module,'client_rect',lambda hwnd:raw[0] if hwnd==501 else None)
    def is_foreground(hwnd,pid):
        assert (hwnd,pid)==(501,701)
        return foreground[0]
    monkeypatch.setattr(module,'foreground',is_foreground)
    monkeypatch.setattr(windows,'virtual_screen',lambda:(0,0,1920,1080))
    app.overlay_state=SimpleNamespace()
    app.lightweight_var=SimpleNamespace(get=lambda:False)
    app.settings_error_message=repr
    app._next_process_check=0.
    monkeypatch.setattr(module,'GameProcess',Mock(return_value=Mock(exited=Mock(return_value=False))))
    app.start()
    assert pipeline.start.call_count==1, app.status.set.call_args
    app._remember_window.assert_called_once_with({'hwnd':501,'pid':701})
    provider=pipeline.start.call_args.args[0]
    app.core.set_target.assert_called_once_with(501,701)
    assert provider()==((20,30,150,40),(340,180,100,80))
    raw[0]=(-40,-10,800,600)
    assert provider()==((40,40,150,40),(360,190,100,80))
    foreground[0]=False
    assert provider() is None
    foreground[0]=True;raw[0]=None
    assert provider() is None
