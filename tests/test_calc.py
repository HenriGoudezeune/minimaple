import sympy as sp
import numpy as np
import pytest
from minimaple import calc
from minimaple.values import BUILTINS, MList, MSet, Seq, Range

x, y, t, s, w, k, n = sp.symbols('x y t s w k n')
Y = sp.Function('y'); Z = sp.Function('z'); U = sp.Function('u')
pi, oo, I = sp.pi, sp.oo, sp.I


class FakeCtx:
    digits = 10
    def __init__(self): self.env = {}
    def sym(self, n): return sp.Symbol(n)


class Rel:
    """x=a..b zoals de interpreter het (mogelijk) aanlevert."""
    def __init__(self, l, r): self.lhs, self.rhs = l, r


def R(v, a, b): return Rel(v, Range(a, b))
def C(name, *a): return BUILTINS[name](FakeCtx(), *a)
def eq(a, b): return sp.Eq(a, b, evaluate=False)
def same(a, b): return sp.simplify(a - b) == 0


def test_diff():
    assert C('diff', x**3, x) == 3*x**2
    assert C('diff', x**3, x, x) == 6*x
    assert C('diff', sp.sin(x*y), x, y) == sp.cos(x*y) - x*y*sp.sin(x*y)
    assert C('diff', Y(x), x, x) == sp.Derivative(Y(x), (x, 2))
    assert C('Diff', x**2, x) == sp.Derivative(x**2, x)
    assert C('value', C('Diff', x**2, x)) == 2*x


def test_int():
    assert C('int', x**2, x) == x**3/3
    assert C('int', x**2, R(x, 0, 1)) == sp.Rational(1, 3)
    assert C('int', sp.exp(-x**2), R(x, -oo, oo)) == sp.sqrt(pi)
    assert C('int', x*y, R(x, 0, 1), R(y, 0, 2)) == 1
    assert isinstance(C('Int', x, R(x, 0, 1)), sp.Integral)
    assert C('value', C('Int', x, R(x, 0, 2))) == 2
    assert C('int', sp.sin(x), R(x, 0, pi)) == 2


def test_limit():
    assert C('limit', sp.sin(x)/x, sp.Eq(x, 0)) == 1
    assert C('limit', 1/x, sp.Eq(x, 0), sp.Symbol('right')) == oo
    assert C('limit', 1/x, sp.Eq(x, 0), sp.Symbol('left')) == -oo
    assert C('limit', 1/x, sp.Eq(x, 0)) == sp.Symbol('undefined')
    assert C('limit', (1+1/x)**x, sp.Eq(x, oo)) == sp.E
    assert C('limit', x*sp.exp(-x), sp.Eq(x, oo)) == 0
    assert isinstance(C('Limit', sp.sin(x)/x, sp.Eq(x, 0)), sp.Limit)


def test_sum_product():
    assert C('sum', k, R(k, 1, n)) == n*(n+1)/2
    assert C('sum', 1/k**2, R(k, 1, oo)) == pi**2/6
    assert C('sum', sp.Rational(1, 2)**k, R(k, 0, oo)) == 2
    assert C('sum', k**2, R(k, 1, 10)) == 385
    assert C('product', k, R(k, 1, 5)) == 120
    assert isinstance(C('Sum', k, R(k, 1, 3)), sp.Sum)
    assert C('value', C('Sum', k, R(k, 1, 3))) == 6


def test_series_taylor():
    sr = C('series', sp.exp(x), sp.Eq(x, 0), 4)
    assert sr.removeO() == 1 + x + x**2/2 + x**3/6
    assert sr.has(sp.Order) and sr.getO() == sp.Order(x**4)
    assert C('taylor', sp.sin(x), sp.Eq(x, 0), 6).removeO() == x - x**3/6 + x**5/120
    assert C('convert', sr, sp.Symbol('polynom')) == 1 + x + x**2/2 + x**3/6
    sr1 = C('series', sp.log(x), sp.Eq(x, 1), 3)
    assert sp.expand(sr1.removeO()) == sp.expand((x-1) - (x-1)**2/2)
    assert C('mtaylor', sp.exp(x+y), MList([x, y]), 3) == 1 + x + y + x**2/2 + x*y + y**2/2


