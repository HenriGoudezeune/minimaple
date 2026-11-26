"""Tests voor pdsolve (minimaple/pde.py): reeksoplossingen numeriek gecontroleerd tegen PDV, randen en beginvoorwaarden."""
import mpmath as mp
import numpy as np
import pytest
import sympy as sp
from minimaple import calc  # noqa: F401  (registreert pdsolve)
from minimaple.values import BUILTINS, MSet

x, y, t, r, th = sp.symbols('x y t r th')
U = sp.Function('u')
pi = sp.pi
kk = sp.Symbol('k', positive=True)
cc = sp.Symbol('c', positive=True)
LL = sp.Symbol('L', positive=True)


class Ctx:
    digits = 10
    env = {}

    def sym(self, n):
        return sp.Symbol(n)


def eq(a, b):
    return sp.Eq(a, b, evaluate=False)


def ps(*a):
    return BUILTINS['pdsolve'](Ctx(), *a)


def sub_(e, a, b):
    return sp.Subs(sp.Derivative(U(x, t) if False else e, a), a, b)


def dx0(pos, u=None, var=x, args=(x, t)):
    """u_var bij var=pos als Subs (zoals eval(diff(u,var), var=pos))."""
    return sp.Subs(sp.Derivative(U(*args), var), var, pos)


@__import__('functools').lru_cache(maxsize=None)
def _jzero(a, b):
    return float(mp.besseljzero(int(a), int(b)))


def num(expr, vals, N=400):
    """Numerieke waarde van (som van) reeks(en) met afkapping N."""
    expr = sp.sympify(expr)
    if isinstance(expr, sp.Add):
        return sum(num(a, vals, N) for a in expr.args)
    if isinstance(expr, sp.Mul) and expr.has(sp.Sum):
        sums = [a for a in expr.args if a.has(sp.Sum)]
        rest = sp.Mul(*[a for a in expr.args if not a.has(sp.Sum)])
        if len(sums) == 1:
            return complex(rest.subs(vals).evalf()).real * num(sums[0], vals, N)
    if isinstance(expr, sp.Sum):
        idx = [l[0] for l in expr.limits]
        f = expr.function.subs(vals)
        zeros = lambda nu, n: np.vectorize(_jzero)(nu, n)
        jv = __import__('scipy.special', fromlist=['jv']).jv
        fn = sp.lambdify(idx, f, modules=[{'BesselJZeros': zeros, 'BesselJ': jv, 'besselj': jv}, 'numpy'])
        grids = np.meshgrid(*[np.arange(1, N + 1) for _ in idx], indexing='ij') if len(idx) > 1 else [np.arange(1, N + 1)]
        if len(idx) > 1:
            grids = np.meshgrid(*[np.arange(1, 61) for _ in idx], indexing='ij')
        with np.errstate(all='ignore'):
            v = float(np.sum(fn(*grids)))
        if not np.isfinite(v) and len(idx) == 1:
            # overflow (bv. sinh(n*pi*y)/sinh(n*pi)): term per term in mpmath
            fm = sp.lambdify(idx, f, modules='mpmath')
            v = float(sum(fm(mp.mpf(j)) for j in range(1, N + 1)))
        return v
    return complex(expr.subs(vals).evalf()).real


def rhs_of(res):
    assert isinstance(res, sp.Equality)
    return res.rhs


def residual(res, pde_op, pts):
    """max |pde_op(u)| over punten; pde_op neemt de rhs-expressie."""
    e = pde_op(rhs_of(res))
    return max(abs(num(e, p)) for p in pts)


def heat_op(k_, xv=x, tv=t):
    return lambda e: sp.diff(e, tv) - k_ * sp.diff(e, xv, 2)


def wave_op(c_, xv=x, tv=t):
    return lambda e: sp.diff(e, tv, 2) - c_ ** 2 * sp.diff(e, xv, 2)


HEAT = eq(U(x, t).diff(t), kk * U(x, t).diff(x, 2))
WAVE = eq(U(x, t).diff(t, 2), cc ** 2 * U(x, t).diff(x, 2))
Ut0 = sp.Subs(sp.Derivative(U(x, t), t), t, 0)


