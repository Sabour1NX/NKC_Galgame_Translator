# SPDX-License-Identifier: MIT
from nkc_galgame_translator.layout import merge_dialogue_lines


def row(text, x=20, y=20, w=300, h=24, **extra):
    return {"text": text, "x": x, "y": y, "w": w, "h": h,
            "bg": [20, 25, 30], "fg": [240, 240, 240], **extra}


def test_close_aligned_dialogue_group_unions_bounds_and_keeps_font_height():
    lines = [row("Welcome to", w=300, font_size=19), row("the mansion.", x=22, y=50, w=200)]
    result = merge_dialogue_lines(lines)
    assert len(result) == 1
    assert result[0]["text"] == "Welcome to\nthe mansion."
    assert [result[0][key] for key in ("x", "y", "w", "h", "font_size")] == [20, 20, 300, 54, 19]
    assert lines[0]["text"] == "Welcome to"  # no input mutation


def test_larger_menu_gaps_stay_separate():
    lines = [row("New Game"), row("Load Game", y=58), row("Options", y=96)]
    assert merge_dialogue_lines(lines) == lines


def test_columns_never_merge_or_bridge_intervening_column():
    lines = [row("Left one", w=150), row("Right one", x=240, w=150),
             row("Left two", y=50, w=150), row("Right two", x=240, y=50, w=150)]
    assert len(merge_dialogue_lines(lines)) == 4


def test_continuous_paragraph_is_not_arbitrarily_split_after_four_lines():
    result = merge_dialogue_lines([row(f"Row {i}", y=20+i*30) for i in range(9)])
    assert [len(item["text"].splitlines()) for item in result] == [9]


def test_paragraph_has_bounded_rows_without_losing_or_reordering_text():
    lines = [row(f"Dialogue row {i}", y=20+i*30) for i in range(35)]
    result = merge_dialogue_lines(lines)
    assert [len(item["text"].splitlines()) for item in result] == [32, 3]
    assert "\n".join(item["text"] for item in result) == "\n".join(item["text"] for item in lines)


def test_paragraph_budget_counts_separating_newline_and_preserves_long_input():
    first = row("a" * 2000)
    second = row("b" * 1999, y=50)
    assert len(merge_dialogue_lines([first, second])) == 1  # 4000 including LF.
    second["text"] += "b"
    assert merge_dialogue_lines([first, second]) == [first, second]
    oversized = row("c" * 4001)
    assert merge_dialogue_lines([oversized]) == [oversized]


def test_union_spans_remain_bounded_without_clipping_source():
    lines = [row("Wide text", w=4096), row("More text", x=22, y=50, w=4096)]
    assert merge_dialogue_lines(lines) == lines


def test_tightly_stacked_compact_menu_labels_remain_separate():
    lines = [row(text, y=20+i*30, w=len(text)*12)
             for i, text in enumerate(("New Game", "Load Game", "Options", "Exit"))]
    assert merge_dialogue_lines(lines) == lines


def test_compact_cjk_button_labels_remain_separate():
    lines = [row(text, y=20+i*30, w=48, source_lang="ja")
             for i, text in enumerate(("\u958b\u59cb", "\u8a2d\u5b9a", "\u7d42\u4e86"))]
    assert merge_dialogue_lines(lines) == lines


def test_short_last_line_stays_with_full_width_dialogue():
    lines = [row("This is a complete dialogue line", w=360), row("Goodbye.", y=50, w=96)]
    result = merge_dialogue_lines(lines)
    assert len(result) == 1
    assert result[0]["text"].endswith("\nGoodbye.")


def test_existing_hard_newlines_unchanged_and_not_misread_as_single_line():
    source = row("First\nSecond", h=54, font_size=21)
    assert merge_dialogue_lines([source]) == [source]
    assert merge_dialogue_lines([source, row("Third", y=80)]) == [source, row("Third", y=80)]


def test_style_or_indentation_changes_block_grouping():
    base = row("Speaker")
    variants = [row("Dialogue", y=50, x=60), row("Dialogue", y=50, h=34),
                row("Dialogue", y=50, bg=[100, 100, 100]), row("Dialogue", y=50, fg=[0, 0, 0])]
    for variant in variants:
        assert len(merge_dialogue_lines([base, variant])) == 2


def test_small_ocr_padding_overlap_allowed_but_same_row_is_not():
    assert len(merge_dialogue_lines([row("One"), row("Two", y=42)])) == 1
    assert len(merge_dialogue_lines([row("One"), row("Two", y=20)])) == 2


def test_empty_input():
    assert merge_dialogue_lines([]) == []
