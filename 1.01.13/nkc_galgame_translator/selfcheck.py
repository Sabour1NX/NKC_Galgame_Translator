# SPDX-License-Identifier: MIT
"""No-dialog packaged runtime check. No network or memory writes."""

from .i18n import ui_source
import json
from pathlib import Path
import sys
import tempfile
import shutil
from PIL import Image, ImageDraw, ImageFont
from . import app as app_module
from .app import App, ROOT
from .ocr import OcrCore
from .tracking import ObjectTracker
from . import __version__
from .selection_regions import capture_plan, mask_regions
from .presentation import OverlayState
from .translation import TranslationEngine, LocalTranslationMiss, TranslationError
from .dictionary_import import parse_dictionary
from .branding import window_icon_handles
from .languages import label_translation
from .i18n import detect_system_language, agreement_text
from .game_identity import warmup_identity
from .vision import parse_transcription
from .config_store import ConfigStore
from .tuning import validate_tuning, PERFORMANCE_PRESETS
from .ocr_quality import rejection_reason
from .layout import merge_dialogue_lines, reflow_translation
from .translatability import preservation_reason, unchanged_translation
from .native import fixed_source_rows

def run():
    # Never migrate a real credential or record user consent during diagnostics.
    with tempfile.TemporaryDirectory(prefix='nishokuchou-selfcheck-') as folder:
        temporary = Path(folder)
        shutil.copytree(ROOT/'assets', temporary/'assets')
        (temporary/'config').mkdir()
        shutil.copyfile(ROOT/'config/example.json', temporary/'config/example.json')
        (temporary/'config/local.json').write_text('{"offline_only":true}', encoding='utf-8')
        app_module.ROOT = temporary
        app = None
        original_tk = app_module.tk.Tk
        def hidden_tk(*args, **kwargs):
            window = original_tk(*args, **kwargs)
            window.withdraw()
            return window
        try:
            app_module.tk.Tk = hidden_tk
            try:
                app=App(show_setup=False)
            finally:
                app_module.tk.Tk = original_tk
            app.root.update_idletasks()
            _check(app)
        finally:
            if app: app.close()
            app_module.ROOT = ROOT