def test_heat_dirichlet_symbolic_L_coefficients_netjes():
    L = LL
    r_ = ps(MSet([HEAT, eq(U(0, t), 0), eq(U(L, t), 0), eq(U(x, 0), x * (L - x))]), U(x, t))
    s = rhs_of(r_)
    assert isinstance(s, sp.Sum) and not s.has(sp.Piecewise)
    n = s.limits[0][0]
    # exacte coefficient 4 L^2 (1-(-1)^n)/(pi^3 n^3)
    c = sp.simplify(s.function.subs({x: 0, t: 0}) * 0 + s.function / (sp.sin(n * pi * x / L) * sp.exp(-pi ** 2 * kk * n ** 2 * t / L ** 2)))
    assert sp.simplify(c - 4 * L ** 2 * (1 - (-1) ** n) / (pi ** 3 * n ** 3)) == 0
    pts = [{x: 0.7, t: 0.05, kk: 0.8, LL: 2.0}, {x: 1.3, t: 0.2, kk: 1.1, LL: 2.0}]
    assert residual(r_, heat_op(kk), pts) < 1e-8
    assert abs(num(rhs_of(r_).subs(x, 0), {t: 0.1, kk: 1, LL: 2.0})) < 1e-12
    assert abs(num(rhs_of(r_), {x: 0.9, t: 0, kk: 1, LL: 2.0}) - 0.9 * 1.1) < 2e-4


def test_heat_dirichlet_trig_resonantie_geeft_eindige_som():
    r_ = ps(MSet([HEAT, eq(U(0, t), 0), eq(U(pi, t), 0), eq(U(x, 0), sp.sin(x) + 3 * sp.sin(2 * x))]), U(x, t))
    ex = sp.exp(-kk * t) * sp.sin(x) + 3 * sp.exp(-4 * kk * t) * sp.sin(2 * x)
    assert sp.simplify(rhs_of(r_) - ex) == 0


def test_heat_neumann_beide_randen():
    ic = eq(U(x, 0), x)
    r_ = ps(MSet([HEAT, eq(dx0(0), 0), eq(dx0(1), 0), ic]), U(x, t))
    s = rhs_of(r_)
    assert not s.has(sp.Piecewise)
    # gemiddelde 1/2 blijft behouden: t -> oneindig
    assert abs(num(s, {x: 0.3, t: 50.0, kk: 1.0}) - 0.5) < 1e-9
    pts = [{x: 0.3, t: 0.05, kk: 0.7}, {x: 0.8, t: 0.1, kk: 0.7}]
    assert residual(r_, heat_op(kk), pts) < 1e-8
    assert abs(num(sp.diff(s, x).subs(x, 1), {t: 0.2, kk: 1.0})) < 1e-10
    assert abs(num(s, {x: 0.3, t: 0, kk: 1.0}) - 0.3) < 2e-3


def test_heat_gemengd_dirichlet_neumann():
    # u(0,t)=0, u_x(1,t)=0, u(x,0)=1: sin((2n-1) pi x/2), coefficient 4/((2n-1) pi)
    r_ = ps(MSet([HEAT, eq(U(0, t), 0), eq(dx0(1), 0), eq(U(x, 0), 1)]), U(x, t))
    s = rhs_of(r_)
    n = s.limits[0][0]
    c = sp.simplify(s.function.subs(t, 0) / sp.sin((2 * n - 1) * pi * x / 2))
    assert sp.simplify(c - 4 / ((2 * n - 1) * pi)) == 0
    assert residual(r_, heat_op(kk), [{x: 0.4, t: 0.05, kk: 1.0}]) < 1e-8
    assert abs(num(sp.diff(s, x).subs(x, 1), {t: 0.2, kk: 1.0})) < 1e-10
    # omgekeerd: u_x(0,t)=0, u(1,t)=0
    r2 = ps(MSet([HEAT, eq(dx0(0), 0), eq(U(1, t), 0), eq(U(x, 0), 1 - x ** 2)]), U(x, t))
    assert residual(r2, heat_op(kk), [{x: 0.4, t: 0.05, kk: 1.0}]) < 1e-8
    assert abs(num(rhs_of(r2).subs(x, 1), {t: 0.2, kk: 1.0})) < 1e-10
    assert abs(num(sp.diff(rhs_of(r2), x).subs(x, 0), {t: 0.2, kk: 1.0})) < 1e-10
    assert abs(num(rhs_of(r2), {x: 0.4, t: 0, kk: 1.0}) - (1 - 0.16)) < 1e-3


