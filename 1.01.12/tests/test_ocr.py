"""File-only Japanese OCR integration tests; never display or activate windows."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont
import pytest

from nkc_galgame_translator.ocr import OcrCore, PortableOcr, filter_portable_lines

ROOT = Path(__file__).resolve().parents[1]
FONT = Path("C:/Windows/Fonts/msgothic.ttc")


def japanese_fixture():
    if not FONT.is_file():
        pytest.skip("Japanese fixture font not installed")
    image = Image.new("RGB", (960,250), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT),38)
    draw.text((32,30),"\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d\u3002",font=font,fill="black")
    draw.text((32,110),"\u30b2\u30fc\u30e0\u3092\u958b\u59cb\u3059\u308b",font=font,fill="black")
    return image


def require_portable():
    ocr = PortableOcr(ROOT)
    if not ocr.available():
        pytest.skip("Optional project-local Japanese OCR wheel/models absent")
    return ocr


def test_real_japanese_ocr_and_process_reuse():
    ocr = require_portable()
    try:
        image = japanese_fixture()
        first = ocr.recognize(image)
        pid = ocr._process.pid
        second = ocr.recognize(image)
        assert ocr._process.pid == pid
        assert [line["text"] for line in first["lines"]] == [line["text"] for line in second["lines"]]
        text = "".join(line["text"] for line in first["lines"])
        assert "\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d" in text
        assert "\u30b2\u30fc\u30e0\u3092\u958b\u59cb\u3059\u308b" in text
        for line in first["lines"]:
            assert 0 <= line["x"] < line["x"]+line["w"] <= image.width
            assert 0 <= line["y"] < line["y"]+line["h"] <= image.height
            assert line["confidence"] > 70
    finally:
        ocr.close()
    assert ocr._process is None


def test_missing_dependencies_are_explicit_and_do_not_spawn(tmp_path):
    ocr = PortableOcr(tmp_path)
    assert not ocr.available()
    with pytest.raises(RuntimeError,match="tesserocr"):
        ocr.recognize(Image.new("RGB",(20,20)))
    assert ocr._process is None


def test_blank_and_single_line_are_normal_ocr_results():
    ocr=require_portable()
    try:
        blank=Image.new("RGB",(640,160),"white")
        assert ocr.recognize(blank)["lines"]==[]
        single=japanese_fixture().crop((0,0,960,90))
        response=ocr.recognize(single)
        assert "\u7d05\u9b54\u9928\u3078\u3088\u3046\u3053\u305d" in "".join(line["text"] for line in response["lines"])
        assert ocr.recognize(blank)["lines"]==[]
    finally:
        ocr.close()


@pytest.mark.skipif(sys.platform != "win32",reason="Windows native bridge")
def test_fallback_coordinate_mapping_and_unchanged_frame(monkeypatch):
    require_portable().close()
    image = japanese_fixture()
    bgra = image.tobytes("raw","BGRX")
    with OcrCore() as core:
        core._native_languages = ["en-US"]
        assert "ja-JP" in core.languages()
        monkeypatch.setattr(core.native,"capture_bgra",lambda *_: {"changed":True,"capture_ms":1.0,"bgra":bgra})
        result = core.capture_ocr(100,200,image.width,image.height,"ja")
        assert result["engine"] == "portable-tesseract"
        assert result["lines"][0]["x"] >= 100
        assert result["lines"][0]["y"] >= 200
        assert result["lines"][0]["bg"] == [255,255,255]
        monkeypatch.setattr(core.native,"capture_bgra",lambda *_: {"changed":False,"capture_ms":1.0,"bgra":None})
        def unexpected(_):
            raise AssertionError("Unchanged frame must not invoke helper")
        monkeypatch.setattr(core.portable,"recognize",unexpected)
        assert core.capture_ocr(100,200,image.width,image.height,"ja")["changed"] is False


def test_low_confidence_icon_is_excluded_before_overlay(monkeypatch):
    image = Image.new("RGB", (240, 100), (17, 17, 17))
    observations = [
        {"text":"\u9375\u30925\u3064\u96c6\u3081\u3066\u30b4\u30fc\u30eb\u3078\u5411\u304b\u3046","x":10,"y":10,"w":210,"h":25,"confidence":91.8},
        {"text":"SR RBS","x":30,"y":55,"w":160,"h":35,"confidence":32.18},
    ]
    with OcrCore() as core:
        core._native_languages = ["en-US"]
        monkeypatch.setattr(core.portable,"available",lambda: True)
        monkeypatch.setattr(core.portable,"recognize",lambda _: {"lines":observations})
        monkeypatch.setattr(core.native,"capture_bgra",lambda *_: {
            "changed":True,"capture_ms":1.0,"bgra":image.tobytes("raw","BGRX")})
        result = core.capture_ocr(100,200,240,100,"ja")
        assert [line["text"] for line in result["lines"]] == [observations[0]["text"]]
        assert result["lines"][0]["confidence"] == 91.8
        assert result["rejected_lines"][0]["text"] == "SR RBS"
        assert result["rejected_lines"][0]["confidence"] == 32.18
        assert result["rejected_lines"][0]["rejected_reason"] == "below_confidence_threshold"
        assert "rejected_reason" not in observations[1]


def test_confidence_boundary_and_invalid_values():
    accepted,rejected=filter_portable_lines([
        {"text":"accepted", "confidence":55},
        {"text":"weak", "confidence":54.99},
        {"text":"unknown"},
        {"text":"nonfinite", "confidence":float("nan")},
    ])
    assert [line["text"] for line in accepted] == ["accepted"]
    assert [line["text"] for line in rejected] == ["weak","unknown","nonfinite"]
    with pytest.raises(ValueError):
        filter_portable_lines([], 101)
