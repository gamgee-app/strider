"""The scenarios.

Two editions of a film as strings of letters. A letter is one frame; the same
letter in both editions is the same frame. Each scenario says outright what the
differences between its two editions are.

A letter may appear more than once. Repeated letters are frames that look
exactly alike -- black between scenes, a fade, a held frame, a static shot.
They are common in a real film, and nothing about them makes them a difference.
"""

from tests.scenarios.editions import Added, Gone, Relocated, Replaced, Scenario

CATALOGUE = [

    Scenario(
        name="identical editions",
        story="Nothing to report.",
        edition_a="abcde",
        edition_b="abcde",
        expect=[],
    ),

    Scenario(
        name="footage only edition_b has",
        story="X is in edition_b and nowhere in edition_a.",
        edition_a="abc",
        edition_b="aXbc",
        expect=[Added("X")],
    ),

    Scenario(
        name="footage only edition_a has",
        story="b is in edition_a and nowhere in edition_b.",
        edition_a="abc",
        edition_b="ac",
        expect=[Gone("b")],
    ),

    Scenario(
        name="footage replaced by more",
        story="b is gone; X and Y stand where it was.",
        edition_a="abc",
        edition_b="aXYc",
        expect=[Replaced("b", "XY")],
    ),

    Scenario(
        name="footage replaced by less",
        story="b and c are gone; X stands where they were.",
        edition_a="abcd",
        edition_b="aXd",
        expect=[Replaced("bc", "X")],
    ),

    Scenario(
        name="footage replaced by the same amount",
        story="X stands where b was.",
        edition_a="abc",
        edition_b="aXc",
        expect=[Replaced("b", "X")],
    ),

    Scenario(
        name="several separate additions",
        story="X, Y and Z are added at three points.",
        edition_a="abcd",
        edition_b="aXbYcZd",
        expect=[Added("X"), Added("Y"), Added("Z")],
    ),

    Scenario(
        name="two touching frames swapped",
        story="b and c trade places. Either could be called the one that "
              "stayed, so both moved.",
        edition_a="abcd",
        edition_b="acbd",
        expect=[Relocated("b"), Relocated("c")],
    ),

    Scenario(
        name="two separated frames swapped",
        story="b and d trade places across c, which does not move.",
        edition_a="abcde",
        edition_b="adcbe",
        expect=[Relocated("b"), Relocated("d")],
    ),

    Scenario(
        name="footage dropped beside footage moved",
        story="c is gone and b and d trade places, with nothing unchanged "
              "between the two changes.",
        edition_a="abcde",
        edition_b="adbe",
        expect=[Relocated("b"), Relocated("d"), Gone("c")],
    ),

    Scenario(
        name="one piece of footage relocated",
        story="b turns up later, after c and d.",
        edition_a="abcd",
        edition_b="acdb",
        expect=[Relocated("b")],
    ),

    Scenario(
        name="the editions share nothing",
        story="No frame of edition_a is in edition_b.",
        edition_a="abc",
        edition_b="XYZ",
        expect=[Replaced("abc", "XYZ")],
    ),

    Scenario(
        name="an addition at the very start",
        story="X is before anything the editions share.",
        edition_a="abc",
        edition_b="Xabc",
        expect=[Added("X")],
    ),

    Scenario(
        name="an addition at the very end",
        story="X is after anything the editions share.",
        edition_a="abc",
        edition_b="abcX",
        expect=[Added("X")],
    ),

    Scenario(
        name="footage only edition_a has, at the very start",
        story="X is before anything the editions share.",
        edition_a="Xabc",
        edition_b="abc",
        expect=[Gone("X")],
    ),

    Scenario(
        name="footage only edition_a has, at the very end",
        story="X is after anything the editions share.",
        edition_a="abcX",
        edition_b="abc",
        expect=[Gone("X")],
    ),

    Scenario(
        name="back-to-back differences",
        story="Two differences held apart by one shared frame, b.",
        edition_a="abcd",
        edition_b="aXbYZd",
        expect=[Added("X"), Replaced("c", "YZ")],
    ),

    Scenario(
        name="identical frames in a row",
        story="b runs twice in both editions.",
        edition_a="abbc",
        edition_b="abbc",
        expect=[],
    ),

    Scenario(
        name="identical frames apart",
        story="b appears twice in both editions, with c between.",
        edition_a="abcb",
        edition_b="abcb",
        expect=[],
    ),

    Scenario(
        name="a run of identical frames grows",
        story="b runs twice in edition_a and three times in edition_b. Which "
              "of the three is the extra one cannot be said, so the run is "
              "the smallest thing there is to point at.",
        edition_a="abbc",
        edition_b="abbbc",
        expect=[Replaced("bb", "bbb")],
    ),

    Scenario(
        name="a frame becomes two identical frames",
        story="b appears once in edition_a and twice over in edition_b.",
        edition_a="abc",
        edition_b="abbc",
        expect=[Replaced("b", "bb")],
    ),

    Scenario(
        name="one of two identical frames is gone",
        story="b appears twice in edition_a, with c between, and once in "
              "edition_b. The run that is gone is the one after c.",
        edition_a="abcb",
        edition_b="abc",
        expect=[Gone("b", nth=2)],
    ),
]