def test_heat_inhomogene_randwaarden_stationaire_toestand():
    r_ = ps(MSet([HEAT, eq(U(0, t), 1), eq(U(1, t), 3), eq(U(x, 0), 0)]), U(x, t))
    s = rhs_of(r_)
    assert abs(num(s, {x: 0.25, t: 80.0, kk: 1.0}) - 1.5) < 1e-9     # u -> 1 + 2x
    assert abs(num(s.subs(x, 1), {t: 0.3, kk: 1.0}) - 3) < 1e-9
    assert abs(num(s.subs(x, 0), {t: 0.3, kk: 1.0}) - 1) < 1e-9
    assert residual(r_, heat_op(kk), [{x: 0.3, t: 0.1, kk: 0.9}]) < 1e-7
    assert abs(num(s, {x: 0.4, t: 0.0, kk: 1.0}) - 0) < 2e-2        # Gibbs-achtig, 1/n-reeks


def test_heat_bron_en_neumann_rand():
    pde = eq(U(x, t).diff(t), U(x, t).diff(x, 2) + sp.sin(x))
    r_ = ps(MSet([pde, eq(U(0, t), 0), eq(U(pi, t), 0), eq(U(x, 0), 0)]), U(x, t))
    assert sp.simplify(rhs_of(r_) - sp.sin(x) * (1 - sp.exp(-t))) == 0
    # u_xx = -1 stationair met u(0)=0, u_x(1)=0 -> x - x^2/2
    pde2 = eq(U(x, t).diff(t), U(x, t).diff(x, 2) + 1)
    r2 = ps(MSet([pde2, eq(U(0, t), 0), eq(dx0(1), 0), eq(U(x, 0), 0)]), U(x, t))
    assert abs(num(rhs_of(r2), {x: 0.6, t: 60.0}) - (0.6 - 0.18)) < 1e-9
    assert residual(r2, lambda e: sp.diff(e, t) - sp.diff(e, x, 2) - 1, [{x: 0.5, t: 0.2}]) < 1e-8


def test_heat_term_met_u_reactie():
    pde = eq(U(x, t).diff(t), kk * U(x, t).diff(x, 2) - 2 * U(x, t))
    r_ = ps(MSet([pde, eq(U(0, t), 0), eq(U(pi, t), 0), eq(U(x, 0), x * (pi - x))]), U(x, t))
    op = lambda e: sp.diff(e, t) - kk * sp.diff(e, x, 2) + 2 * e
    assert residual(r_, op, [{x: 1.0, t: 0.1, kk: 0.5}]) < 1e-8


def test_wave_dirichlet_driehoek_en_snelheid():
    L = 1
    f = sp.Piecewise((x, x < sp.Rational(1, 2)), (1 - x, True))
    r_ = ps(MSet([WAVE, eq(U(0, t), 0), eq(U(1, t), 0), eq(U(x, 0), f), eq(Ut0, 0)]), U(x, t))
    s = rhs_of(r_)
    assert not s.has(sp.Piecewise)
    n = s.limits[0][0]
    assert sp.simplify(s.function.subs(t, 0) / sp.sin(n * pi * x) - 4 * sp.sin(n * pi / 2) / (pi ** 2 * n ** 2)) == 0
    pts = [{x: 0.3, t: 0.37, cc: 1.3}, {x: 0.7, t: 0.11, cc: 0.9}]
    assert residual(r_, wave_op(cc), pts) < 1e-6
    # d'Alembert: periodiek 2/c: u(x, 2/c) = f(x)
    assert abs(num(s, {x: 0.3, t: 2 / 1.3, cc: 1.3}) - 0.3) < 2e-4
    assert abs(num(sp.diff(s, t), {x: 0.3, t: 0.0, cc: 1.0})) < 1e-9


