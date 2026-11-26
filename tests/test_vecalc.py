import sympy as sp
import pytest
from minimaple.values import BUILTINS, MList, Range
from minimaple import vecalc  # noqa: registreert builtins
from minimaple import linalg  # noqa

x, y, z, t, u, v = sp.symbols('x y z t u v')
r, th, ph = sp.symbols('r theta phi', positive=True)


class FakeCtx:
    digits = 10
    coords = None
    def sym(self, n): return sp.Symbol(n)
    def call(self, f, *a): return f(*a)
    def out(self, s): pass


class Opt:
    def __init__(s, l, r): s.lhs, s.rhs = l, r


C = FakeCtx()
def B(name, *a): return BUILTINS[name](C, *a)
def V(*a): return sp.Matrix(list(a))
XYZ = MList([x, y, z])
SPH = sp.Indexed(sp.IndexedBase('spherical'), r, th, ph)


def test_cartesian():
    f = x**2 * y + sp.sin(z)
    assert B('Gradient', f, XYZ) == V(2*x*y, x**2, sp.cos(z))
    assert B('Gradient', f) == V(2*x*y, x**2, sp.cos(z))     # standaard cartesian[x,y,z]
    F = V(x*y, y*z, z*x)
    assert B('Divergence', F, XYZ) == x + y + z
    assert B('Curl', V(-y, x, 0), XYZ) == V(0, 0, 2)
    assert B('Curl', B('Gradient', f, XYZ), XYZ) == V(0, 0, 0)
    assert B('Laplacian', x**2 + y**2 + z**2, XYZ) == 6
    assert B('Laplacian', V(x**2, y**3, 0), XYZ) == V(2, 6*y, 0)
    assert B('Gradient', x*y, MList([x, y])) == V(y, x)


def test_jac_hess_wr():
    J = B('Jacobian', MList([x**2*y, x + y]), MList([x, y]))
    assert J == sp.Matrix([[2*x*y, x**2], [1, 1]])
    assert B('Jacobian', V(x*y, x + y), MList([x, y]), sp.Symbol('determinant')) == x*y*0 + (y - x)
    assert B('Hessian', x**2*y, MList([x, y])) == sp.Matrix([[2*y, 2*x], [2*x, 0]])
    W = B('Wronskian', MList([sp.sin(t), sp.cos(t)]), t)
    assert W == sp.Matrix([[sp.sin(t), sp.cos(t)], [sp.cos(t), -sp.sin(t)]])
    assert B('Wronskian', MList([sp.sin(t), sp.cos(t)]), t, sp.Symbol('determinant')) == -1
    assert B('Wronskian', MList([1, t, t**2]), t, sp.Symbol('determinant')) == 2


def test_spherical():
    f = 1 / r
    assert B('Laplacian', f, SPH) == 0
    assert B('Gradient', f, SPH) == V(-1/r**2, 0, 0)
    # divergentie van e_r * r^2 -> 4r? div(r^2 e_r) = 4 r
    assert B('Divergence', V(r**2, 0, 0), SPH) == 4*r
    # r^2 sin... laplacian r^2 = 6
    assert B('Laplacian', r**2, SPH) == 6
    # Maple-conventie: z = r cos(phi): grad z = e_z
    zf = r*sp.cos(ph)
    g = B('Gradient', zf, SPH)
    assert sp.simplify(g - V(sp.cos(ph), 0, -sp.sin(ph))) == sp.zeros(3, 1)
    # rotatie om z-as: F = r sin(phi) e_theta  == <-y,x,0>, curl = 2 e_z = 2cos(phi) e_r - 2 sin(phi) e_phi
    c = B('Curl', V(0, r*sp.sin(ph), 0), SPH)
    assert sp.simplify(c - V(2*sp.cos(ph), 0, -2*sp.sin(ph))) == sp.zeros(3, 1)


def test_cylindrical_polar():
    CYL = sp.Indexed(sp.IndexedBase('cylindrical'), r, th, z)
    assert B('Laplacian', sp.log(r), CYL) == 0
    assert B('Divergence', V(r, 0, 0), CYL) == 2
    assert B('Curl', V(0, r, 0), CYL) == V(0, 0, 2)
    POL = sp.Indexed(sp.IndexedBase('polar'), r, th)
    assert B('Laplacian', r**2, POL) == 4
    assert B('Gradient', r**2*sp.sin(th), POL) == V(2*r*sp.sin(th), r*sp.cos(th))


def test_set_coordinates():
    c = FakeCtx()
    BUILTINS['SetCoordinates'](c, SPH)
    assert c.coords[0] == 'spherical' and c.coords[1] == [r, th, ph]
    assert BUILTINS['Laplacian'](c, 1/r) == 0
    BUILTINS['SetCoordinates'](c, sp.Indexed(sp.IndexedBase('cartesian'), x, y, z))
    assert BUILTINS['Gradient'](c, x*y) == V(y, x, 0)
    # coords-optie
    assert BUILTINS['Laplacian'](c, 1/r, Opt(sp.Symbol('coords'), SPH)) == 0
    BUILTINS['SetCoordinates'](c, 'polar[r,theta]')
    assert c.coords[0] == 'polar'


def test_potential_and_integrals():
    F = V(2*x*y, x**2 + z, y)
    phi = B('ScalarPotential', F, XYZ)
    assert sp.simplify(sp.Matrix([sp.diff(phi, w) for w in (x, y, z)]) - F) == sp.zeros(3, 1)
    assert B('ScalarPotential', V(-y, x, 0), XYZ) == sp.Symbol('FAIL')
    # cirkulatie van <-y,x,0> langs eenheidscirkel = 2 pi
    path = V(sp.cos(t), sp.sin(t), 0)
    assert B('LineInt', V(-y, x, 0), path, Opt(t, Range(0, 2*sp.pi))) == 2*sp.pi
    assert B('Circulation', V(-y, x, 0), path, Opt(t, Range(0, 2*sp.pi))) == 2*sp.pi
    # booglengte van de cirkel = scalar lijnintegraal van 1
    assert B('LineInt', sp.Integer(1), path, Opt(t, Range(0, 2*sp.pi))) == 2*sp.pi
    # flux van <x,y,z> door eenheidsbol = 4 pi
    S = V(sp.sin(u)*sp.cos(v), sp.sin(u)*sp.sin(v), sp.cos(u))
    fl = B('Flux', V(x, y, z), S, Opt(u, Range(0, sp.pi)), Opt(v, Range(0, 2*sp.pi)))
    assert sp.simplify(fl) == 4*sp.pi
    # oppervlakte bol
    a = B('SurfaceInt', sp.Integer(1), S, Opt(u, Range(0, sp.pi)), Opt(v, Range(0, 2*sp.pi)))
    assert sp.simplify(a) == 4*sp.pi


def test_dot_cross_in_vc():
    from minimaple.values import PACKAGES
    assert 'DotProduct' in PACKAGES['VectorCalculus']
    assert B('CrossProduct', V(x, y, z), V(1, 0, 0)) == V(0, z, -y)
    assert B('Del', x*y, XYZ) == V(y, x, 0*x)
    assert B('Del', V(x, y, z), XYZ) == 3
