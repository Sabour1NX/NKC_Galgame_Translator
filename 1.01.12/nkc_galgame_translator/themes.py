# SPDX-License-Identifier: MIT
"""Interface palettes."""

from .i18n import ui_source
from .system_theme import windows_colors
import re

DEFAULT_THEME = 'neon'
LABELS = {'neon':ui_source('Neon Wave'), 'system':ui_source('Use Windows colors'),
          'nishokuchou':ui_source('Two-color Butterfly'), 'modern_windows':ui_source('Windows style'),
          'custom':ui_source('Custom colors')}
COLOR_FIELDS = {'paper':ui_source('Window background'), 'surface':ui_source('Content background'), 'ink':ui_source('Text color'), 'accent':ui_source('Accent color')}
PRESETS = {
    'nishokuchou': dict(paper='#F7F3EE',surface='#FFFEFC',ink='#302E2B',accent='#B6332D'),
    'neon': dict(paper='#18112E',surface='#F8F2FF',ink='#211738',accent='#FF9FE9'),
    'modern_windows': dict(paper='#F3F6FC',surface='#FFFFFF',ink='#172438',accent='#075BB5'),
}


def mix(first, second, amount):
    return '#'+''.join(f'{round(int(first[i:i+2],16)*(1-amount)+int(second[i:i+2],16)*amount):02X}'
                      for i in (1,3,5))


def validate_theme(config):
    theme=config.get('interface_theme',DEFAULT_THEME)
    if not isinstance(theme,str) or theme not in LABELS:
        raise ValueError('\u8bf7\u9009\u62e9\u6709\u6548\u7684\u754c\u9762\u4e3b\u9898\u3002')
    colors=config.get('interface_colors',PRESETS['nishokuchou'])
    if not isinstance(colors,dict) or any(not re.fullmatch(r'#[0-9A-Fa-f]{6}',str(colors.get(k,''))) for k in COLOR_FIELDS):
        raise ValueError('\u989c\u8272\u987b\u91c7\u7528 #RRGGBB \u683c\u5f0f\u3002')
    picture = config.get('chart_picture', '')
    chart_style = config.get('custom_chart_style', 'line')
    overrides = config.get('chart_colors', {})
    if not isinstance(overrides, dict):
        raise ValueError(ui_source('Use a color in #RRGGBB format.'))
    chart_colors = {}
    for name, pair in overrides.items():
        if (name not in LABELS or not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(v, str) or (v and not re.fullmatch(r'#[0-9A-Fa-f]{6}', v)) for v in pair)):
            raise ValueError(ui_source('Use a color in #RRGGBB format.'))
        if any(pair):
            chart_colors[name] = [v.upper() for v in pair]
    styles = config.get('chart_styles', {})
    chart_styles = {k:v for k,v in styles.items() if k in LABELS and v in ('line', 'mountains')} if isinstance(styles, dict) else {}
    return {'interface_theme':theme, 'interface_colors':{k:colors[k].upper() for k in COLOR_FIELDS},
            'chart_colors':chart_colors, 'chart_styles':chart_styles,
            'custom_chart_style':chart_style if chart_style in ('mountains', 'line') else 'line',
            'chart_picture':picture if isinstance(picture, str) else ''}


def chart_style(config):
    theme = config.get('interface_theme', DEFAULT_THEME)
    if theme in config.get('chart_styles', {}):
        return config['chart_styles'][theme]
    if theme == 'custom':
        return validate_theme(config)['custom_chart_style']
    return 'line'


def luminance(color):
    rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    return sum(weight * (value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4)
               for weight, value in zip((.2126, .7152, .0722), rgb))


def palette(config):
    try:
        prefs=validate_theme(config)
    except (ValueError,TypeError):
        prefs=validate_theme({})
    name=prefs['interface_theme']
    if name == 'system':
        surface, ink, accent = windows_colors()
        paper = mix(surface, ink, .055)
    else:
        paper, surface, ink, accent = (prefs['interface_colors'] if name == 'custom' else PRESETS[name]).values()
    button_text = '#000000' if luminance(accent) > .179 else '#FFFFFF'
    return paper,surface,ink,mix(ink,surface,.24),accent,mix(surface,accent,.20),mix(surface,ink,.28),button_text