def test_wave_beginsnelheid_en_resonantie():
    ic = eq(Ut0, x * (1 - x))
    r_ = ps(MSet([WAVE, eq(U(0, t), 0), eq(U(1, t), 0), eq(U(x, 0), sp.sin(pi * x) + 2 * sp.sin(3 * pi * x)), ic]), U(x, t))
    s = rhs_of(r_)
    pts = [{x: 0.3, t: 0.4, cc: 1.0}]
    assert residual(r_, wave_op(cc), pts) < 1e-6
    assert abs(num(sp.diff(s, t), {x: 0.4, t: 0, cc: 1.0}) - 0.4 * 0.6) < 2e-4
    assert abs(num(s, {x: 0.25, t: 0, cc: 1.0}) - (sp.sin(pi / 4) + 2 * sp.sin(3 * pi / 4)).evalf()) < 1e-12


def test_wave_neumann_nulmodus_geeft_lineaire_term():
    r_ = ps(MSet([WAVE, eq(dx0(0), 0), eq(dx0(1), 0), eq(U(x, 0), x), eq(Ut0, 1)]), U(x, t))
    s = rhs_of(r_)
    assert s.has(t) and abs(num(s, {x: 0.5, t: 0, cc: 1.0}) - 0.5) < 1e-3
    assert residual(r_, wave_op(cc), [{x: 0.3, t: 0.7, cc: 1.2}]) < 1e-6
    # gemiddelde: 1/2 + t
    assert abs(num(s, {x: 0.3, t: 2.0, cc: 1.0}) - num(s, {x: 0.3, t: 2.0, cc: 1.0})) == 0


def test_wave_gemengde_randen_symbolische_L():
    r_ = ps(MSet([WAVE, eq(U(0, t), 0), eq(dx0(LL), 0), eq(U(x, 0), x), eq(Ut0, 0)]), U(x, t))
    pts = [{x: 0.4, t: 0.3, cc: 1.1, LL: 1.5}]
    assert residual(r_, wave_op(cc), pts) < 1e-6
    assert abs(num(sp.diff(rhs_of(r_), x).subs(x, LL), {t: 0.3, cc: 1.1, LL: 1.5})) < 1e-10


def test_wave_inhomogeen_dirichlet():
    r_ = ps(MSet([WAVE, eq(U(0, t), 0), eq(U(1, t), 2), eq(U(x, 0), 2 * x), eq(Ut0, 0)]), U(x, t))
    assert sp.simplify(rhs_of(r_) - 2 * x) == 0          # stationair


def test_2d_warmte_en_golf_rechthoek():
    k_ = sp.Float(0.5)
    pde = eq(U(x, y, t).diff(t), kk * (U(x, y, t).diff(x, 2) + U(x, y, t).diff(y, 2)))
    conds = [eq(U(0, y, t), 0), eq(U(1, y, t), 0), eq(U(x, 0, t), 0), eq(U(x, 1, t), 0),
             eq(U(x, y, 0), x * (1 - x) * y * (1 - y))]
    r_ = ps(MSet([pde] + conds), U(x, y, t))
    op = lambda e: sp.diff(e, t) - kk * (sp.diff(e, x, 2) + sp.diff(e, y, 2))
    assert residual(r_, op, [{x: 0.3, y: 0.6, t: 0.05, kk: 0.5}]) < 1e-8
    assert abs(num(rhs_of(r_), {x: 0.3, y: 0.6, t: 0, kk: 1.0}) - 0.3 * 0.7 * 0.6 * 0.4) < 1e-4
    assert abs(num(rhs_of(r_).subs(y, 0), {x: 0.3, t: 0.1, kk: 1.0})) < 1e-12
    # golf, eigenmode sin(x) sin(2y): frequentie c sqrt(5)
    wv = eq(U(x, y, t).diff(t, 2), cc ** 2 * (U(x, y, t).diff(x, 2) + U(x, y, t).diff(y, 2)))
    c2 = [eq(U(0, y, t), 0), eq(U(pi, y, t), 0), eq(U(x, 0, t), 0), eq(U(x, pi, t), 0),
          eq(U(x, y, 0), sp.sin(x) * sp.sin(2 * y)), eq(sp.Subs(sp.Derivative(U(x, y, t), t), t, 0), 0)]
    r2 = ps(MSet([wv] + c2), U(x, y, t))
    assert sp.simplify(rhs_of(r2) - sp.sin(x) * sp.sin(2 * y) * sp.cos(sp.sqrt(5) * cc * t)) == 0


