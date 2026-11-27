# SPDX-License-Identifier: MIT
"""Target identity and wait UX with fake Win32 only; no focus, capture or API."""
from types import SimpleNamespace
from unittest.mock import Mock
from threading import Event
import os
import queue
import subprocess
import sys
import pytest

from nkc_galgame_translator import windows
import nkc_galgame_translator.app as module
from nkc_galgame_translator.i18n import translate, catalog
from nkc_galgame_translator.presentation import OverlayState


def row(**changes):
    value={'hwnd':501,'pid':701,'title':'Windose','process_path':r'E:\NEEDY GIRL OVERDOSE\Windose.exe',
           'exe_name':'Windose.exe','class_name':'UnityWndClass'}
    value.update(changes);return value


@pytest.mark.parametrize('exe,cls',[
    ('explorer.exe','CabinetWClass'),('EXPLORER.EXE','Whatever'),('','CabinetWClass'),
    ('','ExploreWClass'),('','Progman'),('','WorkerW'),('','Shell_TrayWnd'),
    ('TextInputHost.exe','Windows.UI.Core.CoreWindow'),('ctfmon.exe',''),
    ('SearchHost.exe',''),('StartMenuExperienceHost.exe',''),('ShellExperienceHost.exe',''),
    ('dwm.exe',''),('','MSCTFIME UI'),('','IME'),('','NKC_Galgame_TranslatorReplacement'),('','tooltips_class32'),
    ('GameBar.exe',''),('GameBarFTServer.exe',''),('GameBarPresenceWriter.exe',''),
])
def test_filters_shell_input_and_overlay_by_metadata(exe,cls):
    assert not windows.translation_target(row(title='NEEDY GIRL OVERDOSE',process_path=exe,exe_name=exe,class_name=cls))


@pytest.mark.parametrize('exe,cls,title',[
    ('Windose.exe','UnityWndClass','Windose'),('python.exe','TkTopLevel','English test application'),
    ('notepad.exe','Notepad','NEEDY GIRL OVERDOSE'),('msedge.exe','Chrome_WidgetWin_1','Explorer help'),
    ('ApplicationFrameHost.exe','ApplicationFrameWindow','UWP game'),
    ('DOSBox.exe','SDL_app','Space Rogue'),('','CustomAppClass','English example'),
    ('myexplorer.exe','MyWindow','Folder game'),('Test.exe','Window','explorer.exe'),
])
def test_ordinary_apps_and_game_named_titles_are_not_guessed(exe,cls,title):
    assert windows.translation_target(row(process_path=exe,exe_name=exe,class_name=cls,title=title))


def test_own_process_is_excluded():
    assert not windows.translation_target(row(pid=os.getpid()))


def fake_user(*,exists=True,pid=701,minimized=False,visible=True,active=True):
    user=SimpleNamespace(IsWindow=Mock(return_value=exists),IsIconic=Mock(return_value=minimized),
        IsWindowVisible=Mock(return_value=visible),GetForegroundWindow=Mock(return_value=501 if active else 999))
    user.GetWindowThreadProcessId=Mock(side_effect=lambda hwnd,p:setattr(p._obj,'value',pid))
    user.GetWindowTextLengthW=Mock(return_value=7)
    user.GetWindowTextW=Mock(side_effect=lambda hwnd,b,n:setattr(b,'value','Windose'))
    user.GetClassNameW=Mock(side_effect=lambda hwnd,b,n:setattr(b,'value','UnityWndClass'))
    return user


def test_metadata_and_enum_cache_process_path_once_per_pid(monkeypatch):
    user=fake_user();user.EnumWindows=lambda callback,arg:[callback(h,arg) for h in (501,502)]
    monkeypatch.setattr(windows,'user32',user)
    lookup=Mock(return_value=r'E:\Game\Windose.exe');monkeypatch.setattr(windows,'process_path',lookup)
    result=windows.window_list()
    assert [r['hwnd'] for r in result]==[501,502]
    assert all(r['exe_name']=='Windose.exe' and r['class_name']=='UnityWndClass' for r in result)
    lookup.assert_called_once_with(701)


def test_metadata_rejects_pid_change_during_read(monkeypatch):
    user=fake_user();pids=iter([701,702]);user.GetWindowThreadProcessId.side_effect=lambda hwnd,p:setattr(p._obj,'value',next(pids))
    monkeypatch.setattr(windows,'user32',user);monkeypatch.setattr(windows,'process_path',lambda pid:'game.exe')
    assert windows.window_metadata(501) is None