def _check(app):
    assert rejection_reason('Neu or Id gane?','en')
    assert rejection_reason('(N)ew or (O)ld game?','en') is None
    assert rejection_reason('Karonus system','en') is None
    for text in ('Siiius', 'SYS f ebn', 'HP 300', 'F1', '123'):
        assert preservation_reason(text, 'en')
    for text in ('STATUS', 'CHART', 'SCAN', '(Gun laser)', 'Sirius'):
        assert preservation_reason(text, 'en') is None
    assert unchanged_translation('Sirius', 'SIRIUS')
    assert not unchanged_translation('STATUS', '\u72b6\u6001')
    paragraph = merge_dialogue_lines([
        {'text': 'The airlock opens at a touch', 'x': 10, 'y': 10, 'w': 360, 'h': 24},
        {'text': 'and lets you inside.', 'x': 10, 'y': 38, 'w': 240, 'h': 24},
    ])
    assert len(paragraph) == 1 and paragraph[0]['_flow_layout'] is True
    assert paragraph[0]['text'] == 'The airlock opens at a touch\nand lets you inside.'
    assert len(paragraph[0]['_source_rows']) == 2
    fixed = fixed_source_rows({**paragraph[0], '_fixed_layout': True})
    assert len(fixed) == 2 and [row.y for row in fixed] == [0, 28]
    assert reflow_translation('\u6c14\u95f8\u6253\u5f00\uff0c\n\u4f60\u8fdb\u5165\u8231\u5185\u3002') == '\u6c14\u95f8\u6253\u5f00\uff0c\u4f60\u8fdb\u5165\u8231\u5185\u3002'
    assert reflow_translation('\u6c14\u95f8\u6253\u5f00\u3002\n\n\u68c0\u67e5\u8bbe\u5907\u3002') == '\u6c14\u95f8\u6253\u5f00\u3002\n\n\u68c0\u67e5\u8bbe\u5907\u3002'
    core=OcrCore()
    assert hasattr(core.native._dll, 'gl_overlay_fixed')
    assert hasattr(core.native._dll,'gl_overlay_styled') and core.native.font_supports('Arial','Welcome')
    plan=capture_plan([(0,0,20,20),(40,0,20,20)])
    assert plan.bounds==(0,0,60,20) and len(plan.regions)==2
    with Image.new('RGB',(60,20),'white') as sample,mask_regions(sample,plan.regions) as masked:
        assert masked.getpixel((30,10))==(0,0,0) and masked.getpixel((10,10))==(255,255,255)
    core.set_overlay_font('SimSun')
    core.set_overlay_font('Microsoft YaHei UI')
    image=Image.new('RGB',(960,250),'white')
    font_path=next(p for p in [Path('C:/Windows/Fonts/msgothic.ttc'),Path('C:/Windows/Fonts/msyh.ttc')] if p.exists())
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(str(font_path),38)
    draw.text((32,30),'\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002',font=font,fill='black')
    draw.text((32,110),'\u30b2\u30fc\u30e0\u3092\u958b\u59cb\u3059\u308b',font=font,fill='black')
    result=core.portable.recognize(image)
    assert any('\u7d05\u9b54\u9928' in line['text'] for line in result['lines']),result
    tracker=ObjectTracker(workers=2)
    try:
        boxes=[{'text':'Start','x':10,'y':20,'w':100,'h':30},
               {'text':'Settings','x':210,'y':20,'w':100,'h':30}]
        first=tracker.update(boxes)
        view=OverlayState()
        view.apply_objects([{'track_id':t.track_id,'revision':t.revision,'line':dict(t.line)} for t in first.tracks])
        identity=first.tracks[0].track_id
        view.apply_translation(identity,{'text':ui_source('Start'),'final':True,'_revision':1})
        moved=tracker.update([{**box,'x':box['x']+15} for box in reversed(boxes)])
        assert {t.track_id for t in first.tracks}=={t.track_id for t in moved.tracks}
        view.apply_objects([{'track_id':t.track_id,'revision':t.revision,'line':dict(t.line)} for t in moved.tracks])
        assert view.rendered[identity]['x']==25
        assert not view.apply_translation(identity,{'text':'\u8fc7\u671f\u7ed3\u679c','final':True,'_revision':0})
        rejected={'text':'Neu or Id gane?','x':25,'y':20,'w':240,'h':30,'_preserve_source':True}
        view.apply_objects([{'track_id':identity,'revision':2,'line':rejected}])
        assert not view.rendered
        assert not view.apply_translation(identity,{'text':'\u9519\u8bef\u8bd1\u6587','final':True,'_revision':2})
    finally:
        tracker.close()
    with tempfile.TemporaryDirectory(prefix='ersedie-selfcheck-') as folder:
        offline=TranslationEngine({'api_key':'','offline_only':True},Path(folder)/'codebook.sqlite3')
        try:
            offline.set_term('selfcheck','en','zh-Hans','Start',ui_source('Start'))
            offline.remember_profile('Saved Game')
            assert set(offline.list_profiles())=={'selfcheck','Saved Game'}
            saved_profile=offline.save_profile('Saved Game',notes='The crew are merchants.',source_lang='en',target_lang='zh-Hans')
            assert saved_profile['notes']=='The crew are merchants.'
            assert offline.get_profile('Saved Game')['source_lang']=='en'
            assert offline.delete_profile('Saved Game')
            assert offline.get_profile('Saved Game') is None
            for original in ('Start','Unknown text'):
                try:
                    offline.translate('selfcheck','en','zh-Hans',original)
                except TranslationError:
                    pass
                else:
                    raise AssertionError('AI-only mode must not serve local translations without API')
            assert offline.get_stats()['session_requests']==0
            sample=Path(folder)/'dictionary.csv'
            sample.write_text('source,target\nSettings,\u8bbe\u7f6e\nHP {n},\u751f\u547d {n}\n',encoding='utf-8')
            entries=parse_dictionary(sample,'en','zh-Hans')
            assert offline.import_terms(entries,'','en','zh-Hans',shared=True)['inserted']==2
        finally:
            offline.close()
    assert len(app.tabs.tabs())==5
    assert app.settings_panel.vars['translation_workers'].get() in (8,'8')
    assert 'aggressive_mode' not in app.settings_panel.vars
    assert 'expert_enabled' not in app.settings_panel.vars
    assert not app.agreement_accepted
    assert app.api_dialog is None
    assert app.setup_dialog is None
    assert app.settings_panel.vars['overlay_font_family'].get() == 'SimSun'
    assert app.settings_panel.vars['show_source_label'].get()
    assert app.settings_panel.vars['source_label_mixed_only'].get()
    assert not app.settings_panel.vars['show_translation_brackets'].get()
    assert app.settings_panel.vars['ocr_refine_workers'].get() in (4,'4')
    assert app.settings_panel.vars['capture_interval_ms'].get() in (200,'200')
    before_settle=app.settings_panel.vars['settle_ms'].get()
    app.settings_panel.apply_performance_preset('balanced')
    assert app.settings_panel.vars['settle_ms'].get()==before_settle  # Consent gate remains closed.
    assert validate_tuning(PERFORMANCE_PRESETS['balanced'])['settle_ms']==450
    assert validate_tuning(PERFORMANCE_PRESETS['responsive'])['translation_workers']==8
    assert app.settings_panel.vars['translation_workers'].get() in (8,'8')
    assert app.settings_panel.vars['context_max_chars'].get() in (16384,'16384')
    assert app.settings_panel.values()['vision_ocr_mode'] in ('off','force')
    assert app.settings_panel.vars['unlimited_requests'].get()
    assert app.settings_panel.vars['capture_translations'].get()
    assert app.settings_panel.vars['auto_font_size'].get()
    assert validate_tuning({'overlay_font_min':12,'overlay_font_max':48})['overlay_font_max']==48
    core.set_overlay_options(auto_font_size=False,overlay_font_size=24,capture_translations=False)
    with tempfile.TemporaryDirectory(prefix='nishokuchou-unlimited-selfcheck-') as folder:
        settings_store=ConfigStore(Path(folder))
        settings_store.save({**validate_tuning({'unlimited_requests':True,'max_requests':20}),'offline_only':True})
        saved=settings_store.load()
        assert saved['unlimited_requests'] is True and saved['max_requests']==20
        assert not settings_store.credentials_path.exists()
    assert warmup_identity('',r'C:\Games\Example.exe') == warmup_identity('',r'c:\games\EXAMPLE.exe')
    anchor={'text':'helo','x':3,'y':4,'w':70,'h':20}
    corrected=parse_transcription('{"lines":[{"id":0,"text":"hello"}]}',[anchor])
    assert corrected==[{**anchor,'text':'hello'}] and anchor['text']=='helo'
    assert label_translation(ui_source('Welcome'), 'en', show_source_label=False, show_translation_brackets=False) == ui_source('Welcome')
    assert label_translation(ui_source('Welcome'), 'en', final=False) == '[\u82f1\u8bed\uff1a\u6b22\u8fce'
    assert detect_system_language(0x0411) == 'ja'
    assert detect_system_language(0x0409) == 'en'
    assert detect_system_language(0x0804) == 'zh-CN'
    engine = app.engine
    for code in ('en', 'ja', 'zh-CN'):
        app.apply_ui_language(code)
        assert app.engine is engine
        assert app.agreement_text.get('1.0', 'end-1c') == agreement_text(code)
    assert str(app.start_button['state'])=='disabled'
    assert Path(app.window_icon_path).name=='taiji.ico'
    assert all(window_icon_handles(app.root).values())
    assert app.start_button['text']==ui_source('Start translation')
    assert app.api_settings_button['text']==ui_source('API connections (3 slots)')
    assert app.api_settings_button['style']=='Accent.TButton'
    ancestor=app.api_settings_button.master
    ancestors=[]
    while ancestor is not None:
        ancestors.append(ancestor)
        ancestor=getattr(ancestor,'master',None)
    assert app.settings_tab in ancestors
    assert app.start_button.master is app.run_action_bar
    assert app.settings_panel.vars['retranslate_hotkey'].get()=='Ctrl+Alt+R'
    assert 'Ctrl+Alt+R' in app.hotkey_hint.get() and not hasattr(app,'retranslate_button')
    assert callable(app_module.Pipeline.request_retranslation)
    assert app.config['active_api_slot']==0
    assert len(app.config['api_slots'])==3
    assert all('api_key' not in slot and not slot['has_api_key'] for slot in app.config['api_slots'])
    app.game.set('')
    assert app.term_scope()[0]==''
    report={'ok':True,'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
            'multiple_capture_regions':True,'selection_gap_masking':True,'native_styled_font_export':True,
            'installed_font_coverage_check':True,
            'app_title':app.root.title(),'tab_labels':[app.tabs.tab(tab,'text') for tab in app.tabs.tabs()],
            'ui_pages':len(app.tabs.tabs()),'languages':core.languages(),
            'overlay_only':True,'japanese_ocr':result,
            'multiobject_tracking':True,'translation_follows_position':True,
            'stale_result_rejected':True,'ai_only_no_local_translation':True,'missing_api_preserves_source':True,
            'optional_game_profile':True,'profile_list':True,'taiji_window_icon':True,
            'plain_start_label':True,'agreement_not_autoaccepted':True,
            'prominent_api_entry':True,'api_entry_location':'settings','api_slots':3,'active_api_slot':0,
            'consent_gates_settings':True,'persistent_profile_crud':True,'fixed_start_action_bar':True,
            'configurable_retranslation_shortcut':True,'shortcut_hint_without_button':True,
            'settings_page':True,'dictionary_import':True,'shared_dictionary':True,
            'local_expert_removed':True,'context_budget_settings':True,
            'custom_overlay_font':True,'optional_source_labels':True,
            'native_overlay_options_export':True,'font_size_range_settings':True,'screenshot_inclusion_setting':True,
            'mixed_language_label_option':True,'optional_translation_brackets':True,
            'interface_languages':['zh-CN','en','ja'],'language_switch_preserves_engine':True,
            'ai_only_default':True,'ocr_refine_workers':4,'response_presets':True,'vision_default_off':True,'vision_anchor_geometry_preserved':True,
            'unlimited_requests_default':True,'unlimited_requests_persists':True,
            'suspect_ocr_preserves_game_pixels':True,'suspect_ocr_late_overlay_rejected':True,
            'narrative_reflow_preserves_dictionary_key':True,'explicit_paragraph_breaks_preserved':True,
            'nonmeaningful_hud_keeps_original':True,'glyph_noise_keeps_original':True,
            'unchanged_translation_detected':True,
            'fixed_source_rows':True,'native_fixed_layout_export':True,
            'stable_game_learning_identity':True,'fixed_frame_native_ocr':True,
            'network_requests':0,'dialogs':0}
    core.close()
    (ROOT/'selftest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


