# SPDX-License-Identifier: MIT
"""Record actual Tk UI with explicitly simulated AI SSE, never using network.

No external input injection, game capture, real credential/consent access, email
or shutdown action. Use --frames-only to validate scenes without an encoder, or
--ffmpeg PATH for MP4 encoding with a local FFmpeg supporting h264_mf.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nkc_galgame_translator import __version__
from nkc_galgame_translator import app as app_module
from nkc_galgame_translator.agreement import AGREEMENT_VERSION
from nkc_galgame_translator.config_store import ConfigStore
from ui_snapshot import print_own_window, user32

FPS=8
SIZE=(1024,920)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    output_mode=parser.add_mutually_exclusive_group(required=True)
    output_mode.add_argument('--ffmpeg',type=Path)
    output_mode.add_argument('--frames-only',action='store_true',
                             help='Validate UI and write PNG frames/JSON; no video encoding')
    args=parser.parse_args()
    encoder=args.ffmpeg.resolve(strict=True) if args.ffmpeg else None
    reports=ROOT/'reports';reports.mkdir(exist_ok=True)
    build=(ROOT/'build').resolve();build.mkdir(exist_ok=True)
    frames=build/'public-demo-frames';frames.mkdir(exist_ok=True)
    assert frames.resolve().parent==build
    # Only known frame files created by this tool are replaced, never recurse.
    for old in frames.glob('frame-*.png'):old.unlink()
    foreground_before=user32.GetForegroundWindow()
    focus_observations=[]
    root_factory,top_factory=tk.Tk,tk.Toplevel
    grab_factory=tk.Misc.grab_set
    client_factory,async_factory=httpx.Client,httpx.AsyncClient
    actual_root=app_module.ROOT
    window_provider=app_module.window_list
    old_cwd=Path.cwd()
    network_attempts=[]
    simulated_requests=[]
    app=None

    def no_network(*args,**kwargs):
        network_attempts.append(True)
        raise RuntimeError('Demonstration blocks non-mocked HTTP clients')

    class SimulatedStream(httpx.SyncByteStream):
        def __iter__(self):
            for chunk in ('\u8fd9\u662f','\u4e00\u6bb5','\u6a21\u62df AI ','\u54cd\u5e94\uff0c','\u7528\u4e8e','\u6f14\u793a','\u6d41\u5f0f','\u7ffb\u8bd1','\u754c\u9762\u3002'):
                time.sleep(.18)
                event={'choices':[{'delta':{'content':chunk},'finish_reason':None}]}
                yield ('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode('utf-8')
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b'data: [DONE]\n\n'

    def responder(request):
        if request.url.host!='example.invalid' or request.method!='POST':
            raise AssertionError('Demo accepts only its synthetic endpoint')
        payload=json.loads(request.content)
        assert payload['stream'] is True and payload['model']=='simulated-ai'
        simulated_requests.append({'method':request.method,'path':request.url.path})
        return httpx.Response(200,stream=SimulatedStream(),
                              headers={'Content-Type':'text/event-stream'})

    def mock_client(*args,**kwargs):
        if kwargs.get('transport') is not None:
            raise AssertionError('Unexpected demo HTTP transport')
        kwargs.update(transport=httpx.MockTransport(responder),trust_env=False)
        return client_factory(*args,**kwargs)

    def hide_before_map(factory):
        def create(*args,**kwargs):
            window=factory(*args,**kwargs);window.withdraw()
            hwnd=user32.GetAncestor(window.winfo_id(),2)
            style=user32.GetWindowLongPtrW(hwnd,-20)
            user32.SetWindowLongPtrW(hwnd,-20,style|0x08000000) # WS_EX_NOACTIVATE
            return window
        return create

    def check_focus(stage):
        current=user32.GetForegroundWindow()
        if current!=foreground_before:
            pid=W.DWORD();user32.GetWindowThreadProcessId(current,C.byref(pid))
            if pid.value!=os.getpid():
                raise RuntimeError('External foreground changed during demo; recording stopped')
            observation={'stage':stage,'own_process':True}
            if observation not in focus_observations:focus_observations.append(observation)

    @contextmanager
    def temporary_fixture():
        nonlocal app
        with tempfile.TemporaryDirectory(prefix='public-demo-',dir=build) as temporary:
            try:
                yield temporary
            finally:
                if app:app.close();app=None
                # Windows cannot remove the process's current working directory.
                os.chdir(old_cwd)

    def show(window):
        app.root.update_idletasks()
        hwnd=user32.GetAncestor(window.winfo_id(),2)
        style=user32.GetWindowLongPtrW(hwnd,-20)
        user32.SetWindowLongPtrW(hwnd,-20,style|0x08000000)
        user32.ShowWindow(hwnd,4) # SW_SHOWNOACTIVATE, never SetForegroundWindow
        app.root.update();user32.UpdateWindow(hwnd)
        check_focus('show')
        return hwnd

    def pump_until(predicate):
        deadline=time.monotonic()+8
        while not predicate():
            app.root.update();check_focus('background operation')
            if time.monotonic()>deadline:raise RuntimeError('Demo operation did not finish')
            time.sleep(.01)

    title_font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',21)
    caption_font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    samples=[];scenes=[];frame_count=0

    def hold(label,seconds,window=None):
        nonlocal frame_count
        target=window or app.root;hwnd=show(target)
        start_frame=frame_count;begin=time.monotonic()
        count=round(seconds*FPS)
        for offset in range(count):
            app.root.update();user32.UpdateWindow(hwnd);check_focus(label)
            shot=print_own_window(hwnd)
            shot.thumbnail((1000,790),Image.Resampling.LANCZOS)
            canvas=Image.new('RGB',SIZE,'#F7F3EE');draw=ImageDraw.Draw(canvas)
            draw.rectangle((0,0,SIZE[0],4),fill='#B6332D')
            draw.text((22,14),f'\u4e8c\u8272\u8776 · \u6e38\u620f\u5b9e\u65f6\u7ffb\u8bd1  {__version__}',font=title_font,fill='#302E2B')
            canvas.paste(shot,((SIZE[0]-shot.width)//2,50+(790-shot.height)//2))
            draw.rectangle((0,850,SIZE[0],920),fill='#F5E8E0')
            draw.text((22,858),'\u771f\u5b9e\u754c\u9762 · \u6a21\u62df AI \u6d41\u5f0f\u54cd\u5e94 · \u96f6\u7f51\u7edc',font=caption_font,fill='#B6332D')
            draw.text((22,888),label,font=caption_font,fill='#302E2B')
            canvas.save(frames/f'frame-{frame_count:04d}.png')
            if offset==count//2:samples.append(canvas.copy())
            frame_count+=1
            delay=begin+(offset+1)/FPS-time.monotonic()
            if delay>0:time.sleep(delay)
        scenes.append({'caption':label,'start_seconds':start_frame/FPS,'duration_seconds':count/FPS,
                       'capture':'PrintWindow of actual application-owned HWND'})

    try:
        httpx.Client=mock_client;httpx.AsyncClient=no_network
        tk.Tk=hide_before_map(root_factory);tk.Toplevel=hide_before_map(top_factory)
        tk.Misc.grab_set=lambda self:None  # The isolated fixture must never capture input.
        with temporary_fixture() as temporary:
            fixture=Path(temporary).resolve();assert fixture.parent==build
            shutil.copytree(ROOT/'assets',fixture/'assets')
            (fixture/'config').mkdir()
            (fixture/'config/example.json').write_text('{}',encoding='utf-8')
            ConfigStore(fixture).save({'offline_only':False,'api_setup_complete':True,
                'base_url':'https://example.invalid/v1','model':'simulated-ai',
                'app_language':'zh-CN','app_language_selected':True,
                'max_requests':2,'unlimited_requests':False,'context_web_search':False,'vision_ocr_mode':'off',
                'agreement_version':AGREEMENT_VERSION,'agreement_accepted_at':'2000-01-01T00:00:00+00:00'},
                api_key='synthetic-demo-key-not-a-real-credential')
            os.chdir(fixture)
            app_module.ROOT=fixture;app_module.window_list=lambda:[]
            app=app_module.App(show_setup=False)
            app.root.geometry('980x760')
            app.source.set('\u82f1\u8bed');app.target.set('\u7b80\u4f53\u4e2d\u6587');app.game.set('\u754c\u9762\u6f14\u793a')
            app.status.set('\u754c\u9762\u6d41\u7a0b\u6f14\u793a · \u6a21\u62df AI \u670d\u52a1 · \u672a\u8fde\u63a5\u6e38\u620f · \u96f6\u7f51\u7edc')
            hold('\u8fd9\u662f\u754c\u9762\u6d41\u7a0b\u793a\u8303\uff1b\u6ca1\u6709\u8fde\u63a5\u6e38\u620f\u6216\u771f\u5b9e AI \u670d\u52a1',2)

            dialog=app.show_api_settings()
            hold('\u4e09\u4e2a API \u69fd\u4f4d\uff1b\u8fd9\u91cc\u4f7f\u7528\u4e34\u65f6\u5047\u5bc6\u94a5\u4e0e\u6a21\u62df\u7aef\u70b9',2,dialog.window)
            dialog.close()
            app.tabs.select(app.agreement_tab)
            hold('\u514d\u8d23\u58f0\u660e\u4e0e MIT\uff1b\u6f14\u793a\u540c\u610f\u8bb0\u5f55\u4ec5\u5b58\u5728\u4e8e\u4e34\u65f6\u76ee\u5f55',2)

            app.tabs.select(app.settings_tab);app.settings_canvas.yview_moveto(0)
            app.settings_panel.vars['translation_workers'].set('8')
            assert app.save_settings()
            assert app.config['max_concurrency']==8
            hold('\u5b57\u53f7\u8303\u56f4\u3001\u7ffb\u8bd1\u5e76\u53d1\u548c AI \u8bed\u5883\u9884\u7b97\u53ef\u4ee5\u5728\u8bbe\u7f6e\u4e2d\u8c03\u6574',2)

            app.tabs.select(2)
            app.manual_input.insert('1.0','This simulated AI response demonstrates the streaming translation interface.')
            app.manual_translate()
            assert app.manual_busy
            hold('\u6a21\u62df SSE \u6b63\u5728\u9010\u6bb5\u8fd4\u56de\uff1b\u8fd9\u4e0d\u662f\u5b9e\u9645\u7ffb\u8bd1\u8d28\u91cf\u6216\u901f\u5ea6\u6d4b\u91cf',3)
            pump_until(lambda:not app.manual_busy)
            assert app.manual_output.get('1.0','end').strip()=='\u8fd9\u662f\u4e00\u6bb5\u6a21\u62df AI \u54cd\u5e94\uff0c\u7528\u4e8e\u6f14\u793a\u6d41\u5f0f\u7ffb\u8bd1\u754c\u9762\u3002'
            hold('\u6a21\u62df\u54cd\u5e94\u5b8c\u6210\uff1b\u771f\u5b9e\u4ea7\u54c1\u9700\u8981\u914d\u7f6e\u81ea\u5df1\u7684 API \u670d\u52a1',2)
            app.tabs.select(0);app.status.set('\u754c\u9762\u6f14\u793a\u7ed3\u675f · \u6a21\u62df\u8bf7\u6c42 1 · \u5b9e\u9645\u7f51\u7edc\u8bf7\u6c42 0')
            hold('\u624b\u518c\u53e6\u9644\u771f\u5b9e\u6e38\u620f\u622a\u56fe\uff1b\u672c\u6f14\u793a\u53ea\u5c55\u793a\u754c\u9762\u64cd\u4f5c\u6d41\u7a0b',2)
            assert not network_attempts
            stats=app.get_engine().get_stats()
            assert stats['session_requests']==len(simulated_requests)==1
            user32.ShowWindow(user32.GetAncestor(app.root.winfo_id(),2),0)
            app.close();app=None
    finally:
        if app:app.close()
        os.chdir(old_cwd)
        tk.Tk=root_factory;tk.Toplevel=top_factory
        tk.Misc.grab_set=grab_factory
        httpx.Client=client_factory;httpx.AsyncClient=async_factory
        app_module.ROOT=actual_root;app_module.window_list=window_provider
    check_focus('finished')
    output=reports/'public-demo.mp4' if encoder else None
    if encoder:
        command=[str(encoder),'-hide_banner','-loglevel','error','-y','-framerate',str(FPS),
            '-i',str(frames/'frame-%04d.png'),'-an','-c:v','h264_mf','-b:v','550k',
            '-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
        encoded=subprocess.run(command,capture_output=True,timeout=90)
        if encoded.returncode:raise RuntimeError('FFmpeg encode failed; inspect local encoder configuration')
        if output.stat().st_size>=2_200_000:
            command[command.index('550k')]='380k'
            encoded=subprocess.run(command,capture_output=True,timeout=90)
            if encoded.returncode:raise RuntimeError('FFmpeg size-constrained encode failed')
        assert output.stat().st_size<2_200_000
        # Verify every actual encoded frame, not only file existence.
        probe=subprocess.run([str(encoder),'-hide_banner','-i',str(output),'-f','null','-'],capture_output=True,
                             encoding='utf-8',errors='replace',timeout=60)
        assert probe.returncode==0,'Encoded MP4 failed full decode'
        (reports/'public-demo-decode.txt').write_text(probe.stderr,encoding='utf-8')
    thumbs=[]
    for shot in samples:
        shot.thumbnail((512,460),Image.Resampling.LANCZOS);thumbs.append(shot)
    board=Image.new('RGB',(512*2,460*((len(thumbs)+1)//2)),'#F7F3EE')
    for i,shot in enumerate(thumbs):board.paste(shot,((i%2)*512,(i//2)*460))
    board.save(reports/'storyboard.png')
    record={'version':__version__,'created_utc':datetime.now(timezone.utc).isoformat(),
        'video':'public-demo.mp4' if encoder else None,'codec':'h264_mf' if encoder else None,
        'frames_only':bool(args.frames_only),'fps':FPS,'frames':frame_count,'duration_seconds':frame_count/FPS,
        'size':list(SIZE),'bytes':output.stat().st_size if output else 0,
        'sha256':hashlib.sha256(output.read_bytes()).hexdigest() if output else None,
        'scenes':scenes,'actual_application_ui':True,'simulated_ai_sse':True,
        'simulated_requests':len(simulated_requests),'production_translation_route':'AI',
        'fixture_consent_only':True,'real_credentials_read':False,'network_requests':0,'network_attempts':0,
        'game_capture':False,'game_memory_access':False,'external_input_injection':False,
        'foreground_unchanged':not focus_observations,'explicit_activation_calls':0,
        'own_window_focus_observations':focus_observations,'full_video_decode_ok':True if encoder else None,
        'note':'Actual application UI with clearly labelled MockTransport AI SSE. No network, real LLM, or game translation; timing is scripted and is not a performance result. Frames-only mode creates no video.'}
    (reports/'public-demo.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('video','frames','duration_seconds','bytes','foreground_unchanged','network_requests')},ensure_ascii=False))


if __name__=='__main__':main()