def test_convert():
    P = sp.Symbol
    assert same(C('convert', 1/(x**2-1), P('parfrac'), x), 1/(2*(x-1)) - 1/(2*(x+1)))
    assert C('convert', 1/(x**2-1), P('parfrac'), x).has(sp.Pow)
    assert same(C('convert', sp.sin(x), P('exp')), (sp.exp(I*x)-sp.exp(-I*x))/(2*I))
    assert same(C('convert', sp.cos(x), P('exp')), (sp.exp(I*x)+sp.exp(-I*x))/2)
    assert C('convert', sp.exp(I*x), P('trig')) == sp.cos(x) + I*sp.sin(x)
    assert C('convert', sp.Float('0.75'), P('rational')) == sp.Rational(3, 4)
    assert C('convert', 180, P('radians')) == pi
    assert C('convert', pi, P('degrees')) == 180
    assert C('convert', sp.Matrix([[1, 2], [3, 4]]), P('list')) == [[1, 2], [3, 4]]
    assert isinstance(C('convert', MList([1, 2, 2]), P('set')), MSet) and len(C('convert', MList([1, 2, 2]), P('set'))) == 2
    assert C('convert', MList([[1, 2], [3, 4]]), P('Matrix')) == sp.Matrix([[1, 2], [3, 4]])
    assert abs(float(C('convert', pi, P('float'))) - 3.14159265358) < 1e-9


def test_algebra():
    assert C('expand', (x+1)**3) == x**3 + 3*x**2 + 3*x + 1
    assert C('expand', sp.sin(2*x)) == 2*sp.sin(x)*sp.cos(x)
    assert C('factor', x**2-1) == (x-1)*(x+1)
    assert sp.expand(C('factor', x**2-2, sp.sqrt(2)) - (x-sp.sqrt(2))*(x+sp.sqrt(2))) == 0
    assert C('simplify', sp.sin(x)**2 + sp.cos(x)**2) == 1
    assert C('normal', (x**2-1)/(x-1)) == x+1
    assert C('collect', x*y + x + y*x**2, x) == x**2*y + x*(y+1)
    assert C('combine', sp.sin(x)*sp.cos(x)*2, sp.Symbol('trig')) == sp.sin(2*x)
    assert C('combine', sp.exp(x)*sp.exp(y), sp.Symbol('exp')) == sp.exp(x+y)
    assert C('coeff', 3*x**2 + 2*x + 1, x, 2) == 3
    assert C('coeff', 3*x**2 + 2*x + 1, x) == 2
    assert C('coeff', 3*x**2 + 2*x + 1, x**2) == 3
    assert tuple(C('coeffs', 3*x**2 + 2*x + 1, x)) == (1, 2, 3)
    assert C('degree', x**4 + x, x) == 4
    assert C('numer', (x+1)/(x-2)) == x+1 and C('denom', (x+1)/(x-2)) == x-2
    assert C('numer', sp.Rational(3, 4)) == 3
    assert C('simplify', eq(sp.sin(x)**2+sp.cos(x)**2, 1)).lhs == 1


def test_evalf_evalc():
    assert abs(C('evalf', pi) - sp.N(pi, 10)) < 1e-10
    assert str(C('evalf', pi, 30)) == '3.14159265358979323846264338328'
    assert abs(C('evalf', sp.sqrt(2), 5) - 1.4142) < 1e-4
    assert C('evalc', sp.exp(I*x)) == sp.cos(x) + I*sp.sin(x)
    assert C('evalc', sp.Abs(3+4*I)) == 5
    assert C('evalc', (1+I)**2) == 2*I
    assert abs(C('evalf', C('Int', sp.sin(x), R(x, 0, pi))) - 2) < 1e-9