@pytest.mark.parametrize('values,expected',[
    ({'exists':False},'closed'),({'pid':702},'replaced'),({'minimized':True},'minimized'),
    ({'visible':False},'hidden'),({'active':False},'background'),({},'active'),
])
def test_state_probe_is_pid_bound_and_never_opens_process(monkeypatch,values,expected):
    monkeypatch.setattr(windows,'user32',fake_user(**values))
    lookup=Mock(side_effect=AssertionError('No process path lookup on status timer'))
    monkeypatch.setattr(windows,'process_path',lookup)
    assert windows.window_state(501,701)==expected
    lookup.assert_not_called()


class Value:
    def __init__(self,value=''):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


class Box:
    def __init__(self,index=-1):self.index=index;self.values=[];self.text=''
    def current(self,index=None):
        if index is not None:self.index=index
        return self.index
    def set(self,text):self.index=-1;self.text=text
    def __setitem__(self,key,value):assert key=='values';self.values=value


def app_stub():
    app=object.__new__(module.App)
    app.profile_dialog=None  # Match the .28 constructor before target validation.
    app.tr=lambda text:text;app.window_rows=[row()];app.windows_box=Box(0)
    app.target_window=row();app.pipeline=SimpleNamespace(stop_event=Event(),generation=3)
    app.status=Value();app.regions={};app._run_status_error=False;app._next_target_status=0
    return app


def test_refresh_filters_folders_shows_exe_and_preserves_exact_identity(monkeypatch):
    app=app_stub();app.windows_box=Box(-1)
    rows=[row(title='NEEDY GIRL OVERDOSE',process_path='explorer.exe',hwnd=600,pid=702,class_name='CabinetWClass'),row(),row(hwnd=503,pid=703)]
    monkeypatch.setattr(module,'window_list',lambda:rows)
    app.refresh_windows();assert len(app.window_rows)==2 and app.windows_box.current()==-1
    assert app.windows_box.values[0]=='Windose · Windose.exe · PID 701'
    app.windows_box.current(1);rows.reverse();app.refresh_windows()
    assert app.window_rows[app.windows_box.current()]['pid']==703
    rows[0]={**rows[0],'pid':704};app.refresh_windows()
    assert app.windows_box.current()==-1  # No fallback to another matching title.


@pytest.mark.parametrize('current', [None,row(pid=702),row(process_path='explorer.exe',class_name='CabinetWClass')])
def test_choose_rejects_closed_reused_and_shell_window(monkeypatch,current):
    app=app_stub();monkeypatch.setattr(module,'window_metadata',lambda hwnd:current)
    with pytest.raises(module.UIValidationError):app.chosen_window()


def test_choose_fresh_identity_and_title_without_switching_window(monkeypatch):
    app=app_stub();current=row(title='Windose - Game')
    meta=Mock(return_value=current);monkeypatch.setattr(module,'window_metadata',meta)
    assert app.chosen_window()==current;meta.assert_called_once_with(501)
    app.windows_box.index=99
    with pytest.raises(module.UIValidationError,match='\u8bf7\u5148\u9009\u62e9'):app.chosen_window()


def test_start_rejects_stale_selection_before_core_or_api(monkeypatch):
    app=app_stub();app.pipeline=None;app.stop=Mock();app._require_agreement=Mock(return_value=True)
    app.get_engine=Mock(side_effect=AssertionError('No API'));app.core=None
    monkeypatch.setattr(module,'window_metadata',lambda hwnd:None)
    app.start()
    assert '\u5df2\u5173\u95ed\u6216\u8fdb\u7a0b\u5df2\u53d8\u5316' in app.status.get();app.get_engine.assert_not_called()
    assert app.pipeline is None and app.core is None


@pytest.mark.parametrize('state,word',[
    ('closed','\u5df2\u5173\u95ed'),('replaced','\u8fdb\u7a0b\u5df2\u53d8\u5316'),('minimized','\u5df2\u6700\u5c0f\u5316'),
    ('hidden','\u4e0d\u53ef\u89c1'),('background','\u6b63\u5728\u7b49\u5f85\u76ee\u6807\u7a97\u53e3'),('active','\u6b63\u5728\u8bc6\u522b\u76ee\u6807\u7a97\u53e3'),
])
def test_running_status_names_exact_target(monkeypatch,state,word):
    app=app_stub();probe=Mock(return_value=state);monkeypatch.setattr(module,'window_state',probe)
    app._refresh_running_status({},now=0)
    assert word in app.status.get() and 'Windose.exe · PID 701' in app.status.get()
    probe.assert_called_once_with(501,701)