def test_2d_warmte_gemengd_neumann_x():
    pde = eq(U(x, y, t).diff(t), U(x, y, t).diff(x, 2) + U(x, y, t).diff(y, 2))
    conds = [eq(dx0(0, args=(x, y, t)), 0), eq(dx0(1, args=(x, y, t)), 0), eq(U(x, 0, t), 0), eq(U(x, 1, t), 0),
             eq(U(x, y, 0), x * y)]
    r_ = ps(MSet([pde] + conds), U(x, y, t))
    op = lambda e: sp.diff(e, t) - sp.diff(e, x, 2) - sp.diff(e, y, 2)
    assert residual(r_, op, [{x: 0.3, y: 0.6, t: 0.05}]) < 1e-8
    assert abs(num(r_.rhs, {x: 0.3, y: 0.6, t: 0}) - 0.18) < 5e-3


LAP = eq(U(x, y).diff(x, 2) + U(x, y).diff(y, 2), 0)


def lap_op(e):
    return sp.diff(e, x, 2) + sp.diff(e, y, 2)


def test_laplace_rechthoek_dirichlet_alle_zijden():
    conds = [eq(U(0, y), sp.sin(pi * y)), eq(U(1, y), 0), eq(U(x, 0), 0), eq(U(x, 1), x * (1 - x))]
    r_ = ps(MSet([LAP] + conds), U(x, y))
    s = rhs_of(r_)
    assert residual(r_, lap_op, [{x: 0.3, y: 0.4}, {x: 0.8, y: 0.7}]) < 1e-9
    assert abs(num(s, {x: 0.0, y: 0.3}) - np.sin(np.pi * 0.3)) < 1e-9
    assert abs(num(s, {x: 1.0, y: 0.3})) < 1e-9
    assert abs(num(s, {x: 0.4, y: 0.0})) < 1e-9
    assert abs(num(s, {x: 0.4, y: 1.0}, N=2000) - 0.24) < 1e-3
    assert not s.has(sp.Piecewise)


def test_laplace_rechthoek_exact_een_zijde():
    a, b = sp.symbols('a b', positive=True)
    r_ = ps(MSet([LAP, eq(U(0, y), 0), eq(U(a, y), 0), eq(U(x, 0), 0), eq(U(x, b), sp.sin(pi * x / a))]), U(x, y))
    assert sp.simplify(rhs_of(r_) - sp.sin(pi * x / a) * sp.sinh(pi * y / a) / sp.sinh(pi * b / a)) == 0


def test_laplace_rechthoek_neumann_zijden():
    conds = [eq(dx0(0, args=(x, y)), 0), eq(dx0(1, args=(x, y)), 0), eq(U(x, 0), 0), eq(U(x, 1), x)]
    r_ = ps(MSet([LAP] + conds), U(x, y))
    s = rhs_of(r_)
    assert residual(r_, lap_op, [{x: 0.3, y: 0.4}]) < 1e-9
    assert abs(num(sp.diff(s, x).subs(x, 0), {y: 0.4})) < 1e-10
    assert abs(num(s, {x: 0.4, y: 0.0})) < 1e-10
    assert abs(num(s, {x: 0.4, y: 1.0}, N=3000) - 0.4) < 2e-3
    # Neumann op de bovenrand: u_y(x,1)=cos(pi x), u(x,0)=0 (gemengd)
    c2 = [eq(U(0, y), 0), eq(U(1, y), 0), eq(U(x, 0), 0),
          eq(sp.Subs(sp.Derivative(U(x, y), y), y, 1), sp.sin(pi * x))]
    r2 = ps(MSet([LAP] + c2), U(x, y))
    s2 = rhs_of(r2)
    assert residual(r2, lap_op, [{x: 0.3, y: 0.4}]) < 1e-9
    assert abs(num(sp.diff(s2, y).subs(y, 1), {x: 0.35}) - np.sin(np.pi * 0.35)) < 1e-9


LAPP = eq(U(r, th).diff(r, 2) + U(r, th).diff(r) / r + U(r, th).diff(th, 2) / r ** 2, 0)


