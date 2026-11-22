# SPDX-License-Identifier: MIT
from unittest.mock import Mock
from bisect import bisect_right
from random import Random

import pytest

from nkc_galgame_translator.resource_usage import ResourceUsage, RidgePeak, SessionSamples, version_colors
from nkc_galgame_translator.themes import mix


def record_pair(series, timestamp, pair):
    for index, value in enumerate(pair):
        series.record(index, value, timestamp + index * .5)


def chart_path(series, index, latest):
    points = series.visible(index, latest)
    values = [v for _, v, _ in points]
    limits = (min(values), max(values)) if values else (0, 0)
    return series.plot(index, points, latest, limits, 10, 70, 30, 100)


def test_visible_extrema_scale_small_changes_and_keep_session_peaks():
    series = SessionSamples(capacity=4)
    for timestamp, values in enumerate([(70, 600), (20, 300), (30, 400), (15, 200), (25, 220)]):
        record_pair(series, timestamp, values)
    assert series.peaks == [70, 600]
    path = chart_path(series, 0, 4.5)
    assert [p[0] for p in path] == [20, 40, 60]
    assert [p[0] for p in chart_path(series, 1, 4.5)] == [10, 30, 50, 70]
    assert min(p[1] for p in path) == 30 and max(p[1] for p in path) == 100


def test_flat_data_stays_flat_and_gaps_end_only_the_affected_curve():
    series = SessionSamples(capacity=5)
    for t, values in enumerate([(9, 40), (None, 40), (2, 40), (2, 40)]):
        record_pair(series, t, values)
    assert [p[1] for p in chart_path(series, 0, 3.5)] == [65, 65]
    assert [p[1] for p in chart_path(series, 1, 3.5)] == [65] * 4
    series.record(0, None, 4)
    assert chart_path(series, 0, 4) == []


def test_ridge_peaks_move_independently_and_release_colors_vary():
    samples = SessionSamples()
    samples.random.seed(19)
    record_pair(samples, 0, (10, 100))
    record_pair(samples, 1, (40, 200))
    newest, older = (point[2] for point in chart_path(samples, 0, 1.5))
    assert newest != older
    assert newest.at(30, 120, 2) > 30
    assert newest.at(30, 120, 2) != newest.at(30, 120, 3)
    assert older.at(83, 120, 2) != older.at(83, 120, 3)
    assert version_colors("1.01.01", "#18112E", "#FF9FE9") != version_colors("1.01.02", "#18112E", "#FF9FE9")


def test_triangle_closes_at_the_next_actual_turn_across_a_straight_sample():
    chart = Mock(panel="#18112E")
    peak = RidgePeak(6, 0, 0, 0, 0, "triangle")
    path = [(0, 47, peak), (20, 32, peak), (40, 40, peak), (60, 48, peak), (80, 34, peak)]
    ResourceUsage._draw_ridge(chart, path, "#FF9FE9", 83, 0)
    chart.create_polygon.assert_not_called()
    link, = chart.create_line.call_args_list
    assert link.args[:2] == (20, 32) and link.args[-2:] == (60, 48)
    assert 20 < link.args[2] < 60 and link.args[3] > 48
    assert "ridge-link" in link.kwargs["tags"]


def test_opposing_legs_cannot_cross_even_when_the_peaks_are_far_apart():
    right = RidgePeak(6, 0, 0, 0, 1, "ground")
    left = RidgePeak(6, 0, 0, 0, -1, "ground")
    path = [(0, 120, left), (25, 30, right), (55, 60, left), (85, 42, right)]
    chart = Mock(panel="#18112E")
    visible = ResourceUsage._draw_ridge(chart, path, "#FF9FE9", 140, 0)
    assert visible == {right}
    assert chart.create_line.call_args.args == (25, 30, 55, 140)


