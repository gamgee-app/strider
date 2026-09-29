"""The scenarios.

Each names one property of comparing two editions of a film, and holds the
cases that exercise it. An edition is a string of letters and a letter is one
frame, so a case is two strings and what should be reported between them.

The same token is the same frame. Two tokens sharing a letter are two
renderings of one picture: b and B are that picture encoded twice, so their
pixels differ while the picture does not, and b' is a rendering a bit apart to
look at as well. Frames of the same footage across two transfers of a film were
measured nought to ten bits apart, most of them nought -- so a difference in
the pixels with none in the picture is the ordinary case between two editions,
not a curiosity.

A letter may appear more than once. Repeated letters are frames that look
exactly alike -- black between scenes, a fade, a held frame, a static shot.

The first case of a scenario is the smallest that shows the property. Every
case after it says in its note what it adds.
"""

from tests.scenarios.editions import (
    Added, Case, Reencoded, Relocated, Removed, Replaced, Retimed, Scenario,
)

CATALOGUE = [

    Scenario(
        name="identical editions",
        story="Two editions holding the same frames. There is nothing to report, "
              "however many frames they hold.",
        cases=[
            Case("a", "a", [], "one frame"),
            Case("ab", "ab", [], "two frames"),
            Case("abc", "abc", [], "three frames"),
        ],
    ),

    Scenario(
        name="frames are added",
        story="Footage in the second edition that the first does not have.",
        cases=[
            Case("ab", "axb", [Added("x")], "between two frames"),
            Case("ab", "xab", [Added("x")], "before everything shared"),
            Case("ab", "abx", [Added("x")], "after everything shared"),
            Case("abc", "axbyc", [Added("x"), Added("y")], "two of them, separately"),
        ],
    ),

    Scenario(
        name="frames are removed",
        story="Footage in the first edition that the second does not have.",
        cases=[
            Case("axb", "ab", [Removed("x")], "between two frames"),
            Case("xab", "ab", [Removed("x")], "before everything shared"),
            Case("abx", "ab", [Removed("x")], "after everything shared"),
            Case("axbyc", "abc", [Removed("x"), Removed("y")], "two of them, separately"),
        ],
    ),

    Scenario(
        name="frames are replaced",
        story="Footage standing where other footage was.",
        cases=[
            Case("axb", "ayb", [Replaced("x", "y")], "by as many frames"),
            Case("axb", "ayzb", [Replaced("x", "yz")], "by more frames"),
            Case("axyb", "azb", [Replaced("xy", "z")], "by fewer frames"),
            Case("xa", "ya", [Replaced("x", "y")], "before everything shared"),
            Case("ax", "ay", [Replaced("x", "y")], "after everything shared"),
            Case("a", "x", [Replaced("a", "x")], "the editions share no frame at all"),
        ],
    ),

    Scenario(
        name="editions with nothing in common",
        story="Two editions holding no footage in common, including where one "
              "of them holds no footage at all. One difference covering "
              "whatever each edition has, not one for every frame.",
        cases=[
            Case("abc", "xyz", [Replaced("abc", "xyz")], "neither edition's footage is the other's"),
            Case("", "abc", [Added("abc")], "the first edition is empty"),
            Case("abc", "", [Removed("abc")], "the second edition is empty"),
        ],
    ),

    Scenario(
        name="frames are moved",
        story="Footage in both editions, in a different place in each.",
        cases=[
            Case("abc", "acb", [Relocated("b"), Relocated("c")],
                 "two touching frames trade places"),
            Case("abcd", "acdb", [Relocated("b")], "one frame, to later in the film"),
            Case("abc", "cab", [Relocated("c")], "one frame, to the very start"),
            Case("abcde", "adcbe", [Relocated("b"), Relocated("d")],
                 "two frames trade places across one that stays"),
            Case("abcdef", "adefbc", [Relocated("bc")], "a run of two frames"),
        ],
    ),

    Scenario(
        name="frames that look exactly alike",
        story="Frames indistinguishable from one another -- black between "
              "scenes, a fade, a held frame, a static shot.",
        cases=[
            Case("abbc", "abbc", [], "a run of them, unchanged"),
            Case("abcb", "abcb", [], "two of them apart, unchanged"),
            Case("abc", "abbc", [Retimed("b", "bb")], "one frame becomes two"),
            Case("abbc", "abc", [Retimed("bb", "b")], "two frames become one"),
            Case("abcb", "abc", [Removed("b", nth=2)], "one of two apart is removed"),
            Case("abc", "abcb", [Added("b", nth=2)], "a second one apart is added"),
            Case("abbc", "acbb", [Relocated("bb"), Relocated("c")],
                 "a run of them moves, and the frame it traded places with"),
        ],
    ),

    Scenario(
        name="renderings of one picture",
        story="One picture encoded more than once. The pixels differ; the "
              "picture need not. Two editions of a film are separate transfers, "
              "so this is the ordinary state of the footage they share, and it "
              "has to hold alongside every other kind of difference rather than "
              "only on its own.",
        cases=[
            Case("ab", "aB", [Reencoded("b", "B")], "one frame re-encoded"),
            Case("ab", "AB", [Reencoded("a", "A"), Reencoded("b", "B")],
                 "every frame re-encoded"),
            Case("ab", "ab'", [Reencoded("b", "b'")], "re-encoded and a bit apart to look at"),
            Case("ab", "ab'b", [Added("b'")], "a second rendering beside the one it copies"),
            Case("ab", "AxB", [Reencoded("a", "A"), Added("x"), Reencoded("b", "B")],
                 "every frame re-encoded, and a frame added"),
            Case("axb", "AB", [Reencoded("a", "A"), Removed("x"), Reencoded("b", "B")],
                 "every frame re-encoded, and a frame removed"),
            Case("axb", "AyB", [Reencoded("a", "A"), Replaced("x", "y"), Reencoded("b", "B")],
                 "every frame re-encoded, and a frame replaced"),
            Case("abc", "Acb", [Reencoded("a", "A"), Relocated("b"), Relocated("c")],
                 "two frames trade places, and one that stays is re-encoded"),
            Case("abcd", "acdB", [Relocated("b", becomes="B")],
                 "a frame moves and is re-encoded on the way"),
            Case("abbc", "aBBc", [Reencoded("bb", "BB")],
                 "frames that look exactly alike, re-encoded"),
            Case("abc", "Ab'c", [Reencoded("a", "A"), Reencoded("b", "b'")],
                 "one frame re-encoded, its neighbour a bit apart as well"),
            Case("ab", "ab'b''", [Reencoded("b", "b'"), Added("b''")],
                 "two renderings, with nothing to choose between them but where they sit"),
            Case("abcb", "abcB", [Reencoded("b", "B", a_nth=2)],
                 "one of two apart is re-encoded"),
        ],
    ),

    Scenario(
        name="more than one difference at once",
        story="Differences that have to stay apart rather than merging into one.",
        cases=[
            Case("abcd", "axbd", [Added("x"), Removed("c")], "an addition and a removal"),
            Case("abcd", "axbyzd", [Added("x"), Replaced("c", "yz")],
                 "two differences, one shared frame apart"),
            Case("abcde", "adbe", [Relocated("b"), Relocated("d"), Removed("c")],
                 "a removal touching a swap"),
            Case("axxbye", "aeb",
                 [Removed("xx"), Relocated("b"), Removed("y"), Relocated("e")],
                 "two removals with footage that moved standing between them"),
        ],
    ),
]
