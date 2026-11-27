# SPDX-License-Identifier: MIT
"""Own-process real Tk UI fixture for externally captured teacher-review images.

No game/window enumeration, API construction, real credentials, or user history.
The stdin command 'next' advances one explicit surface; screenshots are captured
through the computer-use window capture API, never synthesized by this fixture.
"""
from pathlib import Path
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
import json
import queue
import shutil
import sys
import tempfile
import threading
import tkinter as tk

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from nkc_galgame_translator import app as module
from nkc_galgame_translator.agreement import AGREEMENT_VERSION


def main():
    commands=queue.Queue()
    def reader():
        for line in sys.stdin:commands.put(line.strip())
    threading.Thread(target=reader,daemon=True).start()
    fixture=tempfile.TemporaryDirectory(prefix='nkc-teacher-ui-')
    root=Path(fixture.name)
    shutil.copytree(ROOT/'assets',root/'assets')
    (root/'config').mkdir()
    config=json.loads((ROOT/'config/example.json').read_text(encoding='utf-8-sig'))
    config.update(api_key='',game='TeacherReview',app_language='zh-CN',app_language_selected=True,
                  api_setup_complete=True,agreement_version=AGREEMENT_VERSION,
                  agreement_accepted_at='2026-11-18T00:00:00Z',base_url='https://api.example.test/v1',
                  model='review-model',cuda_enabled=False,source_lang='ja',target_lang='zh-Hans')
    config.pop('api_slots',None)
    (root/'config/example.json').write_text(json.dumps(config),encoding='utf-8')
    stack=ExitStack()
    def forbidden(*args,**kwargs):raise AssertionError('Teacher UI fixture blocks network/client construction')
    stack.enter_context(patch.object(module,'ROOT',root))
    stack.enter_context(patch.object(module,'window_list',lambda:[]))
    stack.enter_context(patch.object(httpx,'Client',forbidden))
    stack.enter_context(patch.object(httpx,'AsyncClient',forbidden))
    stack.enter_context(patch.object(tk.Misc,'grab_set',lambda self:None))
    stack.enter_context(patch.object(tk.Misc,'focus_force',lambda self:None))
    app=module.App(show_setup=False)
    real_title=app.root.title
    def review_title(value=None):
        return real_title() if value is None else real_title(value.split(' · Teacher UI Review')[0]+' · Teacher UI Review')
    app.root.title=review_title
    app.root.geometry('980x820+60+35')
    app.windows_box.configure(values=())
    app.status.set(app.tr('\u5c31\u7eea · \u5c4f\u5e55\u8986\u76d6\u7ffb\u8bd1'))
    active=[app.root];extras=[];plan=[]
    def add(surface,title,action,language='zh-CN',limitations=None):
        plan.append({'surface':surface,'title':title,'language':language,
                     'action':action,'limitations':limitations or []})
    def clean():
        for dialog in (app.api_dialog,app.language_dialog,app.import_dialog):
            if dialog is not None:dialog.close()
        for window in extras:
            if window.winfo_exists():window.destroy()
        extras.clear();active[0]=app.root
        app.root.deiconify()
    def language(code):
        clean();app.apply_ui_language(code)
        app.root.title(module.BRAND+' 0.01.27 · Teacher UI Review')
    def tab(index):
        clean();app.tabs.select(index)
        if index==0:app.run_canvas.yview_moveto(0)
        if index==3:app.agreement_text.yview_moveto(0)
        if index==4:app.settings_canvas.yview_moveto(0)
    def settings_position(fraction):
        tab(4);app.settings_canvas.yview_moveto(fraction)
    def api(index=0,saved=False,endpoint_changed=False):
        clean();app.agreement_accepted=True
        app.config['active_api_slot']=0
        for slot in app.config['api_slots']:slot['has_api_key']=False
        app.config['api_slots'][0]['has_api_key']=saved
        dialog=app.show_api_settings();dialog.select_slot(index)
        if endpoint_changed:dialog.base_url.set('https://other.example.test/v1')
        dialog.window.geometry('700x720+180+70')
        active[0]=dialog.window
    def first_run():
        clean();dialog=app.show_language_setup()
        dialog.window.geometry('720x650+180+80');active[0]=dialog.window
    def import_dialog():
        clean();dialog=app.open_dictionary_import()
        dialog.window.geometry('820x700+120+55');active[0]=dialog.window
    def history():
        clean()
        class HistoryFixture:
            def list_translation_history(self,*args,**kwargs):
                return [{'created_at':'2026-11-18 12:00:00','source':'Welcome to the game.',
                         'translation':'\u6b22\u8fce\u6765\u5230\u6e38\u620f\u3002','context':'Demonstration record; not an API result.'}]
            def get_context_status(self,*args,**kwargs):
                return {'updated_at':'2026-11-18 12:00:00','directory':'data/contexts/TeacherReview'}
        with patch.object(app,'get_engine',lambda:HistoryFixture()):window=app.open_translation_history()
        extras.append(window);window.geometry('850x600+130+90');active[0]=window
    def agreement_end():
        tab(3);app.agreement_text.yview_moveto(1)
    def selection():
        clean()
        backdrop=tk.Toplevel(app.root);backdrop.title('Teacher UI Review · Synthetic selection target')
        backdrop.geometry('980x720+60+35');backdrop.configure(background='#e7e9ef')
        tk.Label(backdrop,text='Synthetic selection target · no game or desktop image',
                 background='#e7e9ef',font=('Segoe UI',15)).pack(pady=130)
        backdrop.update();extras.append(backdrop)
        box=(backdrop.winfo_rootx(),backdrop.winfo_rooty(),980,720)
        target={'hwnd':backdrop.winfo_id(),'pid':0}
        with patch.object(app,'chosen_window',lambda:target),patch.object(module,'virtual_screen',lambda:box),patch.object(module,'client_rect',lambda hwnd:box):
            app.select_region();top=app.root.winfo_children()[-1]
            canvas=next(w for w in top.winfo_children() if isinstance(w,tk.Canvas))
            top.update()
            for x,y,w,h in ((70,200,340,160),(500,420,350,170)):
                for event,px,py in (('<Button-1>',x,y),('<B1-Motion>',x+w,y+h),('<ButtonRelease-1>',x+w,y+h)):
                    canvas.event_generate(event,x=px,y=py)
                top.update()
            # Keep the real picker controls; only its synthetic target bounds differ.
            top.title('Teacher UI Review · Multiple regions')
            extras.append(top);active[0]=top
    # Each language gets every main page plus the two major setup surfaces.
    for code in ('zh-CN','en','ja'):
        add(code+'-main-screen','Screen translation',lambda c=code:(language(c),tab(0)),code)
        add(code+'-main-dictionary','Glossary',lambda:tab(1),code)
        add(code+'-main-text','Translate text manually',lambda:tab(2),code)
        add(code+'-agreement-top','User agreement / disclaimer',lambda:tab(3),code)
        add(code+'-settings-top','Settings / font appearance',lambda:tab(4),code)
        if code=='zh-CN':
            # Overlapping viewports cover the entire long settings page.
            for index,fraction in enumerate((.15,.30,.45,.60,.75,1.0),1):
                add(f'zh-CN-settings-scroll-{index}',f'Settings continuous viewport {index}',lambda f=fraction:settings_position(f))
            add('zh-CN-agreement-license-end','MIT agreement ending',agreement_end)
            add('zh-CN-api-slot-1-empty','API configuration / slot 1 empty',lambda:api(0))
            add('zh-CN-api-slot-2-empty','API configuration / slot 2 empty',lambda:api(1))
            add('zh-CN-api-slot-3-empty','API configuration / slot 3 empty',lambda:api(2))
            add('zh-CN-api-saved-placeholder','Saved-key placeholder',lambda:api(0,True),limitations=['Synthetic has_api_key state only; no key exists or is displayed.'])
            add('zh-CN-api-endpoint-changed','Changed endpoint requires new key',lambda:api(0,True,True),limitations=['Synthetic configured-state fixture; no API request.'])
            add('zh-CN-dictionary-import','Dictionary import dialog',import_dialog)
            add('zh-CN-history','Translation/context history dialog',history,limitations=['One synthetic example record; no private history or API result.'])
            add('zh-CN-region-multiple','Multiple region selection (two regions)',selection,limitations=['Actual selector over an owned synthetic target, no game/desktop capture; event-generated test selections.'])
        else:
            add(code+'-settings-cuda','CUDA and OCR settings',lambda:settings_position(.30),code)
            add(code+'-settings-bottom','Settings final controls',lambda:settings_position(1),code)
            add(code+'-api','API configuration',lambda:api(0,True),code,['Synthetic has_api_key state; no key exists.'])
        add(code+'-first-language-cuda','First-run language and CUDA controls',first_run,code,
            ['Dialog invoked directly by isolated test fixture; no preference or consent is saved.'])
    index=[-1]
    def advance():
        index[0]+=1
        if index[0]>=len(plan):
            print(json.dumps({'done':True,'surfaces':len(plan)}),flush=True);app.close();return
        item=plan[index[0]]
        item['action']();app.root.update_idletasks()
        window=active[0]
        app.root.after(300,lambda:print(json.dumps({**{k:v for k,v in item.items() if k!='action'},
            'index':index[0],'total':len(plan),'title_match':window.title(),'tk_id':window.winfo_id(),
            'client_size':[window.winfo_width(),window.winfo_height()],
            'settings_yview':list(app.settings_canvas.yview()) if 'settings' in item['surface'] else None},ensure_ascii=False),flush=True))
    def poll():
        try:command=commands.get_nowait()
        except queue.Empty:command=''
        if command=='next':advance()
        elif command=='quit':app.close();return
        if not app._closing:app.root.after(60,poll)
    app.root.after(300,advance);app.root.after(60,poll)
    try:app.run()
    finally:stack.close();fixture.cleanup()


if __name__=='__main__':main()
