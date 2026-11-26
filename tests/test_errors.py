"""Ongeldige argumenttypes geven een Maple-achtige fout, nooit een stil leeg resultaat."""
import pytest

from minimaple.interp import Interpreter


def run(code):
    it = Interpreter()
    return it.run(code)


def last(code):
    return run(code)[-1]


@pytest.mark.parametrize("code, needle", [
    # strijdige Vector-vergelijking: zichtbare fout (geen stille NULL)
    ("A := Matrix([[1,2],[3,4],[5,6]]): yv := Vector([1,2,4]): solve(A.(<v0, -g/2>)=yv, {v0,g});",
     "(in solve) inconsistent system"),
    ("solve(<a, b> = <1, 2, 3>, {a, b});", "must have the same dimensions"),
    ("solve(<a, b> = Matrix([[1, 2]]), {a, b});", "(in solve) invalid input"),
    ("solve(Matrix([[1,2],[3,4]]), x);", "(in solve) invalid input"),
    ("fsolve(<x^2-2>, x);", "(in fsolve) invalid input"),
    ("solve(\"abc\", x);", "solve received \"abc\""),
    ("solve(x^2 - 1, 3);", "not valid for its 2nd argument"),
    ("solve(x^2 - 1, \"x\");", "not valid for its 2nd argument"),
    ("isolate(<x> = <1>, x);", "(in isolate) invalid input"),
    ("dsolve(<diff(y(x), x)> = <y(x)>, y(x));", "(in dsolve) invalid input"),
    ("dsolve(diff(y(x), x) = y(x), 3);", "(in dsolve) invalid input"),
    ("int(\"a\", x);", "int received \"a\""),
    ("int(x^2, 5);", "not valid for its 2nd argument"),
    ("diff(\"s\", x);", "invalid input: diff received \"s\""),
    ("diff(x^2, 2);", "diff received 2, which is not valid for its 2nd argument"),
    ("limit(\"q\", x = 0);", "(in limit) invalid input"),
    ("series(\"q\", x = 0);", "(in series) invalid input"),
])
def test_invalid_arguments_raise(code, needle):
    r = last(code)
    assert r["error"] is not None, f"geen fout voor {code!r}: {r['text']!r}"
    assert needle in r["error"], r["error"]


@pytest.mark.parametrize("code, text", [
    ("solve(x = x + 1, x);", ""),                                  # Maple: NULL (geen oplossing)
    ("solve({x + y = 1, x + y = 2}, {x, y});", ""),                # strijdig stelsel: NULL
    ("with(LinearAlgebra): solve(Equate(<a, b>, <1, 2>), {a, b});", "{a = 1, b = 2}"),
    # Vector/Matrix-vergelijkingen worden per component opgelost (normaalvergelijkingen)
    ("solve(<a, b> = <1, 2>, {a, b});", "{a = 1, b = 2}"),
    ("A := Matrix([[1,2],[3,4],[5,6]]): yv := <1,2,4>: solve((A^%T.A).(<v0,-g/2>) = A^%T.yv, {v0, g});",
     "{v0 = 2/3, g = -1/6}"),
    ("solve(Matrix([[a, b], [c, 1]]) = Matrix([[1, 2], [3, 1]]), {a, b, c});", "{a = 1, b = 2, c = 3}"),
    ("fsolve(<x^2> = <2>, x = 1..2);", "1.414213562"),
    ("A := Matrix([[1,2],[3,4],[5,6]]): solve(LinearAlgebra:-Equate(A.<v0, -g/2>, <1, 2, 3>), {v0, g});",
     "{g = -1, v0 = 0}"),
    ("int(<x, 1>, x);", "[x^2/2]\n[    x]"),                        # int/diff mogen een Vector afbeelden
    ("diff([x^2, x^3], x);", "[2*x, 3*x^2]"),
    ("diff(x^3, x$2);", "6*x"),
    ("int(x, x = 0..1);", "1/2"),
    ("series(sin(x), x = 0, 4);", "x - x^3/6 + O(x^4)"),
    ("fsolve(x^2 = 2, x = 1..2);", "1.414213562"),
])
def test_valid_arguments_still_work(code, text):
    r = last(code)
    assert r["error"] is None, r["error"]
    if text == "{g = -1, v0 = 0}":
        assert r["text"] in ("{g = -1, v0 = 0}", "{v0 = 0, g = -1}")
    else:
        assert r["text"] == text