def test_solve():
    r = C('solve', eq(x**2, 4), x)
    assert isinstance(r, Seq) and set(r) == {-2, 2}
    assert C('solve', eq(2*x+1, 7), x) == 3
    assert C('solve', x**2 - 3*x + 2, x) is not None
    r = C('solve', MSet([eq(x+y, 3), eq(x-y, 1)]), MSet([x, y]))
    assert isinstance(r, MSet) and set(r) == {sp.Eq(x, 2), sp.Eq(y, 1)}
    r = C('solve', MSet([eq(x+y, 3), eq(x-y, 1)]))
    assert set(r) == {sp.Eq(x, 2), sp.Eq(y, 1)}
    r = C('solve', MList([eq(x+y, 3), eq(x-y, 1)]), MList([x, y]))
    assert r == [[sp.Eq(x, 2), sp.Eq(y, 1)]]
    r = C('solve', MSet([eq(x**2+y**2, 1), eq(x, y)]), MSet([x, y]))
    assert isinstance(r, Seq) and len(r) == 2
    a, b = sp.symbols('a b')
    assert C('solve', eq(a*x+b, 0), x) == -b/a
    assert C('solve', eq(x**2, -1), x) is not None
    assert len(C('solve', x**2+1, x)) == 2
    r = C('solve', x**2 > 4, x)
    assert r.subs(x, 3) and r.subs(x, -3) and not r.subs(x, 0)
    assert len(C('solve', eq(x**2+1, 0), x)) == 2
    assert C('isolate', eq(a*x+b, 3), x) == sp.Eq(x, (3-b)/a)


def test_fsolve():
    r = C('fsolve', sp.cos(x) - x, x)
    assert abs(float(r) - 0.7390851332) < 1e-8
    r = C('fsolve', eq(sp.cos(x), x), sp.Eq(x, 1))
    assert abs(float(r) - 0.7390851332) < 1e-8
    r = C('fsolve', x**3 - 3*x + 1, x)
    assert len(r) == 3 and abs(float(r[0]) + 1.879385242) < 1e-8
    r = C('fsolve', sp.sin(x), R(x, 3, 4))
    assert abs(float(r) - np.pi) < 1e-8
    r = C('fsolve', MSet([x**2+y**2-1, x-y]), MSet([sp.Eq(x, 1), sp.Eq(y, 1)]))
    assert abs(float(r[0].rhs) - 0.70710678) < 1e-7


def test_dsolve_basic():
    r = C('dsolve', eq(Y(x).diff(x, 2) + Y(x), 0), Y(x))
    assert isinstance(r, sp.Equality) and r.lhs == Y(x)
    C1, C2 = sp.symbols('_C1 _C2')
    assert sp.simplify(r.rhs - (C1*sp.sin(x) + C2*sp.cos(x))) == 0 or sp.simplify(r.rhs - (C1*sp.cos(x) + C2*sp.sin(x))) == 0
    assert r.rhs.has(C1) and r.rhs.has(C2)
    r = C('dsolve', MSet([eq(Y(x).diff(x, 2) + Y(x), 0), eq(Y(0), 1), eq(sp.Subs(sp.Derivative(Y(t), t), t, 0), 0)]), Y(x))
    assert same(r.rhs, sp.cos(x))
    r = C('dsolve', eq(Y(x).diff(x), Y(x)), Y(x))
    assert same(r.rhs, sp.Symbol('_C1')*sp.exp(x))
    r = C('dsolve', MSet([eq(Y(x).diff(x), 2*Y(x)), eq(Y(0), 3)]), Y(x))
    assert same(r.rhs, 3*sp.exp(2*x))


