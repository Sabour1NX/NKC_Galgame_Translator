"""Compare CUDA on/off through the same uncached local OCR caller."""
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import subprocess
import sys
import winreg
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from nkc_galgame_translator import __version__
from nkc_galgame_translator.ocr import OcrCore
from benchmark_cuda27 import accuracy


def main():
    baseline = Path(sys.argv[1])
    cases = json.loads((baseline/'accuracy-truth.json').read_text(encoding='utf-8'))
    needy = json.loads((baseline/'needy-local25.json').read_text(encoding='utf-8'))
    cases['needy-caution-full.png'] = needy['scenes']['needy-caution-full.png']['accuracy']
    records = []
    rounds = 7
    for name, truth in cases.items():
        path = baseline/'ocr-private'/name
        language = 'ja' if name.startswith('needy') else 'en'
        row = {'scene': name, 'language': language, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        with Image.open(path) as source, source.convert('RGB') as image:
            row['size'] = image.size
            for enabled in (False, True):
                key = 'cuda_on' if enabled else 'cuda_off'
                with OcrCore(cuda_enabled=enabled, cuda_memory_mb=1024, cuda_quality=75) as ocr:
                    samples = []
                    for _ in range(rounds+1):
                        ocr._frames.clear()
                        began = perf_counter()
                        result = ocr.recognize_image(image, language)
                        samples.append(1000*(perf_counter()-began))
                        assert not result['frame_cache_hit']
                    score = accuracy(result['lines'], truth)
                    row[key] = {'engine': result.get('engine'), 'cuda_status': result.get('cuda_status'),
                                'first_ms': samples[0], 'warm_ms': samples[1:],
                                'median_ms': median(samples[1:]), 'characters': score['characters'],
                                'edits': score['edits'], 'accuracy_percent': score['character_accuracy_percent']}
                print(name, key, row[key], flush=True)
        records.append(row)
    gpu = subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'], text=True).strip()
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
        cpu = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    report = {'version':__version__, 'platform':platform.platform(), 'gpu':gpu, 'cpu':cpu,
              'warm_rounds':rounds, 'cuda_budget_mib':1024, 'cuda_quality':75,
              'scope':'Uncached local OCR including caller/IPC/refinement; no capture, translation, network, or overlay.',
              'scenes':records}
    (ROOT/'reports/cuda-comparison30.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()