def test_new_crowded_turn_waits_until_the_chart_has_room():
    peaks = [RidgePeak(n, 0, 0, 0, 0, "ground") for n in range(4)]
    chart = Mock(panel="#18112E")
    earlier = [(0, 60, peaks[1]), (12, 35, peaks[2]), (24, 80, peaks[3])]
    old = ResourceUsage._draw_ridge(chart, earlier, "#FF9FE9", 120, 0)
    shifted = [(0, 35, peaks[0])] + [(x + 12, y, p) for x, y, p in earlier]
    assert ResourceUsage._draw_ridge(chart, shifted, "#FF9FE9", 120, 1, old) == {peaks[2]}
    wider = [(3 * x, y, p) for x, y, p in shifted]
    assert ResourceUsage._draw_ridge(chart, wider, "#FF9FE9", 120, 2, old) == {peaks[1], peaks[2]}


def test_whole_ridges_keep_clearance_at_different_chart_sizes():
    rng = Random(2301)
    shapes_drawn = set()
    for width in (180, 420, 860, 1600):
        for floor in (73, 220):
            for frame in range(12):
                path = [(i * width / 71, rng.uniform(33, floor - 10),
                         RidgePeak(6, 3, 2, i, rng.uniform(-1, 1), rng.choice(("ground", "triangle", "fork"))))
                        for i in range(72)]
                chart = Mock(panel="#18112E")
                ResourceUsage._draw_ridge(chart, path, "#FF9FE9", floor, frame)
                groups = []
                for stroke in chart.create_line.call_args_list:
                    tag = stroke.kwargs["tags"][-1]
                    shapes_drawn.add(tag)
                    if tag != "ridge-fork":
                        groups.append([])
                    groups[-1].extend(stroke.args[::2])
                assert groups
                spans = sorted((min(xs), max(xs)) for xs in groups)
                assert all(right[0] - left[1] >= 6 - 1e-8 for left, right in zip(spans, spans[1:]))
                if width == 180:
                    assert len(groups) <= 11
    assert {"ground", "ridge-link", "ridge-fork"} <= shapes_drawn


def test_short_ridges_go_to_ground_even_with_a_neighbor():
    for shape in ("fork", "triangle", "ground"):
        peak = RidgePeak(6, 0, 0, 0, 0, shape)
        path = [(0, 74, peak), (20, 69, peak), (40, 75, peak), (60, 68, peak)]
        chart = Mock(panel="#18112E")
        ResourceUsage._draw_ridge(chart, path, "#FF9FE9", 83, 0)
        assert all(not line.kwargs.get("smooth") for line in chart.create_line.call_args_list)
        assert [line.args for line in chart.create_line.call_args_list] == [
            (20, 69, 20, 83), (40, 75, 40, 83)]


def test_ground_strokes_keep_their_signed_slope_and_fit_the_plot():
    for tilt in (-1., -.4, 0., .6, 1.):
        peak = RidgePeak(6, 0, 0, 0, tilt, "ground")
        path = [(0, 60, peak), (60, 40, peak), (100, 60, peak)]
        for floor in (80, 160):
            chart = Mock(panel="#18112E")
            for now in (0, 15):
                ResourceUsage._draw_ridge(chart, path, "#FF9FE9", floor, now)
                line = chart.create_line.call_args
                assert line.args == (60, 40, max(0, min(100, 60 + (floor - 40) * .75 * tilt)), floor)
                assert not line.kwargs.get("smooth")


def test_qualified_fork_has_one_joint_and_two_feet_on_the_ground():
    peak = RidgePeak(6, 0, 0, 0, 0, "fork")
    path = [(0, 45, peak), (20, 32, peak), (40, 45, peak)]
    chart = Mock(panel="#18112E")
    ResourceUsage._draw_ridge(chart, path, "#FF9FE9", 83, 0)
    trunk, fork = [line.args for line in chart.create_line.call_args_list]
    assert fork[2:4] == trunk[-2:]
    assert fork[0] < trunk[0] < fork[-2]
    assert fork[1] == fork[-1] == 83


