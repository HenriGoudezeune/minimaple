"""Maple-taalconstructies (synthetische voorbeelden; geen cursusmateriaal)."""
import pytest

from minimaple.interp import Interpreter


def outs(code):
    it = Interpreter()
    res = it.run(code)
    errs = [r["error"] for r in res if r["error"]]
    assert not errs, errs
    return [r["text"] for r in res if r["show"] and r["text"] != ""]


def last(code):
    return outs(code)[-1]


def err(code):
    res = Interpreter().run(code)
    e = [r["error"] for r in res if r["error"]]
    assert e, [r["text"] for r in res]
    return e[-1]


CASES = [
    # modules
    ("M := module() export f, g; local a; option package; a := 3; f := x -> a*x; "
     "g := proc(y) y + a end proc; end module: M:-f(2), M:-g(1);", "6, 4"),
    ("M := module() export f; local a := 10; f := () -> a; end module: with(M): f();", "10"),
    ("M := module() export f; f := x -> 2*x; end module: use M in f(10) end use;", "20"),
    ("C := module() local n := 0; export inc; inc := proc() n := n + 1 end proc; end module: "
     "C:-inc(): C:-inc(): C:-inc();", "3"),
    ("M := module() export ModuleApply; ModuleApply := x -> x^2 end module: M(5);", "25"),
    ("use StringTools in Length(\"abcd\") end use;", "4"),
    ("use a = 5, b = 7 in a*b end use;", "35"),
    # elementsgewijze operatoren
    ("[1,2,3] ^~ 2;", "[1, 4, 9]"),
    ("[1,2] +~ [10,20];", "[11, 22]"),
    ("[1,2] *~ 3, 10 -~ [1,2], [4,6] /~ 2;", "[3, 6], [9, 8], [2, 3]"),
    ("f := x -> x^2: f~([1,2,3]);", "[1, 4, 9]"),
    ("[1,2,3] =~ [1,5,3];", "[1 = 1, 2 = 5, 3 = 3]"),
    ("sin~([0, Pi/2]);", "[0, 1]"),
    # parameters
    ("p := proc(a, b:=5) a+b end proc: p(1), p(1,2);", "6, 3"),
    ("p := proc(a, {k:=1}) a*k end proc: p(2), p(2, k=10);", "2, 20"),
    ("q := proc(x, y::integer := 3, {opt::truefalse := false}) [x, y, opt] end proc: "
     "q(1), q(1, 5), q(1, opt = true), q(1, opt), q(1, 2.5);",
     "[1, 3, false], [1, 5, false], [1, 3, true], [1, 3, true], [1, 3, false]"),
    ("p := proc(n::posint:=4) n! end proc: p(), p(3);", "24, 6"),
    ("p := proc() nargs, [args] end proc: p(1,2,3);", "3, [1, 2, 3]"),
    ("p := proc(a) [_rest] end proc: p(1,2,3);", "[2, 3]"),
    ("p := proc(n) if n<=1 then 1 else n*procname(n-1) end if end proc: p(5);", "120"),
    ("p := proc(x) if not type(x, numeric) then return 'procname'(x) end if; x^2 end proc: p(3), p(z);",
     "9, p(z)"),
    ("p := proc() local r := 7; r end proc: p();", "7"),
    ("f := (X) -> X + 1: f(2);", "3"),
    # types
    ("type(3, posint), type(-3, posint), type(x, name), type([1,2], list(integer)), type(2.5, float), "
     "type(1/2, rational), type(x+1, `+`);", "true, false, true, true, true, true, true"),
    # foutafhandeling
    ("try error \"boom %1\", 3 catch \"boom\": lastexception[2], lasterror end try;", "\"boom %1\", \"boom 3\""),
    ("f := proc() error \"bad: %1\", 5 end proc: try f() catch: lastexception[1], "
     "StringTools:-FormatMessage(lastexception[2..-1]) end try;", "f, \"bad: 5\""),
    ("try try error \"in\" catch: error end try catch: lasterror end try;", "\"in\""),
    ("r := 0: try r := 1 finally r := r + 10 end try: r;", "11"),
    # operatoren als functies, subsop, evaln
    ("`+`(1,2,3), `*`(2,3), `if`(true,1,2), `if`(1>2, 1/0, 3), `union`({1},{2});", "6, 6, 1, 3, {1, 2}"),
    ("e := x^2+1: subsop(2=y, e), subsop(2=NULL, [1,2,3]), subsop(0=g, f(1,2)), op(0, f(1,2));",
     "x^2 + y, [1, 3], g(1, 2), f"),
    ("x := 3: evaln(x), eval(x);", "x, 3"),
    # last-name evaluation / operatoralgebra
    ("f := x->x^2: g := x->x+1: h := f+g: h, h(2), (2*f)(3);", "f + g, 7, 18"),
    ("p := (T,v) -> T*v: e1 := 1/p + p*E: coeff(e1, p);", "E"),
    # StringTools / ListTools
    ("with(StringTools): Length(\"hello\"), SubString(\"hello\", 2..4), Split(\"a,b,c\", \",\"), "
     "Join([\"a\",\"b\"], \"-\"), Search(\"ll\", \"hello\"), UpperCase(\"ab\");",
     "5, \"ell\", [\"a\", \"b\", \"c\"], \"a-b\", 3, \"AB\""),
    ("with(ListTools): Reverse([1,2,3]), Flatten([[1,[2]],3]), MakeUnique([1,1,2]), Search(2,[1,2]), "
     "PartialSums([1,2,3]);", "[3, 2, 1], [1, 2, 3], [1, 2], 2, [1, 3, 6]"),
    ("cat(a, 1, \"x\"), cat(\"x\", 1);", "a1x, \"x1\""),
    ("upperbound(<1,2,3>), upperbound(Matrix(2,3), 2), lowerbound([1,2]);", "3, 3, 1"),
    # commentaar en afsluiters
    ("(* blok\n commentaar *) 3; # regel\n", "3"),
    ("if 1<2 then 7 fi;", "7"),
    ("proc(x) x^2 end(4);", "16"),
    ("p := proc(a, b) local r; r := a + b; r end: p(2,3);", "5"),
]


@pytest.mark.parametrize("code, expected", CASES)
def test_lang(code, expected):
    assert last(code) == expected


def test_dollar_endmarker():
    assert "too many and/or wrong type of arguments" in err("f := proc(x, $) x end proc: f(1,2);")


def test_typed_param_error():
    assert "expects its 1st argument, n, to be of type posint" in err("p := proc(n::posint) n end proc: p(-1);")


def test_module_private_local():
    assert "does not export" in err("M := module() export f; local a; a := 1; f := () -> a end module: M:-a;")