def test_dsolve_oscillator():
    om = sp.Symbol('omega', positive=True)
    r = C('dsolve', MSet([eq(Y(t).diff(t, 2) + om**2*Y(t), 0), eq(Y(0), 1),
                          eq(sp.Subs(sp.Derivative(Y(s), s), s, 0), 0)]), Y(t))
    assert same(r.rhs, sp.cos(om*t))
    # gedempt: y''+2y'+5y=0, y(0)=0,y'(0)=2 -> e^{-t} sin(2t)
    r = C('dsolve', MSet([eq(Y(t).diff(t, 2) + 2*Y(t).diff(t) + 5*Y(t), 0), eq(Y(0), 0),
                          eq(sp.Subs(sp.Derivative(Y(s), s), s, 0), 2)]), Y(t))
    assert same(r.rhs, sp.exp(-t)*sp.sin(2*t))


def test_dsolve_system_and_laplace():
    r = C('dsolve', MSet([eq(Y(t).diff(t), Z(t)), eq(Z(t).diff(t), -Y(t)), eq(Y(0), 0), eq(Z(0), 1)]),
          MSet([Y(t), Z(t)]))
    assert isinstance(r, MSet)
    d = {e.lhs: e.rhs for e in r}
    assert same(d[Y(t)], sp.sin(t)) and same(d[Z(t)], sp.cos(t))
    r = C('dsolve', MSet([eq(Y(t).diff(t, 2) + Y(t), 0), eq(Y(0), 1), eq(sp.Subs(sp.Derivative(Y(s), s), s, 0), 0)]),
          Y(t), sp.Eq(sp.Symbol('method'), sp.Symbol('laplace')))
    assert same(r.rhs, sp.cos(t))
    r = C('dsolve', MSet([eq(Y(t).diff(t) + 2*Y(t), sp.exp(-t)), eq(Y(0), 1)]), Y(t), sp.Eq(sp.Symbol('method'), sp.Symbol('laplace')))
    assert same(r.rhs, sp.exp(-t)*0 + sp.exp(-t) + 0*t) or same(r.rhs, sp.exp(-t))


def test_dsolve_numeric():
    sol = C('dsolve', MSet([eq(Y(x).diff(x), Y(x)), eq(Y(0), 1)]), Y(x), sp.Symbol('numeric'))
    res = sol(1)
    assert res[0].lhs == x and abs(float(res[1].rhs) - np.e) < 1e-6
    sol = C('dsolve', MSet([eq(Y(t).diff(t, 2), -Y(t)), eq(Y(0), 0), eq(sp.Subs(sp.Derivative(Y(s), s), s, 0), 1)]),
            Y(t), sp.Eq(sp.Symbol('type'), sp.Symbol('numeric')))
    assert abs(float(sol(np.pi/2)[1].rhs) - 1) < 1e-6


def test_laplace():
    assert C('laplace', sp.sin(t), t, s) == 1/(s**2+1)
    assert C('laplace', sp.exp(-2*t), t, s) == 1/(s+2)
    assert C('laplace', t**2, t, s) == 2/s**3
    assert C('laplace', sp.Heaviside(t-1), t, s) == sp.exp(-s)/s
    assert C('laplace', sp.DiracDelta(t), t, s) == 1
    r = C('laplace', Y(t).diff(t), t, s)
    assert r.has(sp.LaplaceTransform) and r.has(Y(0))
    assert same(C('invlaplace', 1/(s**2+1), s, t), sp.sin(t))
    assert same(C('invlaplace', 1/(s*(s+1)), s, t), 1 - sp.exp(-t))
    assert same(C('invlaplace', 1/(s**2+2*s+5), s, t), sp.exp(-t)*sp.sin(2*t)/2)
    assert same(C('invlaplace', sp.exp(-s)/s, s, t), sp.Heaviside(t-1))


