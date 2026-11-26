import os
import numpy as np
import sympy as sp
import pytest
from minimaple import values as V
from minimaple import plots  # noqa: F401  (registreert builtins)
from minimaple.values import BUILTINS, MList, MSet, Range, Str, Plot

x, y, t, z = sp.symbols("x y t z")


class FakeCtx:
    def __init__(self):
        self.env, self.digits, self.plots = {}, 10, []

    def call(self, f, *a):
        return f(*a)

    def sym(self, n):
        return sp.Symbol(n)


@pytest.fixture
def ctx():
    return FakeCtx()


class REq:
    def __init__(self, lhs, rhs):
        self.lhs, self.rhs = lhs, rhs


def opt(k, v):
    return REq(sp.Symbol(k), v)


def R(var, a, b):
    return REq(var, Range(sp.sympify(a), sp.sympify(b)))


def check(p, tmp_path, name="p.png"):
    assert isinstance(p, Plot)
    path = tmp_path / name
    p.render(str(path))
    assert path.exists() and path.stat().st_size > 2000
    assert path.read_bytes()[:4] == b"\x89PNG"
    return p


def test_sin(ctx, tmp_path):
    p = BUILTINS["plot"](ctx, sp.sin(x), R(x, -sp.pi, sp.pi), opt("color", sp.Symbol("blue")),
                         opt("title", Str("sinus")), opt("legend", Str("sin(x)")))
    check(p, tmp_path)
    ly = p.layers[0]
    assert np.allclose(ly["y"], np.sin(ly["x"]))
    assert ly["color"] == "#1f77b4"


def test_multi_and_callable(ctx, tmp_path):
    p = BUILTINS["plot"](ctx, MList([sp.sin(x), sp.cos(x)]), R(x, 0, 6), opt("legend", MList([Str("s"), Str("c")])))
    assert len(p.layers) == 2
    check(p, tmp_path)
    p = BUILTINS["plot"](ctx, lambda v: v ** 2, Range(sp.Integer(0), sp.Integer(2)))
    check(p, tmp_path, "c.png")
    assert abs(p.layers[0]["y"][-1] - 4) < 1e-9


def test_circle_parametric(ctx, tmp_path):
    p = BUILTINS["plot"](ctx, MList([sp.cos(t), sp.sin(t), R(t, 0, 2 * sp.pi)]), opt("scaling", sp.Symbol("constrained")))
    check(p, tmp_path)
    L = p.layers[0]
    assert np.allclose(L["x"] ** 2 + L["y"] ** 2, 1)


def test_singularities_and_piecewise(ctx, tmp_path):
    p = BUILTINS["plot"](ctx, 1 / x, R(x, -2, 2))
    check(p, tmp_path)
    L = p.layers[0]
    assert np.isnan(L["y"]).any()  # lijn onderbroken bij de pool
    p = BUILTINS["plot"](ctx, sp.sqrt(x), R(x, -1, 1))
    assert np.isnan(p.layers[0]["y"][0])
    check(p, tmp_path, "s.png")
    pw = sp.Piecewise((x, x < 0), (x ** 2, True)) + sp.Heaviside(x)
    check(BUILTINS["plot"](ctx, pw, R(x, -2, 2)), tmp_path, "pw.png")
    check(BUILTINS["plot"](ctx, sp.tan(x), R(x, -5, 5)), tmp_path, "tan.png")


def test_data(ctx, tmp_path):
    pts = MList([MList([1, 2]), MList([2, 4]), MList([3, 5])])
    check(BUILTINS["plot"](ctx, pts, opt("style", sp.Symbol("point"))), tmp_path, "d.png")
    check(BUILTINS["pointplot"](ctx, pts, opt("color", Str("red"))), tmp_path, "pp.png")
    check(BUILTINS["pointplot"](ctx, sp.Matrix([1, 2, 3]), sp.Matrix([2, 3, 5])), tmp_path, "pp2.png")
    check(BUILTINS["listplot"](ctx, MList([1, 4, 9, 16])), tmp_path, "lp.png")
    check(BUILTINS["plot"](ctx, sp.Matrix([[0, 0], [1, 1], [2, 4]])), tmp_path, "m.png")


def test_log_plots(ctx, tmp_path):
    h = sp.Symbol("h")
    hs = MList([sp.Rational(1, 10 ** k) for k in range(1, 6)])
    p = BUILTINS["loglogplot"](ctx, h ** 2, REq(h, hs), opt("legend", Str("h^2")), opt("linestyle", Str("dot")))
    check(p, tmp_path)
    check(BUILTINS["semilogplot"](ctx, sp.exp(x), R(x, 0, 10)), tmp_path, "sl.png")
    check(BUILTINS["logplot"](ctx, x, R(x, 1, 100)), tmp_path, "lg.png")