@pytest.mark.parametrize("shape", ["ground", "fork", "triangle"])
def test_decoration_fits_under_the_outline_for_its_entire_length(shape):
    floor = 180
    profiles = [
        [(0, 130), (4, 35), (6, 170), (44, 42), (49, 160), (55, 50)],
        [(0, 150), (5, 50), (6, 60), (9, 70), (40, 80), (45, 90), (50, 40)],
    ]
    for points in profiles:
        xs = [x for x, _ in points]
        for tilt in (-1, 0, 1):
            peak = RidgePeak(5, 3, 2, 0, tilt, shape)
            path = [(x, y, peak) for x, y in points]
            chart = Mock(panel="#18112E")
            ResourceUsage._draw_ridge(chart, path, "#FF9FE9", floor, 3)
            assert chart.create_line.called
            for line in chart.create_line.call_args_list:
                vertices = list(zip(line.args[::2], line.args[1::2]))
                for (u, v), (w, z) in zip(vertices, vertices[1:]):
                    assert xs[0] <= min(u, w) <= max(u, w) <= xs[-1]
                    # Between any two vertices both functions are linear.
                    probes = [(u, v), (w, z)]
                    probes.extend((x, v + (z - v) * (x - u) / (w - u))
                                  for x in xs if min(u, w) < x < max(u, w))
                    for x, y in probes:
                        i = min(bisect_right(xs, x) - 1, len(xs) - 2)
                        (a, b), (c, d) = points[i:i + 2]
                        ceiling = b + (d - b) * (x - a) / (c - a)
                        assert ceiling - 1e-8 <= y <= floor


def test_chart_style_is_theme_specific_and_preserves_custom_selection():
    from nkc_galgame_translator.themes import chart_style, validate_theme

    assert chart_style({}) == "line"
    for name in ("custom", "neon", "nishokuchou", "modern_windows", "system"):
        assert chart_style({"interface_theme": name}) == "line"
        assert chart_style({"interface_theme": name, "chart_styles": {name: "mountains"}}) == "mountains"
    for name in ("nishokuchou", "modern_windows", "system"):
        assert chart_style({"interface_theme": name, "custom_chart_style": "mountains"}) == "line"
    for style in ("line", "mountains"):
        assert chart_style(validate_theme({"interface_theme": "custom", "custom_chart_style": style})) == style


@pytest.mark.parametrize("show_gpu", [False, True])
@pytest.mark.parametrize("style", ["line", "mountains"])
def test_only_utilization_can_render_ridges(show_gpu, style):
    chart = Mock(show_gpu=show_gpu, chart_style=style, panel="#18112E", text_color="#FFFFFF",
                 background_size=(600, 160), lines=("#1234AB", "#F071AF"))
    chart.winfo_width.return_value = 600
    chart.winfo_height.return_value = 160
    chart.bbox.side_effect = [(17, 10, 65, 20)] * 2 + [(525, 10, 583, 20)] * 2
    chart.translate.side_effect = str
    chart._draw_ridge.side_effect = lambda *args: ResourceUsage._draw_ridge(chart, *args)
    chart.cpu, chart.gpu = SessionSamples(), SessionSamples()
    active = chart.gpu if show_gpu else chart.cpu
    for t, pair in enumerate([(10, 900), (30, 700), (5, 850), (40, 600)]):
        record_pair(active, t, pair)

    ResourceUsage.draw(chart, now=4)

    lines = [call.kwargs for call in chart.create_line.call_args_list]
    assert [line["fill"] for line in lines if "data-line" in line["tags"]] == list(chart.lines)
    ridges = [line["fill"] for line in lines if any(tag.startswith("ridge") for tag in line["tags"])]
    expected = {mix(chart.panel, chart.lines[0], .76)} if style == "mountains" else set()
    assert set(ridges) == expected