def test_fourier():
    f = C('fourier', sp.exp(-t**2), t, w)
    assert same(f, sp.sqrt(pi)*sp.exp(-w**2/4))
    assert same(C('invfourier', f, w, t), sp.exp(-t**2))
    f = C('fourier', sp.exp(-sp.Abs(t)), t, w)
    assert same(f, 2/(1+w**2))
    assert same(C('fourier', sp.cos(3*t), t, w), pi*(sp.DiracDelta(w-3)+sp.DiracDelta(w+3)))
    assert same(C('invfourier', sp.DiracDelta(w), w, t), 1/(2*pi))
    assert same(C('fouriercos', sp.exp(-t), t, w), sp.sqrt(2/pi)/(1+w**2))
    assert same(C('fouriersin', sp.exp(-t), t, w), sp.sqrt(2/pi)*w/(1+w**2))


def test_fft():
    r = C('FourierTransform', MList([1, 2, 3, 4]))
    assert [complex(z) for z in r] == pytest.approx([10, -2+2j, -2, -2-2j])
    r2 = C('InverseFourierTransform', r)
    assert [complex(z).real for z in r2] == pytest.approx([1, 2, 3, 4])
    v = C('FourierTransform', sp.Matrix([1, 0, 0, 0]))
    assert v.shape == (4, 1)


def test_heat_wave_pde():
    L = sp.Symbol('L', positive=True)
    kk = sp.Symbol('k', positive=True)
    pde = eq(U(x, t).diff(t), kk*U(x, t).diff(x, 2))
    # separatie
    r = C('pdsolve', pde, U(x, t))
    assert r[0].lhs == U(x, t) and isinstance(r[1], MSet) and len(r[1]) == 2
    # randvw: u(0,t)=u(pi,t)=0, u(x,0)=sin(x) + 3 sin(2x) -> sin(x)e^{-kt}+3 sin(2x) e^{-4kt}
    conds = MSet([pde, eq(U(0, t), 0), eq(U(pi, t), 0), eq(U(x, 0), sp.sin(x) + 3*sp.sin(2*x))])
    r = C('pdsolve', conds, U(x, t))
    assert isinstance(r.rhs, sp.Sum)
    nn = r.rhs.limits[0][0]
    val = sum(r.rhs.function.subs({nn: j, x: 0.7, t: 0.3, kk: 0.5}) for j in range(1, 8))
    ex = np.sin(0.7)*np.exp(-0.15) + 3*np.sin(1.4)*np.exp(-4*0.15)
    assert abs(float(val) - ex) < 1e-9
    conds = MSet([pde, eq(U(0, t), 0), eq(U(pi, t), 0), eq(U(x, 0), x*(pi-x))])
    r = C('pdsolve', conds, U(x, t))
    nn = r.rhs.limits[0][0]
    val = sum(r.rhs.function.subs({nn: j, x: 1.0, t: 0.1, kk: 0.5}) for j in range(1, 40))
    assert abs(float(val) - 1.7*np.exp(0)*0 - float(sum(4*(1-(-1)**j)/(np.pi*j**3)*np.sin(j)*np.exp(-0.5*j*j*0.1) for j in range(1, 40)))) < 1e-9
    # golf: u_tt = c^2 u_xx, u(x,0)=sin(x), u_t=0 -> sin x cos(ct)
    c = sp.Symbol('c', positive=True)
    wv = eq(U(x, t).diff(t, 2), c**2*U(x, t).diff(x, 2))
    conds = MSet([wv, eq(U(0, t), 0), eq(U(pi, t), 0), eq(U(x, 0), sp.sin(x)),
                  eq(sp.Subs(sp.Derivative(U(x, s), s), s, 0), 0)])
    r = C('pdsolve', conds, U(x, t))
    nn = r.rhs.limits[0][0]
    val = sum(r.rhs.function.subs({nn: j, x: 0.7, t: 0.3, c: 2.0}) for j in range(1, 6))
    assert abs(float(val) - np.sin(0.7)*np.cos(0.6)) < 1e-9
    # eerste orde
    r = C('pdsolve', eq(U(x, t).diff(x) + U(x, t).diff(t), 0), U(x, t))
    assert r.lhs == U(x, t) and r.rhs.has(sp.Function('_F1'))
