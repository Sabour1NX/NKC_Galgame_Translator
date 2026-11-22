# SPDX-License-Identifier: MIT
"""0.01.13 settings/identity/recognition integration with hidden synthetic UI."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import Mock

import httpx
import pytest

import nkc_galgame_translator.app as module
from nkc_galgame_translator.config_store import ConfigStore
from nkc_galgame_translator.game_identity import warmup_identity
from nkc_galgame_translator.i18n import translate, catalog
from nkc_galgame_translator.pipeline import Pipeline
from nkc_galgame_translator.presentation import OverlayState
from nkc_galgame_translator.settings_ui import OCR_MODE_LABELS
from nkc_galgame_translator.vision_core import VisionCore

_setup=runpy.run_path(str(Path(__file__).with_name('test_app_setup.py')))
hidden_app=_setup['hidden_app'];SYNTHETIC_KEY=_setup['SYNTHETIC_KEY']


def pump(app,predicate):
    until=time.monotonic()+4
    while not predicate():
        app.root.update()
        if time.monotonic()>until:raise AssertionError('UI operation timed out')
        time.sleep(.005)


class FakeCore:
    def __init__(self,**options):
        self.options=options;self._lock=threading.RLock();self.native=Mock()
        self._native_languages=['en-US'];self.closed=False;self.pending=False
        self.hide_overlay=Mock();self.reset=Mock();self.cancel_pending=Mock();self.set_target=Mock();self.set_overlay_font=Mock()
        self.set_overlay_options=Mock()
    def enable_live_capture(self, **options): self.capture_options = options
    def languages(self):return ['en-US','ja-JP']
    def close(self):self.closed=True


class IdlePipeline:
    def __init__(self,core,engine,emit,**options):
        self.core=core;self.engine=engine;self.options=options;self.alive=False
        self.stop_event=threading.Event();self.generation=1
    def start(self,*args):self.start_args=args;self.alive=True
    def stop(self):
        self.alive=False;self.stop_event.set()
        if hasattr(self.core,'cancel_pending'):self.core.cancel_pending()
    def join(self,*args):return True


def prepare_capture(app,patch):
    import nkc_galgame_translator.ocr as ocr
    created=[]
    def new_core(**kwargs):
        core=FakeCore(**kwargs);created.append(core);return core
    patch.setattr(ocr,'OcrCore',new_core)
    patch.setattr(module,'Pipeline',IdlePipeline)
    patch.setattr(module, 'GameProcess', Mock(return_value=Mock(exited=Mock(return_value=False))))
    patch.setattr(module,'foreground',lambda *args:False)
    patch.setattr(app,'chosen_window',lambda:{'hwnd':123,'pid':456,'process_path':r'C:\Private Games\Demo.exe'})
    return created


def case_new_settings_roundtrip_languages_and_resource_rebuild(root,patch):
    with hidden_app(root,patch,settings={'source_lang':'en'}) as app:
        panel=app.settings_panel
        assert panel.vars['context_history_records'].get()=='2'
        assert 'smart_mode' not in panel.vars
        assert panel.vars['context_max_chars'].get()=='16384'
        assert panel.values()['vision_ocr_mode'] in ('off','force')
        assert panel.vars['vision_interval_ms'].get()=='3000'
        engine=app.get_engine();core=FakeCore();app.core=core
        panel.ocr_mode_var.set('\u50cf\u7d20\u6587\u5b57\u7cbe\u8bfb')
        panel.vars['context_history_records'].set('1')
        panel.vision_mode_var.set(app.tr('\u622a\u56fe\u8bc6\u522b\u5f3a\u5236'))
        panel.vars['vision_interval_ms'].set('5500')
        assert app.save_settings()
        assert engine._stop.is_set() and app.engine is None
        assert core.closed and app.core is None
        for selection,code,expected in [('English','en','Pixel-text recognition'),
                                        ('\u65e5\u672c\u8a9e (beta)','ja','Pixel Font \u306e\u7cbe\u5bc6\u8a8d\u8b58'),
                                        ('\u7b80\u4f53\u4e2d\u6587','zh-CN','\u50cf\u7d20\u6587\u5b57\u7cbe\u8bfb')]:
            panel.app_language_var.set(selection)
            assert app.save_settings()
            assert panel.ocr_mode_var.get()==expected
            assert expected in panel.ocr_mode_box['values']
            assert panel.values()['ocr_mode']=='pixel'
            loaded=ConfigStore(root).load()
            assert loaded['ocr_mode']=='pixel' and loaded['app_language']==code
            assert loaded['context_history_records']==1 and loaded['vision_interval_ms']==5500 and loaded['vision_ocr_mode']=='force'
        before=app.config_store.config_path.read_bytes()
        for invalid in ({'context_history_records':65},{'vision_ocr':'false'},{'vision_interval_ms':999},{'ocr_mode':'remote'}):
            assert not app.save_settings(invalid)
            assert app.config_store.config_path.read_bytes()==before
        panel.refresh(True)
        assert str(panel.ocr_mode_box['state'])=='disabled'
        panel.refresh(False)
        assert str(panel.ocr_mode_box['state'])=='readonly'


def case_ai_context_settings_save_in_all_languages(root,patch):
    with hidden_app(root,patch,key=SYNTHETIC_KEY,settings={'offline_only':False}) as app:
        panel=app.settings_panel
        for label,code in [('English','en'),('\u65e5\u672c\u8a9e (beta)','ja'),('\u7b80\u4f53\u4e2d\u6587','zh-CN')]:
            panel.app_language_var.set(label)
            panel.vars['context_max_chars'].set('8192')
            assert app.save_settings()
            assert ConfigStore(root).load()['context_max_chars']==8192
            assert app.get_engine().get_stats()['ai_only']
            expected=translate(module.ui_source('Translation backend: LLM ({model})'),code).format(model=app.config['model'])
            assert app._mode_name()==expected and expected in app.footer_text.get()
        for invalid in ({'context_max_chars':511},{'context_history_records':65},{'ocr_refine_workers':9}):
            assert not app.save_settings(invalid)


def case_saved_ocr_selection_survives_direct_ui_switch_before_save(root,patch):
    with hidden_app(root,patch,settings={'ocr_mode':'native','app_language':'en'}) as app:
        for language in ('ja','zh-CN','en'):
            app.apply_ui_language(language)
            assert app.settings_panel.ocr_mode_var.get()=='Windows OCR'
            assert app.settings_panel.values()['ocr_mode']=='native'
            assert app.settings_panel.values()['app_language']==language
        app.settings_panel.ocr_mode_var.set('Automatic OCR')
        app.apply_ui_language('ja')
        assert app.settings_panel.ocr_mode_var.get()=='\u81ea\u52d5\u8a8d\u8b58'
        assert app.settings_panel.values()['ocr_mode']=='auto'


def case_pipeline_scope_uses_profile_before_executable_without_changing_dictionary(root,patch):
    with hidden_app(root,patch,settings={'source_lang':'en','vision_ocr':False}) as app:
        created=prepare_capture(app,patch)
        app.game.set('  \u6e38\u620f\u6863\u6848  ')
        app.start()
        assert app.pipeline.options['warmup_scope']=='profile:\u6e38\u620f\u6863\u6848'
        assert app.pipeline.start_args[1]=='\u6e38\u620f\u6863\u6848'
        assert created[0].options['mode']=='auto'
        app.stop();app.game.set('')
        app.start()
        identity=app.pipeline.options['warmup_scope']
        assert identity==warmup_identity('',r'c:\private games\DEMO.EXE')
        assert identity.startswith('exe:') and 'Private' not in identity and '\\' not in identity
        assert app.pipeline.start_args[1]==''


def case_vision_rebinds_after_api_engine_change_and_unwraps_offline(root,patch):
    url = 'https://api.deepseek.com/v1'
    with hidden_app(root,patch,key=SYNTHETIC_KEY,settings={'source_lang':'en','offline_only':False,
            'base_url':url,'vision_ocr':True,'vision_interval_ms':4500,'settle_ms':120,'ocr_mode':'pixel'}) as app:
        created=prepare_capture(app,patch)
        app.start()
        first=app.core;first_engine=app.engine
        assert isinstance(first,VisionCore) and first.recognizer.engine is first_engine
        assert first.interval==4.5 and first.settle==.12
        app.stop()
        app.save_api_settings(url,_setup['MODEL'],api_key=SYNTHETIC_KEY+'replacement',offline_only=False)
        assert first_engine._stop.is_set() and app.engine is None
        app.start()
        second=app.core
        assert isinstance(second,VisionCore) and second is not first and first._closed
        assert second.recognizer.engine is app.engine and app.engine is not first_engine
        assert len(created)==2 and created[0].closed
        app.stop();app.start()
        assert app.core is second and len(created)==2
        app.stop()
        app.offline_only.set(True);app.change_translation_mode()
        app.start()
        assert not isinstance(app.core,VisionCore) and second._closed
        assert len(created)==3 and app.engine.offline_only


def case_vision_checkbox_without_key_stays_local_and_pending_blocks_changes(root,patch):
    with hidden_app(root,patch,settings={'source_lang':'en','vision_ocr':True}) as app:
        created=prepare_capture(app,patch)
        app.start()
        assert isinstance(app.core,FakeCore) and len(created)==1
        assert app.engine.offline_only
        app.stop();app.core.pending=True
        before=app.config_store.config_path.read_bytes()
        assert not app.save_settings({'warmup_limit':50})
        assert app.config_store.config_path.read_bytes()==before
        assert app.show_api_settings() is None
        app.core.pending=False


def case_manual_warmup_is_local_identity_and_busy_click_does_not_repeat_request(root,patch):
    requests=[];entered=threading.Event();release=threading.Event()
    def handler(request):
        requests.append(json.loads(request.content));entered.set()
        assert release.wait(4)
        event={'choices':[{'delta':{'content':'\u6b22\u8fce'},'finish_reason':'stop'}]}
        return httpx.Response(200,text='data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n')
    # Create an explicitly synthetic transport before the hidden fixture forbids
    # any application-owned client construction.
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with hidden_app(root,patch,key=SYNTHETIC_KEY,settings={'source_lang':'en','offline_only':False,'warmup_limit':1}) as app:
            app.game.set('PrivateProfile-Settings')
            engine=app.get_engine();engine._client=client;engine._owned_client=False
            app.manual_input.insert('1.0','Welcome')
            app.manual_translate()
            assert entered.wait(2)
            try:
                app.manual_translate()
                assert len(requests)==1 and app.manual_busy
            finally:release.set()
            pump(app,lambda:not app.manual_busy)
            assert app.manual_output.get('1.0','end').strip()=='\u6b22\u8fce'
            progress=engine.get_warmup_status('PrivateProfile-Settings','en','zh-Hans',warmup_scope='profile:PrivateProfile-Settings')
            assert not progress['active']
            assert 'PrivateProfile' not in json.dumps(requests) and 'warmup_scope' not in json.dumps(requests)
            app.manual_translate();pump(app,lambda:not app.manual_busy)
            assert len(requests)==2  # Every new invocation uses AI; history is only reference.


def case_unlimited_quota_saves_restores_and_remains_disabled_while_busy(root,patch):
    with hidden_app(root,patch,key=SYNTHETIC_KEY,settings={'source_lang':'en',
            'offline_only':False,'warmup_limit':0,'max_requests':20}) as app:
        panel=app.settings_panel
        assert panel.vars['unlimited_requests'].get() is False
        assert str(panel.request_limit_control['state'])=='normal'
        for selection,code in [('English','en'),('\u65e5\u672c\u8a9e (beta)','ja'),('\u7b80\u4f53\u4e2d\u6587','zh-CN')]:
            panel.app_language_var.set(selection)
            old_engine=app.get_engine()
            panel.vars['unlimited_requests'].set(True)
            assert str(panel.request_limit_control['state'])=='disabled'
            assert app.save_settings()
            assert old_engine._stop.is_set() and app.engine is None
            stored=ConfigStore(root).load()
            assert stored['unlimited_requests'] is True and stored['max_requests']==20
            assert stored['app_language']==code
            assert panel.unlimited_requests_check['text']==translate('API \u8bf7\u6c42\u65e0\u4e0a\u9650',code)
            rebuilt=app.get_engine()
            assert rebuilt.unlimited_requests and rebuilt.max_requests==20
            assert rebuilt.get_stats()['requests_remaining'] is None
            app.next_stats_update=0
            app.drain()  # The live title/status refresh accepts unbounded stats.
            panel.refresh(True)
            assert str(panel.unlimited_requests_check['state'])=='disabled'
            assert str(panel.request_limit_control['state'])=='disabled'
            panel.refresh(False)
            assert str(panel.unlimited_requests_check['state'])=='normal'
            assert str(panel.request_limit_control['state'])=='disabled'
            before=app.config_store.config_path.read_bytes()
            app.manual_busy=True
            assert not app.save_settings({'unlimited_requests':False})
            assert app.config_store.config_path.read_bytes()==before
            app.manual_busy=False
            panel.vars['unlimited_requests'].set(False)
            assert str(panel.request_limit_control['state'])=='normal'
            assert app.save_settings()
            assert rebuilt._stop.is_set()
            saved=ConfigStore(root).load()
            assert saved['unlimited_requests'] is False and saved['max_requests']==20
            assert app.get_engine().get_stats()['requests_remaining']==20
        before=app.config_store.config_path.read_bytes()
        assert not app.save_settings({'unlimited_requests':'true'})
        assert app.config_store.config_path.read_bytes()==before


CASES=[name for name in globals() if name.startswith('case_')]


@pytest.mark.parametrize('case',CASES)
def test_hidden_app_13_flow(case):
    process=subprocess.run([sys.executable,'-c','import runpy,sys;runpy.run_path(sys.argv[1],run_name="__main__")',
        str(Path(__file__).resolve()),case],cwd=module.ROOT,capture_output=True,text=True,timeout=40,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode==0,process.stdout+process.stderr


@pytest.mark.parametrize('identity',[None,'exe:synthetic'])
def test_pipeline_legacy_engine_signature_and_optional_warmup_kwarg(identity):
    helpers=runpy.run_path(str(Path(__file__).with_name('test_pipeline.py')))
    core=helpers['FakeCore']([helpers['line']('Welcome')]);events=helpers['Recorder']()
    base=helpers['FakeEngine']
    seen=[]
    if identity is None:engine=base()  # Deliberately has no **kwargs or warmup parameter.
    else:
        class ScopeEngine(base):
            def translate(self,*args,warmup_scope=None):
                seen.append(warmup_scope);return super().translate(*args)
        engine=ScopeEngine()
    pipeline=Pipeline(core,engine,events,interval=.005,settle=0,merge_lines=False,warmup_scope=identity)
    try:
        pipeline.start(lambda:(0,0,800,600),'','en','zh-Hans')
        helpers['wait_until'](lambda:len(helpers['finals'](events))==1)
        assert engine.calls==['Welcome']
        assert seen==([] if identity is None else [identity])
    finally:
        pipeline.stop();pipeline.join(2);pipeline.pool.shutdown(wait=True,cancel_futures=True)


def test_new_labels_and_diagnostics_are_localized_and_reverse_unique():
    for original in ('\u81ea\u52a8\u8bc6\u522b','\u50cf\u7d20\u6587\u5b57\u7cbe\u8bfb','\u672c\u5730\u6587\u5b57\u8bc6\u522b','\u7ffb\u8bd1\u6700\u5927\u8f93\u51fa Token',
            '\u65b0\u6e38\u620f\u79ef\u6781\u6a21\u5f0f · {completed}/{limit}',
            '\u591a\u8bed\u79cd\u81ea\u52a8\u7ffb\u8bd1 · {progress}',
            '\u667a\u80fd\u6df7\u5408\u672c\u5730\u77ed\u6587\u672c\u5b57\u7b26\u4e0a\u9650','\u667a\u80fd\u6df7\u5408\uff1a\u81ea\u52a8\u9009\u62e9\u672c\u5730\u6216 LLM \u7ffb\u8bd1',
            '\u667a\u80fd\u6df7\u5408 · \u672c\u5730 / LLM \u81ea\u52a8\u9009\u62e9','\u667a\u80fd\u7ffb\u8bd1\u6a21\u5f0f\u987b\u4e3a\u5f00\u6216\u5173\u3002',
            '\u667a\u80fd\u7ffb\u8bd1\u77ed\u6587\u672c\u4e0a\u9650\u987b\u4e3a 1 \u81f3 256 \u7684\u6574\u6570\u3002',
            'AI \u56fe\u50cf\u8bc6\u522b\u8bf7\u6c42\u5931\u8d25\uff08HTTP {code}\uff09\uff0c\u7ee7\u7eed\u4f7f\u7528\u672c\u5730\u8bc6\u522b\u3002'):
        english=translate(original,'en');japanese=translate(english,'ja')
        assert english!=original and japanese!=english
        assert translate(japanese,'zh-CN')==original
    aliases={}
    for original,targets in catalog().items():
        for alias in (original,*targets):assert aliases.setdefault(alias,original)==original,alias


def test_smart_learning_help_uses_512_and_separates_request_quota_from_learning():
    choices=catalog()
    assert not any('\u65b0\u6e38\u620f\u9ed8\u8ba4\u524d 80 \u6b21' in source for source in choices)
    learning=next(source for source in choices if source.startswith('\u65b0\u6e38\u620f\u9ed8\u8ba4\u524d 512 \u6b21'))
    for code in ('en','ja'):
        localized=translate(learning,code)
        assert '512' in localized and localized!=learning
        assert translate(localized,'zh-CN')==learning
    explanation=next(source for source in choices if source.startswith('\u77ed\u6587\u672c\u9700\u4e3a\u5355\u884c'))
    assert '6 \u4e2a\u8bcd' in explanation and '\u8bc6\u522b\u8bf7\u6c42\u4e0d\u8ba1\u5165\u6210\u529f\u7ffb\u8bd1\u6b21\u6570' in explanation
    assert 'request quota' in translate(explanation,'en')
    assert 'Request \u67a0' in translate(explanation,'ja')


def warmup_mode_app(states, sources, *, language='zh-CN'):
    """Exercise the actual UI status method without creating Tk or a worker."""
    app=object.__new__(module.App)
    app.ui_language=language
    app.config={'smart_mode':True, 'model':'lab/test-v2'}
    app.offline_only=Mock(get=Mock(return_value=False))
    app.source=Mock(get=Mock(return_value='\u65e5\u8bed'))
    app.target=Mock(get=Mock(return_value='\u7b80\u4f53\u4e2d\u6587'))
    app.game=Mock(get=Mock(return_value='Game'))
    app.target_window=None
    app.pipeline=object()  # No worker API/state is available to the status code.
    app.overlay_state=OverlayState()
    app.overlay_state.apply_objects([
        {'track_id':index,'revision':1,'line':{'source_lang':source}}
        for index,source in enumerate(sources)])
    app.engine=Mock(spec=['get_warmup_status'])
    app.engine.get_warmup_status.side_effect=lambda game,source,target,**options:dict(states[source])
    return app


def learning(completed,reason='collecting'):
    return {'completed':completed,'limit':512,'active':reason=='collecting','reason':reason}


@pytest.mark.parametrize('completed',[0,37,512])
@pytest.mark.parametrize('sources',[['en'],['en','ja']])
def test_retired_learning_cannot_change_ai_route_status(completed,sources):
    app=warmup_mode_app({'en':learning(completed),'ja':learning(0)},sources)
    assert 'lab/test-v2' in app._mode_name()
    app.engine.get_warmup_status.assert_not_called()


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='app13-ui-') as folder,pytest.MonkeyPatch.context() as patch:
        globals()[sys.argv[-1]](Path(folder),patch)
