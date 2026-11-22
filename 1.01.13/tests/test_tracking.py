# SPDX-License-Identifier: MIT
"""Stable OCR identity, bounded scheduling and snapshot safety; no UI/network."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

import nkc_galgame_translator.tracking as tracking
from nkc_galgame_translator.tracking import ObjectTracker
from nkc_galgame_translator.presentation import OverlayState


def line(text='Hello', x=20, y=20, w=200, h=24, **extra):
    return {'text': text, 'x': x, 'y': y, 'w': w, 'h': h,
            'bg': [10, 20, 30], 'fg': [250, 250, 250], **extra}


def by_text(update):
    return {track.line['text']: track for track in update.tracks}


def test_distinct_objects_survive_motion_and_reordered_detections():
    with ObjectTracker() as tracker:
        first = by_text(tracker.update([line('Start', x=20, y=20), line('Exit', x=400, y=120)]))
        second = tracker.update([line('Exit', x=410, y=125), line('Start', x=30, y=25)])
        latest = by_text(second)
        assert latest['Start'].track_id == first['Start'].track_id
        assert latest['Exit'].track_id == first['Exit'].track_id
        assert second.changed_ids == []
        assert latest['Exit'].revision == 1


def test_duplicate_text_boxes_remain_distinct_and_follow_nearest_geometry():
    with ObjectTracker() as tracker:
        first = tracker.update([line('OK', x=20, y=20), line('OK', x=500, y=180)])
        latest = tracker.update([line('OK', x=507, y=183), line('OK', x=25, y=23)])
        assert len({track.track_id for track in latest.tracks}) == 2
        assert [track.track_id for track in latest.tracks] == [track.track_id for track in first.tracks]
        assert latest.changed_ids == []


def test_only_changed_content_increments_its_own_revision():
    with ObjectTracker() as tracker:
        first = tracker.update([line('Take the key'), line('Exit', y=160)])
        latest = tracker.update([line('Open the door'), line('Exit', y=160)])
        assert [track.track_id for track in latest.tracks] == [track.track_id for track in first.tracks]
        assert [track.revision for track in latest.tracks] == [2, 1]
        assert latest.changed_ids == [first.tracks[0].track_id]


def test_colors_and_dimensions_update_without_invalidating_translation():
    with ObjectTracker() as tracker:
        first = tracker.update([line()]).tracks[0]
        second = tracker.update([line(x=25, w=208, bg=[60, 70, 80])])
        assert second.tracks[0].track_id == first.track_id
        assert second.tracks[0].revision == first.revision
        assert tuple(second.tracks[0].line['bg']) == (60, 70, 80)
        assert not second.changed_ids


def test_unicode_and_spacing_normalization_but_hard_linebreak_revision():
    with ObjectTracker() as tracker:
        first = tracker.update([line('\uff28\uff30  \uff15')]).tracks[0]
        second = tracker.update([line('HP 5')]).tracks[0]
        assert second.track_id == first.track_id and second.revision == 1
        third = tracker.update([line('HP\n5')]).tracks[0]
        assert third.track_id == first.track_id and third.revision == 2


def test_origin_change_keeps_ids_and_publishes_absolute_geometry():
    with ObjectTracker() as tracker:
        first = tracker.update([line(x=120, y=220)], origin=(100, 200)).tracks[0]
        second = tracker.update([line(x=1020, y=720)], origin=(1000, 700)).tracks[0]
        assert (second.track_id, second.revision) == (first.track_id, 1)
        assert second.line['x'] == 1020 and second.line['y'] == 720


def test_missing_hidden_immediately_then_reacquired_without_new_revision():
    with ObjectTracker(max_missing=2) as tracker:
        first = tracker.update([line()]).tracks[0]
        absent = tracker.update([])
        assert absent.tracks == [] and absent.removed_ids == [first.track_id]
        assert tracker.get(first.track_id).visible is False
        assert tracker.update([]).removed_ids == []
        returned = tracker.update([line(x=22)]).tracks[0]
        assert (returned.track_id, returned.revision) == (first.track_id, 1)
        assert returned.visible


def test_expired_detection_gets_new_id():
    with ObjectTracker(max_missing=1) as tracker:
        first = tracker.update([line()]).tracks[0]
        tracker.update([])
        tracker.update([])
        assert tracker.get(first.track_id) is None
        returned = tracker.update([line()]).tracks[0]
        assert returned.track_id > first.track_id


def test_reset_does_not_reuse_ids():
    with ObjectTracker() as tracker:
        before = tracker.update([line()]).tracks[0]
        tracker.reset()
        assert tracker.get(before.track_id) is None
        after = tracker.update([line()]).tracks[0]
        assert after.track_id > before.track_id


def test_capacity_does_not_let_hidden_objects_block_visible_new_text():
    with ObjectTracker(max_tracks=2, max_missing=10) as tracker:
        first = tracker.update([line('A', y=10), line('B', y=100)])
        latest = tracker.update([line('C', x=2000, y=1000), line('D', x=2400, y=1000), line('E', x=2800, y=1000)])
        assert len(latest.tracks) == 2
        assert {track.line['text'] for track in latest.tracks} == {'C', 'D'}
        assert set(latest.removed_ids) == {track.track_id for track in first.tracks}
        assert all(tracker.get(track.track_id) is None for track in first.tracks)


def test_input_and_returned_snapshot_cannot_mutate_state():
    with ObjectTracker() as tracker:
        original = line()
        track = tracker.update([original]).tracks[0]
        original['text'] = 'Changed externally'
        original['bg'][0] = 200
        assert tracker.get(track.track_id).line['text'] == 'Hello'
        assert tracker.get(track.track_id).line['bg'][0] == 10
        with pytest.raises(TypeError):
            track.line['text'] = 'Mutation'
        with pytest.raises(TypeError):
            track.line['bg'][0] = 90


def test_worker_pool_actually_scores_concurrently_and_is_bounded(monkeypatch):
    actual = tracking._score_candidates
    barrier = threading.Barrier(2)
    guard = threading.Lock()
    active, peak, names = 0, 0, set()

    def score(*args):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
            names.add(threading.current_thread().name)
        try:
            barrier.wait(2)
            return actual(*args)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(tracking, '_score_candidates', score)
    with ObjectTracker(workers=2) as tracker:
        first = tracker.update([line('A'), line('B', y=100), line('C', y=180), line('D', y=260)])
        latest = tracker.update([line('D', y=260), line('B', y=100), line('A'), line('C', y=180)])
        assert peak == 2 and len(names) == 2
        assert latest.changed_ids == []
        assert [track.track_id for track in latest.tracks] == [track.track_id for track in first.tracks]


def test_get_remains_responsive_during_scoring(monkeypatch):
    actual = tracking._score_candidates
    entered, release = threading.Event(), threading.Event()

    def score(*args):
        entered.set()
        assert release.wait(3)
        return actual(*args)

    with ObjectTracker() as tracker, ThreadPoolExecutor(max_workers=1) as caller:
        old = tracker.update([line()]).tracks[0]
        monkeypatch.setattr(tracking, '_score_candidates', score)
        pending = caller.submit(tracker.update, [line('Changed')])
        assert entered.wait(1)
        try:
            assert tracker.get(old.track_id).line['text'] == 'Hello'
        finally:
            release.set()
        assert pending.result(2).tracks[0].revision == 2


def test_invalid_boxes_ignored_and_invalid_origin_rejected():
    with ObjectTracker() as tracker:
        result = tracker.update([line(''), line(w=0), line(x=float('nan')), line('Valid')])
        assert [track.line['text'] for track in result.tracks] == ['Valid']
        with pytest.raises(ValueError):
            tracker.update([line()], origin=(float('inf'), 0))


def test_worker_count_and_capacity_have_hard_limits():
    with ObjectTracker(workers=99, max_tracks=999) as tracker:
        assert tracker.workers == 4 and tracker.max_tracks == 128
        assert len(tracker.update([line(str(i), y=i*30) for i in range(150)]).tracks) == 128


def test_close_idempotent_and_refuses_more_work():
    tracker = ObjectTracker()
    tracker.update([line()])
    tracker.close()
    tracker.close()
    assert tracker.get(1) is None
    with pytest.raises(RuntimeError, match='closed'):
        tracker.update([line()])
    with pytest.raises(RuntimeError, match='closed'):
        tracker.reset()


def test_distant_nonmatching_text_never_runs_fuzzy_similarity(monkeypatch):
    def unexpected_similarity(*_):
        raise AssertionError('Fuzzy similarity ran for an impossible distant pair')

    with ObjectTracker() as tracker:
        first = tracker.update([line('Old text', x=0, y=0)]).tracks[0]
        monkeypatch.setattr(tracking, '_similarity', unexpected_similarity)
        latest = tracker.update([line('Completely different', x=5000, y=5000)])
        assert latest.tracks[0].track_id != first.track_id
        assert latest.removed_ids == [first.track_id]


@pytest.mark.parametrize('change', ['append', 'insert', 'delete'])
def test_small_edits_to_long_repetitive_text_trim_without_fuzzy_matching(monkeypatch, change):
    original = 'abc ' * 180
    if change == 'append':
        edited = original + '!'
    elif change == 'insert':
        edited = original[:360] + '\u8ffd\u52a0' + original[360:]
    else:
        edited = original[:360] + original[364:]

    def unexpected_matcher(*_, **__):
        raise AssertionError('Known common edges should avoid SequenceMatcher')

    monkeypatch.setattr(tracking, 'SequenceMatcher', unexpected_matcher)
    expected = 2 * min(len(original), len(edited)) / (len(original) + len(edited))
    assert tracking._similarity(original, edited) == pytest.approx(expected)


def test_long_dialogue_edits_keep_ids_and_increment_only_changed_object():
    original = '\u3042\u3044\u3046\u3048\u304a ' * 140
    with ObjectTracker() as tracker:
        first = tracker.update([line(original, y=0), line('Inventory', y=140)])
        edited = original[:420] + '\u9375\u3092\u62fe\u3046' + original[420:]
        latest = tracker.update([line(edited, y=0), line('Inventory', y=140)])
        assert [item.track_id for item in latest.tracks] == [item.track_id for item in first.tracks]
        assert [item.revision for item in latest.tracks] == [2, 1]
        assert latest.changed_ids == [first.tracks[0].track_id]


def test_unmatched_middle_is_bounded_even_when_both_ends_change(monkeypatch):
    real_matcher = tracking.SequenceMatcher
    sample_lengths = []

    def measured(_, first, second, **kwargs):
        sample_lengths.append((len(first), len(second)))
        return real_matcher(None, first, second, **kwargs)

    monkeypatch.setattr(tracking, 'SequenceMatcher', measured)
    similarity = tracking._similarity('A' + 'abc ' * 180 + 'Z', 'B' + 'abc ' * 180 + 'Y')
    assert similarity > .9
    assert sample_lengths and all(max(lengths) <= 256 for lengths in sample_lengths)


def overlay_objects(update):
    return [{'track_id': item.track_id, 'revision': item.revision, 'line': item.line}
            for item in update.tracks]


@pytest.mark.parametrize('mistake', [
    'Welcome to the manslon',       # One interior substitution.
    'Welcome to the manXXon',       # Two interior substitutions.
    'Welcome to the manZsion',      # One interior insertion.
    'Welcome to the manon',        # Two interior deletions.
])
def test_single_minor_ocr_error_keeps_revision_and_existing_translation(mistake):
    original = 'Welcome to the mansion'
    with ObjectTracker() as tracker:
        overlay = OverlayState()
        first = tracker.update([line(original)])
        track = first.tracks[0]
        overlay.apply_objects(overlay_objects(first))
        overlay.apply_translation(track.track_id, {'text': '\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986', 'final': True,
                                                  '_revision': track.revision})
        observed = tracker.update([line(mistake, x=22, bg=[40, 50, 60])])
        overlay.apply_objects(overlay_objects(observed))
        latest = observed.tracks[0]
        assert (latest.track_id, latest.revision) == (track.track_id, track.revision)
        assert latest.line['text'] == original
        assert tuple(latest.line['bg']) == (40, 50, 60)
        assert observed.changed_ids == []
        assert observed.removed_ids == []
        assert overlay.rendered[track.track_id]['text'] == '\u6b22\u8fce\u6765\u5230\u7ea2\u9b54\u9986'


def test_two_consecutive_identical_minor_changes_commit_real_content():
    before, after = 'Welcome to the mansion', 'Welcome to the manslon'
    with ObjectTracker() as tracker:
        initial = tracker.update([line(before)]).tracks[0]
        assert tracker.update([line(after)]).changed_ids == []
        confirmed = tracker.update([line(after)])
        assert confirmed.tracks[0].track_id == initial.track_id
        assert confirmed.tracks[0].revision == initial.revision + 1
        assert confirmed.tracks[0].line['text'] == after
        assert confirmed.changed_ids == [initial.track_id]
        assert tracker.update([line(after)]).changed_ids == []


def test_recovery_to_accepted_text_clears_minor_change_candidate():
    before, mistake = 'Welcome to the mansion', 'Welcome to the manslon'
    with ObjectTracker() as tracker:
        first = tracker.update([line(before)]).tracks[0]
        for text in (mistake, before, mistake):
            update = tracker.update([line(text)])
            assert update.changed_ids == []
            assert update.tracks[0].line['text'] == before
            assert update.tracks[0].revision == first.revision
        assert tracker.update([line(mistake)]).changed_ids == [first.track_id]


def test_alternating_minor_ocr_candidates_do_not_confirm_each_other():
    before = 'Welcome to the mansion'
    candidates = ['Welcome to the manslon', 'Welcome to the mansxon']
    with ObjectTracker() as tracker:
        first = tracker.update([line(before)]).tracks[0]
        for text in candidates * 3:
            update = tracker.update([line(text)])
            assert update.changed_ids == []
            assert update.tracks[0].line['text'] == before
            assert update.tracks[0].revision == first.revision
        assert tracker.update([line(candidates[-1])]).changed_ids == [first.track_id]


def test_reacquired_changed_text_commits_immediately_after_missing_frame():
    before, after = 'Welcome to the mansion', 'Welcome to the manslon'
    with ObjectTracker() as tracker:
        first = tracker.update([line(before)]).tracks[0]
        tracker.update([])
        update = tracker.update([line(after)])
        assert update.tracks[0].track_id == first.track_id
        assert update.tracks[0].revision == first.revision + 1
        assert update.tracks[0].line['text'] == after
        assert update.changed_ids == [first.track_id]


@pytest.mark.parametrize('before,after', [
    ('Collect 5 keys in this room.', 'Collect 6 keys in this room.'),
    ('Welcome to the mansion', 'Welcome to the mansion!'),
    ('Welcome to the mansion', 'Welcome to the mansio'),
    ('Welcome to the mansion', 'Welcome to\nthe mansion'),
    ('Welcome to\nthe mansion', 'Welcome to the mansion'),
    ('Welcome to the mansion', 'Welcome to the manXYZn'),
    ('Welcome to the mansion', 'A completely different dialogue passage'),
    ('A' * 260 + 'mansion' + 'Z' * 260, 'A' * 260 + 'manslon' + 'Z' * 260),
    ('Welcome', 'WelcXme'),
])
def test_meaningful_or_unbounded_changes_are_not_delayed(before, after):
    with ObjectTracker() as tracker:
        first = tracker.update([line(before)]).tracks[0]
        latest = tracker.update([line(after)])
        assert latest.tracks[0].track_id == first.track_id
        assert latest.tracks[0].revision == first.revision + 1
        assert latest.tracks[0].line['text'] == after
        assert latest.changed_ids == [first.track_id]


def test_changed_source_language_does_not_hold_a_minor_text_edit():
    with ObjectTracker() as tracker:
        first = tracker.update([line('Welcome to the mansion', source_lang='en')]).tracks[0]
        update = tracker.update([line('Welcome to the manslon', source_lang='ja')])
        assert update.tracks[0].track_id == first.track_id
        assert update.tracks[0].revision == first.revision + 1
        assert update.changed_ids == [first.track_id]


def test_quality_change_revises_identical_text_and_bypasses_minor_edit_debounce():
    with ObjectTracker() as tracker:
        before=tracker.update([line('New or Old game?',source_lang='en')]).tracks[0]
        rejected=tracker.update([line('New or Old game?',source_lang='en',_preserve_source=True)]).tracks[0]
        assert rejected.track_id==before.track_id and rejected.revision==before.revision+1
        # Even a one-character change cannot retain rejected text on recovery.
        restored=tracker.update([line('New or Old Game?',source_lang='en')]).tracks[0]
        assert restored.revision==rejected.revision+1 and restored.line['text']=='New or Old Game?'
        rejected_again=tracker.update([line('New or Old Gane?',source_lang='en',_preserve_source=True)]).tracks[0]
        assert rejected_again.revision==restored.revision+1 and rejected_again.line['text']=='New or Old Gane?'