def test_plot3d(ctx, tmp_path):
    p = BUILTINS["plot3d"](ctx, x ** 2 - y ** 2, R(x, -2, 2), R(y, -2, 2))
    check(p, tmp_path)
    assert p.dim == 3
    u, v = sp.symbols("u v")
    p = BUILTINS["plot3d"](ctx, MList([sp.cos(u) * sp.sin(v), sp.sin(u) * sp.sin(v), sp.cos(v)]), R(u, 0, 2 * sp.pi),
                           R(v, 0, sp.pi), opt("scaling", sp.Symbol("constrained")))
    check(p, tmp_path, "sph.png")
    r, th, ph = sp.symbols("r theta phi")
    check(BUILTINS["plot3d"](ctx, sp.Integer(1), R(th, 0, 2 * sp.pi), R(ph, 0, sp.pi), opt("coords", sp.Symbol("spherical"))),
          tmp_path, "sph2.png")
    check(BUILTINS["plot3d"](ctx, sp.sin(x) * y, R(x, 0, 3), R(y, 0, 3), opt("style", sp.Symbol("wireframe"))),
          tmp_path, "wf.png")
    # vlak als matrixvorm: h*K1+v*K2
    K1, K2 = sp.Matrix([1, 0, 1]), sp.Matrix([0, 1, 1])
    check(BUILTINS["plot3d"](ctx, x * K1 + y * K2, R(x, -1, 1), R(y, -1, 1), opt("color", sp.Symbol("green"))),
          tmp_path, "pl.png")


def test_space_and_points3d(ctx, tmp_path):
    p = BUILTINS["spacecurve"](ctx, MList([sp.cos(t), sp.sin(t), t]), R(t, 0, 6 * sp.pi))
    check(p, tmp_path)
    check(BUILTINS["spacecurve"](ctx, MList([sp.cos(t), sp.sin(t), t, R(t, 0, 6)])), tmp_path, "sc2.png")
    check(BUILTINS["pointplot3d"](ctx, MList([MList([1, 2, 3]), MList([2, 3, 1]), MList([0, 1, 5])])), tmp_path, "p3.png")


def test_fields(ctx, tmp_path):
    p = BUILTINS["fieldplot"](ctx, MList([-y, x]), R(x, -2, 2), R(y, -2, 2))
    check(p, tmp_path)
    L = p.layers[0]
    assert np.allclose(L["U"], -L["Y"])
    check(BUILTINS["fieldplot3d"](ctx, MList([x, y, z]), R(x, -1, 1), R(y, -1, 1), R(z, -1, 1)), tmp_path, "f3.png")
    check(BUILTINS["gradplot"](ctx, x ** 2 + y ** 2, R(x, -1, 1), R(y, -1, 1)), tmp_path, "g.png")
    check(BUILTINS["contourplot"](ctx, x ** 2 + y ** 2, R(x, -2, 2), R(y, -2, 2), opt("filled", sp.Symbol("true"))),
          tmp_path, "c.png")
    check(BUILTINS["contourplot"](ctx, x * y, R(x, -2, 2), R(y, -2, 2), opt("contours", MList([-1, 0, 1]))),
          tmp_path, "c2.png")


def test_implicit(ctx, tmp_path):
    p = BUILTINS["implicitplot"](ctx, sp.Eq(x ** 2 + y ** 2, 1), R(x, -2, 2), R(y, -2, 2),
                                 opt("scaling", sp.Symbol("constrained")))
    check(p, tmp_path)
    check(BUILTINS["implicitplot3d"](ctx, sp.Eq(x ** 2 + y ** 2 + z ** 2, 1), R(x, -1.5, 1.5), R(y, -1.5, 1.5),
                                     R(z, -1.5, 1.5)), tmp_path, "i3.png")


def test_polar_text_display(ctx, tmp_path):
    th = sp.Symbol("theta")
    p1 = BUILTINS["polarplot"](ctx, 1 + sp.cos(th), R(th, 0, 2 * sp.pi))
    check(p1, tmp_path, "pol.png")
    p2 = BUILTINS["plot"](ctx, sp.sin(x), R(x, 0, 3), opt("color", sp.Symbol("red")))
    p3 = BUILTINS["textplot"](ctx, MList([1, 0.5, Str("hallo")]))
    d = BUILTINS["display"](ctx, p2, p3, opt("title", Str("samen")), opt("view", MList([Range(sp.Integer(0), sp.Integer(3)),
                                                                                           Range(sp.Integer(-1), sp.Integer(1))])))
    assert len(d.layers) == 2
    check(d, tmp_path, "disp.png")
    d2 = BUILTINS["display"](ctx, MList([p2, p3]))
    assert len(d2.layers) == 2
    # array van plots -> subplots
    arr = BUILTINS["display"](ctx, MList([MList([p2, p3]), MList([p1, p2])]))
    assert arr.kind == "multi" and arr.opts["shape"] == (2, 2)
    check(arr, tmp_path, "multi.png")


def test_odeplot(ctx, tmp_path):
    yf = sp.Function("y")

    def sol(tv):  # nep-dsolve numeric: y(t)=exp(-t)
        return MList([sp.Eq(t, tv), sp.Eq(yf(t), float(np.exp(-tv)))])

    p = BUILTINS["odeplot"](ctx, sol, MList([t, yf(t)]), R(t, 0, 3))
    check(p, tmp_path)
    assert np.allclose(p.layers[0]["y"], np.exp(-p.layers[0]["x"]))


def test_errors(ctx):
    with pytest.raises(ValueError):
        BUILTINS["plot"](ctx, x * sp.Symbol("a"), R(x, 0, 1))
    assert "plots" in V.PACKAGES and "display" in V.PACKAGES["plots"]
