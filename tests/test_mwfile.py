"""Werkbladen lezen/schrijven. Alleen eigen synthetische fixtures (tests/fixtures)."""
from pathlib import Path

import pytest

from minimaple import mwfile

FX = Path(__file__).parent / "fixtures"


def test_sectioned_mw():
    r = mwfile.parse_mw((FX / "sectioned.mw").read_bytes())
    g = r["groups"]
    assert [x["type"] for x in g] == ["text", "input", "text", "input", "text", "input"]
    assert g[0]["code"] == "# Oefening 1"
    assert g[1]["code"] == "restart:"
    assert g[2]["code"] == "Cirkel met r=2 en een café."          # 2D-math benaderd + octale UTF-8
    assert g[3]["code"] == "f := x -> x^2*sin(x);\nint(f(x), x = 0 .. Pi);"   # 2 Inputs = 1 groep
    assert "oude uitvoer" not in str(g)                              # Output genegeerd
    assert g[4]["code"] == "## Deel b"
    assert g[5]["code"] == 'if a < 1 then "klein" else "groot" end if;'
    w = " ".join(r["warnings"])
    assert "2D" in w and "plot" in w


def test_flat_mw_merges_text():
    g = mwfile.parse_mw((FX / "flat.mw").read_bytes())["groups"]
    assert g[0] == {"type": "text", "code": "# Titel\n\nEerste alinea.\n\nTweede alinea."}
    assert g[1] == {"type": "input", "code": "with(plots):\nplot(sin(x), x = -Pi..Pi);"}


def test_mpl_split():
    g = mwfile.parse_mpl((FX / "sample.mpl").read_text())["groups"]
    assert g[0] == {"type": "text", "code": "Kop\nuitleg over f"}
    assert g[1]["type"] == "input" and g[1]["code"].startswith("f := proc(n)") and g[1]["code"].endswith("end proc:")
    assert "\n\n" in g[1]["code"]                     # lege regel binnen proc splitst niet
    assert g[2]["code"] == "f(3);\ng := 1 +\n  2;"
    assert g[3]["code"] == "h := 5"
    assert len(g) == 4


def test_unfinished_statement_does_not_split():
    g = mwfile.parse_mpl("a := 1 +\n\n2;\n\nb;")["groups"]
    assert [x["code"] for x in g] == ["a := 1 +\n\n2;", "b;"]


def test_roundtrip_mw_and_mpl():
    groups = [{"type": "text", "code": "# Kop\n\nTekst met <tags> & \"quotes\""},
              {"type": "input", "code": "x := 3;\ny := x < 4"},
              {"type": "input", "code": "plot(x^2, x = 0..1):"}]
    back = mwfile.parse_mw(mwfile.to_mw(groups))["groups"]
    assert back == groups
    back = mwfile.parse_mpl(mwfile.to_mpl(groups))["groups"]
    assert back[0] == groups[0]
    assert [x["code"] for x in back[1:]] == ["x := 3;\ny := x < 4;", "plot(x^2, x = 0..1):"]


def test_parse_file_dispatch_and_errors():
    assert mwfile.parse_file("a.mpl", b"1+1;")["groups"] == [{"type": "input", "code": "1+1;"}]
    assert mwfile.parse_file("a.txt", b"1+1;")["groups"][0]["type"] == "input"
    with pytest.raises(mwfile.WorksheetError):
        mwfile.parse_file("a.mw", b"<Worksheet><Group>")
    with pytest.raises(mwfile.WorksheetError):
        mwfile.parse_file("a.mw", b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Worksheet/>')
    with pytest.raises(mwfile.WorksheetError):
        mwfile.parse_file("a.mw", b"<Other/>")
    with pytest.raises(mwfile.WorksheetError):
        mwfile.parse_file("a.png", b"\x89PNG")
    with pytest.raises(mwfile.WorksheetError):
        mwfile.parse_file("a.mpl", b"x" * (mwfile.MAX_BYTES + 1))
