# SPDX-License-Identifier: MIT
"""Shared UI parameter ranges and strict validation; no I/O or credentials."""

from .i18n import ui_source
import re
import unicodedata
from .hotkeys import DEFAULT_HOTKEY, DEFAULT_TOGGLE_HOTKEY, HotkeyValidationError, normalize_hotkey

DEFAULT_OVERLAY_FONT = 'Microsoft YaHei UI'
DEFAULT_TRANSLATION_HOLD_MS = 250
DEFAULT_SCENE_CHANGE_SENSITIVITY = 70
APP_LANGUAGES = ('zh-CN', 'en', 'ja')
APPEARANCE_FIELDS = {'overlay_font_family', 'show_source_label', 'show_translation_brackets',
                     'source_label_mixed_only', 'app_language', 'capture_translations',
                     'auto_font_size', 'auto_font_style', 'overlay_font_size', 'overlay_font_min', 'overlay_font_max',
                     'retranslate_hotkey_enabled', 'retranslate_hotkey',
                     'toggle_hotkey_enabled','toggle_hotkey','translation_hold_ms','scene_change_sensitivity'}

class TuningValidationError(ValueError):
    """A controlled, non-sensitive settings diagnostic."""


NUMERIC_FIELDS = {
    'cuda_quality': (ui_source('OCR quality'), 0, 100, 75),
    'cuda_memory_mb': (ui_source('GPU memory budget (MiB)'), 256, 16384, 1024),
    'overlay_font_size': (ui_source('Fixed font size (pixels)'), 8, 512, 24),
    'overlay_font_min': (ui_source('Minimum automatic size (pixels)'), 8, 512, 8),
    'overlay_font_max': (ui_source('Maximum automatic size (pixels)'), 8, 512, 72),
    'context_max_chars': (ui_source('Translation context length (characters)'), 512, 16384, 16384),
    'context_history_records': (ui_source('Translations to keep before summarizing'), 1, 2, 2),
    'ocr_refine_workers': (ui_source('OCR region refinement workers'), 1, 8, 4),
    'vision_interval_ms': (ui_source('Minimum AI image-reading interval (ms)'), 1000, 60000, 3000),
    'translation_workers': (ui_source('Concurrent translations'), 1, 16, 8),
    'tracking_workers': (ui_source('Text matching workers'), 1, 4, 2),
    'max_tracked_objects': (ui_source('Tracked text boxes'), 1, 128, 96),
    'capture_interval_ms': (ui_source('Capture interval (ms)'), 50, 2000, 50),
    'settle_ms': (ui_source('Text stability delay (ms)'), 0, 3000, 80),
    'track_missing_frames': (ui_source('Missed-frame retention'), 0, 30, 10),
    'translation_hold_ms': (ui_source('Previous translation hold (ms)'), 0, 10000, DEFAULT_TRANSLATION_HOLD_MS),
    'scene_change_sensitivity': (ui_source('Screen change sensitivity'), 0, 100, DEFAULT_SCENE_CHANGE_SENSITIVITY),
    'ocr_min_confidence': (ui_source('Portable OCR confidence threshold'), 0, 100, 55),
    'max_requests': (ui_source('API request limit per session'), 0, 10000, 80),
    'request_timeout': (ui_source('API timeout (seconds)'), 1, 120, 30),
    'max_retries': (ui_source('Retries after failure'), 0, 2, 1),
    'max_output_tokens': (ui_source('Maximum translation output tokens'), 32, 4096, 512),
    'max_input_chars': (ui_source('Maximum input characters'), 64, 16000, 4000),
}
BOOLEAN_FIELDS = {
    'cursor_attention': (ui_source('Prioritize text near the pointer'), True),
    'active_scene_summary': (ui_source('Summarize game context in background (uses API requests)'), True),
    'retranslate_hotkey_enabled': (ui_source('Enable global retranslation shortcut'), True),
    'toggle_hotkey_enabled': (ui_source('Enable global translation toggle'), True),
    'cuda_enabled': (ui_source('Enable CUDA OCR (automatic fallback when unavailable)'), True),
    'context_web_search': (ui_source('Research game background online (DeepSeek Flash)'), False),
    'auto_font_style': (ui_source('Match the source font style automatically (target-language support)'), False),
    'capture_translations': (ui_source('Include translations in screenshots and recordings'), True),
    'auto_font_size': (ui_source('Automatically fit translation font size'), True),
    'unlimited_requests': (ui_source('Unlimited API requests'), False),
    'show_source_label': (ui_source('Show source-language label'), True),
    'source_label_mixed_only': (ui_source('Label only when one text block contains multiple foreign languages'), True),
    'show_translation_brackets': (ui_source('Wrap translations in brackets [ ]'), True),
    'merge_dialogue_lines': (ui_source('Merge adjacent dialogue lines'), True),
}
TUNING_DEFAULTS = {k:v[3] for k,v in NUMERIC_FIELDS.items()}
TUNING_DEFAULTS.update({k:v[1] for k,v in BOOLEAN_FIELDS.items()})
TUNING_DEFAULTS['max_concurrency'] = TUNING_DEFAULTS['translation_workers']
TUNING_DEFAULTS.update(overlay_font_family=DEFAULT_OVERLAY_FONT, app_language='zh-CN', ocr_mode='auto',
                       sampling_mode='auto', vision_ocr_mode='off')