def test_game_process_exit_stops_translation_even_during_an_error(monkeypatch):
    app = app_stub()
    app.overlay_state = OverlayState()
    app.overlay_state.rendered[1] = {'text': 'Previous overlay'}
    app.core = Mock()
    app.pipeline.stop = Mock(side_effect=app.pipeline.stop_event.set)
    app.pipeline.join = Mock()
    app.pipeline.alive = False
    app._mode_name = lambda: 'AI'
    app._refresh_mode_control = Mock()
    app.object_metric = Value()
    app._run_status_error = True
    app._next_process_check = 0
    with subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
                          stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW) as child:
        app.target_window = row(pid=child.pid)
        watch = windows.GameProcess(child.pid)
        app._game_process = watch
        try:
            # A vanished HWND while its owning process is alive is not an exit.
            monkeypatch.setattr(module, 'window_state', lambda *args: 'closed')
            assert not app._check_game_process()
            assert app.pipeline and app.overlay_state.rendered
            child.communicate(timeout=5)
            app._next_process_check = 0
            assert app._check_game_process()
        finally:
            watch.close()
    assert app.pipeline is None and app.target_window is None
    assert not app.overlay_state.rendered
    app.core.hide_overlay.assert_called_once()
    assert '\u6e38\u620f\u7a0b\u5e8f\u5df2\u9000\u51fa\uff0c\u7ffb\u8bd1\u5df2\u505c\u6b62' in app.status.get()


def test_status_throttle_ai_and_capture_diagnostics(monkeypatch):
    app=app_stub();probe=Mock(return_value='active');monkeypatch.setattr(module,'window_state',probe)
    app._refresh_running_status({'in_flight':2},now=0);assert '\u7b49\u5f85 AI' in app.status.get()
    app._refresh_running_status({},now=.9);probe.assert_called_once()
    app._capture_region_unavailable=True;app._refresh_running_status({},now=1)
    assert '\u6240\u9009\u533a\u57df\u4e0d\u5728\u53ef\u89c1\u5ba2\u6237\u533a' in app.status.get()
    app._capture_region_unavailable=False;app._last_ocr_line_count=0;app._refresh_running_status({},now=2)
    assert '\u5c1a\u672a\u627e\u5230\u53ef\u7ffb\u8bd1\u6587\u5b57' in app.status.get()
    app._last_ocr_line_count=2;app.regions={1:object()};app._refresh_running_status({},now=3)
    assert '\u8bd1\u6587\u5df2\u663e\u793a' in app.status.get()
    assert probe.call_count==4


@pytest.mark.parametrize('kind,payload',[
    ('error','API authentication failed'),
    ('timing',{'lines':[],'vision_error':'Vision unavailable'}),
])
def test_drain_errors_are_not_overwritten_by_periodic_wait_state(monkeypatch,kind,payload):
    app=app_stub();app.events=queue.SimpleQueue();app.events.put((kind,3,payload))
    app.overlay_state=OverlayState();app.core=None;app.engine=None;app.next_stats_update=0
    app.config={};app.manual_busy=False;app.start_button=Mock();app.metric=Value();app.object_metric=Value()
    app._refresh_mode_control=Mock();app._mode_name=lambda:'AI';app.root=Mock()
    monkeypatch.setattr(module,'foreground',lambda *args:False)
    probe=Mock(return_value='background');monkeypatch.setattr(module,'window_state',probe)
    app.drain()
    expected=payload if isinstance(payload,str) else payload['vision_error']
    assert app.status.get()==expected and app._run_status_error
    app._refresh_running_status({},now=500);assert app.status.get()==expected
    probe.assert_not_called()


@pytest.mark.parametrize('lang',['en','ja'])
def test_target_ux_translates_all_new_messages_and_preserves_identity(monkeypatch,lang):
    messages=[k for k in catalog() if '{window}' in k]
    assert len(messages)>=10
    for message in messages:
        localized=translate(message,lang)
        assert localized!=message and '{window}' in localized
        displayed=localized.format(window='Windose.exe · PID 701',pid=500)
        assert 'Windose.exe · PID 701' in displayed
        if '{pid}' in message:
            assert '500' in displayed
    app=app_stub();app.tr=lambda text:translate(text,lang)
    monkeypatch.setattr(module,'window_state',lambda *args:'background')
    app._refresh_running_status({},now=0)
    assert ('Waiting' if lang=='en' else '\u5f85\u6a5f\u4e2d') in app.status.get()
