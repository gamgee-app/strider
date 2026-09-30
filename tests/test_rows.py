"""The report can draw the line between the same picture and another
picture for itself, from how far apart the comparison found the frames."""

from movie_edition_comparer.compare_hashes import Difference, Frames, Move, Row, report


def rows_of(item, within=None):
    return [(r.kind, r.a.start, r.a.count, r.b.start, r.b.count, r.bits_apart) for r in Row.of(item, within)]


def test_a_row_says_how_far_apart_its_sides_are():
    stretch = Difference(Frames(10, 9), Frames(20, 9), "reencoded", ((3, 1), (2, 7), (4, 2)))
    assert rows_of(stretch) == [("reencoded", 10, 9, 20, 9, 7)]


def test_a_re_encoding_further_apart_than_the_line_is_a_replacement_for_that_stretch():
    stretch = Difference(Frames(10, 9), Frames(20, 9), "reencoded", ((3, 1), (2, 7), (4, 2)))
    assert rows_of(stretch, within=5) == [
        ("reencoded", 10, 3, 20, 3, 1),
        ("replaced", 13, 2, 23, 2, 7),
        ("reencoded", 15, 4, 25, 4, 2),
    ]
    assert rows_of(stretch, within=7) == [("reencoded", 10, 9, 20, 9, 7)]
    assert rows_of(stretch, within=0) == [("replaced", 10, 9, 20, 9, 7)]


def test_a_replacement_of_the_same_length_within_the_line_is_a_re_encoding():
    alike = Difference(Frames(10, 5), Frames(20, 5), "replaced", ((5, 3),))
    assert rows_of(alike, within=5) == [("reencoded", 10, 5, 20, 5, 3)]
    assert rows_of(alike, within=2) == [("replaced", 10, 5, 20, 5, 3)]
    assert rows_of(alike) == [("replaced", 10, 5, 20, 5, 3)]


def test_what_cannot_be_laid_side_by_side_is_left_as_it_was():
    unequal = Difference(Frames(10, 5), Frames(20, 8), "replaced")
    retimed = Difference(Frames(10, 2), Frames(20, 3), "retimed", ((2, 1),))
    added = Difference(Frames(10, 0), Frames(20, 8), "added")
    assert rows_of(unequal, within=100) == [("replaced", 10, 5, 20, 8, None)]
    assert rows_of(retimed, within=0) == [("retimed", 10, 2, 20, 3, 1)]
    assert rows_of(added, within=0) == [("added", 10, 0, 20, 8, None)]
    assert rows_of(Move(4, 10, 20), within=0) == [("moved", 10, 4, 20, 4, None)]


def test_the_report_keeps_every_frame_whichever_line_is_drawn():
    reported = [Difference(Frames(10, 9), Frames(20, 9), "reencoded", ((3, 1), (2, 7), (4, 2))),
                Difference(Frames(30, 5), Frames(40, 5), "replaced", ((5, 3),))]
    for within in (None, 0, 3, 5, 9):
        rows = report(reported, within)
        assert sum(r.a.count for r in rows) == 14 and sum(r.b.count for r in rows) == 14


def test_rows_that_touch_and_are_now_one_kind_are_one_row():
    reported = [Difference(Frames(10, 2), Frames(20, 2), "reencoded", ((2, 4),)),
                Difference(Frames(12, 1), Frames(22, 1), "replaced", ((1, 7),)),
                Difference(Frames(13, 3), Frames(23, 3), "reencoded", ((3, 2),))]
    at_five = [(r.kind, r.a.start, r.a.count, r.bits_apart) for r in report(reported, 5)]
    assert at_five == [("replaced", 12, 1, 7), ("reencoded", 10, 2, 4), ("reencoded", 13, 3, 2)]
    at_eight = [(r.kind, r.a.start, r.a.count, r.bits_apart) for r in report(reported, 8)]
    assert at_eight == [("reencoded", 10, 6, 7)]