TUNING_DEFAULTS['retranslate_hotkey'] = DEFAULT_HOTKEY
TUNING_DEFAULTS['toggle_hotkey'] = DEFAULT_TOGGLE_HOTKEY


def fast_capture_interval_ms(memory_mb):
    # DXGI can report capacity after a small hardware reservation. Keep an
    # 8017 MiB reading in the 8 GiB class rather than the 4 GiB class.
    hardware_gib=(memory_mb+256)//1024
    if hardware_gib>=12:return 25
    if hardware_gib>=8:return 33
    if hardware_gib>=4:return 40
    return 50


def default_sampling_mode(nvidia_memory_mb):
    return 'supersample' if nvidia_memory_mb>0 else 'auto'

# Presets only change scheduling/resource fields when explicitly selected.
# Existing custom values remain intact on upgrade. Miss retention stays ~500 ms.
PERFORMANCE_PRESETS = {
    'responsive': dict(capture_interval_ms=50,settle_ms=80,translation_workers=8,
                       ocr_refine_workers=4,tracking_workers=2,track_missing_frames=10),
    'balanced': dict(capture_interval_ms=250,settle_ms=450,translation_workers=4,
                    ocr_refine_workers=2,tracking_workers=2,track_missing_frames=2),
}


def validate_font_family(value):
    """A Windows LOGFONT family name, not a font file or path."""
    if not isinstance(value, str) or any(unicodedata.category(c) in {'Cc', 'Cf', 'Cs'} for c in value):
        raise TuningValidationError(ui_source('Font names cannot contain control characters.'))
    value = value.strip()
    if not value or len(value.encode('utf-16-le')) // 2 > 31:
        raise TuningValidationError(ui_source('Font names must contain 1–31 UTF-16 code units.'))
    return value


def validate_tuning(values):
    """Return only managed fields, preserving unrelated config in the caller."""
    if not isinstance(values, dict):
        raise TuningValidationError(ui_source('Settings must be key-value pairs.'))
    result = {}
    for name,(label,minimum,maximum,default) in NUMERIC_FIELDS.items():
        value = values.get(name, default)
        if isinstance(value, str) and len(value.strip()) <= 6 and re.fullmatch(r'[0-9]+', value.strip()):
            value = int(value.strip())
        if type(value) is not int or not minimum <= value <= maximum:
            raise TuningValidationError(f'{label}\u987b\u4e3a {minimum} \u81f3 {maximum} \u7684\u6574\u6570\u3002')
        result[name] = value
    for name,(label,default) in BOOLEAN_FIELDS.items():
        value = values.get(name,default)
        if type(value) is not bool:
            raise TuningValidationError(f'{label}\u987b\u4e3a\u5f00\u6216\u5173\u3002')
        result[name] = value
    result['max_concurrency'] = result['translation_workers']
    if result['overlay_font_min'] > result['overlay_font_max']:
        raise TuningValidationError(ui_source('The minimum font size cannot exceed the maximum.'))
    result['overlay_font_family'] = validate_font_family(values.get('overlay_font_family', DEFAULT_OVERLAY_FONT))
    app_language = values.get('app_language', 'zh-CN')
    if not isinstance(app_language, str) or app_language not in APP_LANGUAGES:
        raise TuningValidationError(ui_source('Choose Simplified Chinese, English, or Japanese for the interface.'))
    result['app_language'] = app_language
    if values.get('ocr_mode','auto') not in ('auto','native','pixel'):
        raise TuningValidationError(ui_source('OCR mode must be Automatic, Windows, or Pixel text.'))
    result['ocr_mode'] = values.get('ocr_mode','auto')
    result['sampling_mode'] = values.get('sampling_mode','auto')
    if result['sampling_mode'] not in ('off','auto','supersample'):
        raise TuningValidationError('\u5e73\u79fb\u91c7\u6837\u987b\u4e3a\u5173\u95ed\u3001\u81ea\u52a8\u6216\u8d85\u91c7\u6837\u3002')
    legacy_vision = values.get('vision_ocr', False)
    if type(legacy_vision) is not bool:
        raise TuningValidationError('\u65e7\u7248\u56fe\u50cf\u8bc6\u522b\u8bbe\u7f6e\u987b\u4e3a\u5f00\u6216\u5173\u3002')
    mode = values.get('vision_ocr_mode', 'force' if legacy_vision else 'off')
    if mode not in ('force', 'off'):
        raise TuningValidationError('LLM\u540e\u7aef\u8bc6\u522b\u56fe\u7247\u987b\u4e3a\u5f3a\u5236\u6216\u5173\u3002')
    result['vision_ocr_mode'] = mode
    try:
        result['retranslate_hotkey'] = normalize_hotkey(values.get('retranslate_hotkey', DEFAULT_HOTKEY))
        result['toggle_hotkey'] = normalize_hotkey(values.get('toggle_hotkey', DEFAULT_TOGGLE_HOTKEY))
    except HotkeyValidationError as error:raise TuningValidationError(str(error)) from None
    if (result['toggle_hotkey_enabled'] and result['retranslate_hotkey_enabled']
            and result['toggle_hotkey']==result['retranslate_hotkey']):
        raise TuningValidationError(ui_source('Toggle and retranslate need different shortcuts.'))
    return result