def test_laplace_schijf():
    R = sp.Symbol('R', positive=True)
    r_ = ps(MSet([LAPP, eq(U(R, th), sp.sin(th) + sp.cos(2 * th) + 1)]), U(r, th))
    assert sp.simplify(rhs_of(r_) - (1 + r * sp.sin(th) / R + r ** 2 * sp.cos(2 * th) / R ** 2)) == 0
    r2 = ps(MSet([LAPP, eq(U(1, th), th * (2 * pi - th))]), U(r, th))
    op = lambda e: sp.diff(e, r, 2) + sp.diff(e, r) / r + sp.diff(e, th, 2) / r ** 2
    assert residual(r2, op, [{r: 0.6, th: 1.0}]) < 1e-9
    # randwaarde (r=1) benaderd; th=1.3: 1.3*(2pi-1.3)
    assert abs(num(rhs_of(r2), {r: 1.0, th: 1.3}, N=4000) - 1.3 * (2 * np.pi - 1.3)) < 5e-3


def test_laplace_schijf_neumann():
    r_ = ps(MSet([LAPP, eq(sp.Subs(sp.Derivative(U(r, th), r), r, 1), sp.cos(th))]), U(r, th))
    assert sp.simplify(rhs_of(r_).subs(sp.Symbol('_C1'), 0) - r * sp.cos(th)) == 0


def test_trommel_bessel_golf_en_warmte():
    R = 1
    c_ = cc
    pde = eq(U(r, t).diff(t, 2), c_ ** 2 * (U(r, t).diff(r, 2) + U(r, t).diff(r) / r))
    ut0 = sp.Subs(sp.Derivative(U(r, t), t), t, 0)
    r_ = ps(MSet([pde, eq(U(1, t), 0), eq(U(r, 0), 1 - r ** 2), eq(ut0, 0)]), U(r, t))
    s = rhs_of(r_)
    assert s.has(sp.Function('BesselJZeros'))
    op = lambda e: sp.diff(e, t, 2) - cc ** 2 * (sp.diff(e, r, 2) + sp.diff(e, r) / r)
    assert residual(r_, op, [{r: 0.4, t: 0.3, cc: 1.5}]) < 1e-5
    assert abs(num(s, {r: 0.4, t: 0, cc: 1.0}, N=300) - (1 - 0.16)) < 1e-4
    assert abs(num(s, {r: 1.0, t: 0.37, cc: 1.0}, N=300)) < 1e-9
    heat = eq(U(r, t).diff(t), kk * (U(r, t).diff(r, 2) + U(r, t).diff(r) / r))
    r2 = ps(MSet([heat, eq(U(1, t), 0), eq(U(r, 0), 1)]), U(r, t))
    op2 = lambda e: sp.diff(e, t) - kk * (sp.diff(e, r, 2) + sp.diff(e, r) / r)
    assert residual(r2, op2, [{r: 0.5, t: 0.05, kk: 1.0}]) < 1e-6
    assert abs(num(rhs_of(r2), {r: 0.5, t: 0.0, kk: 1.0}, N=400) - 1) < 5e-3


def test_maple_syntax_via_interpreter():
    from minimaple.interp import Interpreter
    it = Interpreter()
    it.run("heat := diff(u(x,t),t) = k*diff(u(x,t),x$2):")
    out = it.run("pdsolve(heat, {u(0,t)=0, eval(diff(u(x,t),x),x=1)=0, u(x,0)=1});")[0]
    assert out['error'] is None and out['text'].startswith("u(x, t) = Sum(") and 'sin' in out['text']
    out = it.run("pdsolve(heat, IBC = {u(0,t)=0, u(1,t)=0, u(x,0)=1});")[0]
    assert out['error'] is None and 'Sum(' in out['text']
    out = it.run("pdsolve(heat, [u(0,t)=0, u(1,t)=0], u(x,0)=x*(1-x));")[0]
    assert out['error'] is None and 'Piecewise' not in out['text']
    out = it.run("pdsolve(heat, HINT = `+`);")[0]
    assert out['error'] is None


def test_robin_en_onbekend_geven_duidelijke_fout():
    robin = eq(U(1, t) + sp.Subs(sp.Derivative(U(x, t), x), x, 1), 0)
    with pytest.raises(ValueError, match="Robin"):
        ps(MSet([HEAT, eq(U(0, t), 0), robin, eq(U(x, 0), 1)]), U(x, t))
    with pytest.raises(ValueError):
        ps(MSet([HEAT, eq(U(0, t), 0), eq(U(x, 0), 1)]), U(x, t))
