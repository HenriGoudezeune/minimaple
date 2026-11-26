import sympy as sp
import pytest
from minimaple.values import BUILTINS, MList, Seq, Range
from minimaple import linalg as la

x, y, t = sp.symbols('x y t')


class Opt:
    """stand-in voor naam=waarde met niet-sympy-waarde"""
    def __init__(s, l, r): s.lhs, s.rhs = l, r


class FakeCtx:
    digits = 10
    coords = None
    def sym(self, n): return sp.Symbol(n)
    def call(self, f, *a): return f(*a)
    def out(self, s): pass

C = FakeCtx()
def B(name, *a): return BUILTINS[name](C, *a)
def M(*rows): return sp.Matrix(list(rows))


def test_constructors():
    assert B('Matrix', 2, 2, MList([MList([1, 2]), MList([3, 4])])) == M([1, 2], [3, 4])
    assert B('Matrix', 2, 3, lambda i, j: i * 10 + j) == M([11, 12, 13], [21, 22, 23])
    assert B('Matrix', 2, 2, sp.Eq(sp.Symbol('fill'), 7)) == M([7, 7], [7, 7])
    assert B('Matrix', 2, 2, 5) == M([5, 5], [5, 5])
    assert B('Matrix', 2, 2, MList([1, 2, 3, 4])) == M([1, 2], [3, 4])
    assert B('Matrix', 3, 3, MList([a for a in [1, 2, 3, 4, 5, 6, 7, 8, 9]]), sp.Eq(sp.Symbol('shape'), sp.Symbol('diagonal'))) == sp.diag(1, 5, 9)
    assert B('Vector', 3, MList([1, 2, 3])) == sp.Matrix([1, 2, 3])
    assert B('Vector', 3, lambda i: i ** 2) == sp.Matrix([1, 4, 9])
    assert B('Vector[row]', MList([1, 2])) == sp.Matrix([[1, 2]])
    assert B('Vector[column]', MList([1, 2])) == sp.Matrix([1, 2])
    assert B('Vector', 3, 2) == sp.Matrix([2, 2, 2])
    assert B('IdentityMatrix', 2) == sp.eye(2)
    assert B('ConstantMatrix', 3, 2, 2) == M([3, 3], [3, 3])
    assert B('DiagonalMatrix', MList([1, 2])) == sp.diag(1, 2)


def test_stack():
    a, b = sp.Matrix([1, 2]), sp.Matrix([3, 4])
    assert B('_vstack', 1, 2, 3) == sp.Matrix([1, 2, 3])
    assert B('_hstack', a, b) == M([1, 3], [2, 4])
    assert B('_vstack', B('_hstack', 1, 2), B('_hstack', 3, 4)) == M([1, 2], [3, 4])
    assert B('_hstack', B('_vstack', 1, 2), B('_vstack', 3, 4)) == M([1, 3], [2, 4])


def test_basic():
    A = M([1, 2], [3, 4])
    assert B('Determinant', A) == -2
    assert B('MatrixInverse', A) == M([-2, 1], [sp.Rational(3, 2), -sp.Rational(1, 2)])
    assert B('Transpose', A) == A.T
    assert B('Trace', A) == 5
    assert B('Rank', M([1, 2], [2, 4])) == 1
    assert B('NullSpace', M([1, 2], [2, 4]))[0].T in (M([-2, 1]), M([2, -1]))
    assert B('Dimension', A) == Seq((2, 2))
    assert B('RowDimension', M([1, 2, 3])) == 1
    assert B('Column', A, 2) == sp.Matrix([2, 4])
    assert B('Row', A, 1) == M([1, 2])
    with pytest.raises(ValueError):
        B('MatrixInverse', M([1, 2], [2, 4]))
    assert B('HermitianTranspose', M([sp.I, 1])) == sp.Matrix([-sp.I, 1])


def test_mul():
    A = M([1, 2], [3, 4])
    v = sp.Matrix([1, 1])
    assert la.matmul(A, v) == sp.Matrix([3, 7])
    assert la.dotprod(v, v) == 2
    assert la.dotprod(A, A) == A * A
    assert la.dotprod(2, A) == 2 * A
    assert la.dotprod(v.T, v) == 2
    assert la.matpow(A, 2) == A ** 2
    assert la.matpow(A, -1) == A.inv()
    assert B('MatrixPower', M([1, 1], [0, 1]), 5) == M([1, 5], [0, 1])
    n = sp.Symbol('n', integer=True, positive=True)
    assert sp.simplify(la.matpow(M([1, 1], [0, 1]), n) - M([1, n], [0, 1])) == sp.zeros(2, 2)
    assert B('MatrixExponential', sp.zeros(2, 2)) == sp.eye(2)
    E = B('MatrixExponential', M([0, 1], [-1, 0]), t)
    assert sp.simplify(E - M([sp.cos(t), sp.sin(t)], [-sp.sin(t), sp.cos(t)])) == sp.zeros(2, 2)


def test_eigen():
    A = M([2, 1], [1, 2])
    ev = B('Eigenvalues', A)
    assert sorted(ev) == [1, 3]
    s = B('Eigenvectors', A)
    assert isinstance(s, Seq)
    vals, V = s
    for i in range(2):
        assert A * V[:, i] == vals[i] * V[:, i]
    assert B('CharacteristicPolynomial', A, x) == x ** 2 - 4 * x + 3
    # defect: [[1,1],[0,1]]
    J = M([1, 1], [0, 1])
    vals, V = B('Eigenvectors', J)
    assert list(vals) == [1, 1] and V[:, 1] == sp.zeros(2, 1)
    P, D = B('Diagonalize', A)
    assert P * D * P.inv() == A
    assert B('JordanForm', J) == J
    Jf, Q = B('JordanForm', J, Opt(sp.Symbol('output'), MList([sp.Symbol('J'), sp.Symbol('Q')])))
    assert Q * Jf * Q.inv() == J
    # numeriek
    ev = B('Eigenvalues', M([2.0, 1], [1, 2]))
    assert abs(float(ev[0]) - 1) < 1e-9 and abs(float(ev[1]) - 3) < 1e-9
    # complex
    assert sorted([sp.im(e) for e in B('Eigenvalues', M([0, -1], [1, 0]))]) == [-1, 1]


def test_solve():
    A = M([1, 2], [3, 4])
    assert B('LinearSolve', A, sp.Matrix([5, 6])) == sp.Matrix([-4, sp.Rational(9, 2)])
    S = B('LinearSolve', M([1, 1], [2, 2]), sp.Matrix([2, 4]))
    assert sp.simplify(M([1, 1], [2, 2]) * S - sp.Matrix([2, 4])) == sp.zeros(2, 1)
    with pytest.raises(ValueError):
        B('LinearSolve', M([1, 1], [1, 1]), sp.Matrix([1, 2]))
    G = B('GaussianElimination', M([1, 2, 3], [2, 4, 7], [1, 1, 1]))
    assert G.is_upper
    assert B('ReducedRowEchelonForm', M([1, 2], [3, 4])) == sp.eye(2)
    # kleinste kwadraten: fit y = a + b x
    Ls = B('LeastSquares', M([1, 0], [1, 1], [1, 2]), sp.Matrix([1, 3, 5]))
    assert Ls == sp.Matrix([1, 2])


def test_norms():
    v = sp.Matrix([3, 4])
    assert B('Norm', v, 2) == 5
    assert B('Norm', v) == 4                       # Maple-default: oneindignorm
    assert B('Norm', v, sp.oo) == 4
    assert B('Norm', v, sp.Symbol('Euclidean')) == 5
    assert B('Norm', v, 1) == 7
    A = M([1, 2], [3, 4])
    assert B('Norm', A, sp.Symbol('Frobenius')) == sp.sqrt(30)
    assert B('Norm', A, 1) == 6 and B('Norm', A, sp.oo) == 7
    assert abs(float(B('Norm', M([3, 0], [0, 1]), 2)) - 3) < 1e-12
    assert B('Normalize', v) == sp.Matrix([sp.Rational(3, 5), sp.Rational(4, 5)])
    assert B('DotProduct', v, v) == 25
    assert B('CrossProduct', sp.Matrix([1, 0, 0]), sp.Matrix([0, 1, 0])) == sp.Matrix([0, 0, 1])
    assert B('VectorAngle', sp.Matrix([1, 0]), sp.Matrix([0, 1])) == sp.pi / 2


def test_gs_qr():
    gs = B('GramSchmidt', MList([sp.Matrix([1, 1, 0]), sp.Matrix([1, 0, 1])]))
    assert gs[0].dot(gs[1]) == 0
    gn = B('GramSchmidt', MList([sp.Matrix([1, 1, 0]), sp.Matrix([1, 0, 1])]), sp.Symbol('normalized'))
    assert sp.simplify(gn[0].dot(gn[0])) == 1
    A = M([1, 1], [1, -1], [0, 1])
    Q, R = B('QRDecomposition', A)
    assert sp.simplify(Q * R - A) == sp.zeros(3, 2)
    assert R.is_upper
    A = M([2, 0], [1, 3])
    P, L, U = B('LUDecomposition', A)
    assert P * L * U == A
    A = M([0, 1], [1, 0])
    P, L, U = B('LUDecomposition', A)
    assert P * L * U == A


def test_svd():
    A = M([3, 0], [0, 2])
    S = B('SingularValues', A)
    assert list(S) == [3, 2]
    Af = M([1.0, 2.0], [3.0, 4.0], [5.0, 6.0])
    U, Sv, Vt = B('SingularValues', Af, Opt(sp.Symbol('output'), MList([sp.Symbol('U'), sp.Symbol('S'), sp.Symbol('Vt')])))
    import numpy as np
    Un, Sn, Vtn = [np.array(m.tolist(), dtype=float) for m in (U, Sv, Vt)]
    rec = Un[:, :2] @ np.diag(Sn.ravel()) @ Vtn
    assert np.allclose(rec, np.array(Af.tolist(), dtype=float))
    s = B('svd', M([1, 2], [3, 4]))
    assert abs(float(s[0]) - 5.4649857) < 1e-6
    assert abs(float(s[1]) - 0.3659662) < 1e-6


def test_predicates():
    assert B('IsDefinite', M([2, 0], [0, 3])) == sp.true
    assert B('IsDefinite', M([1, 2], [2, 1])) == sp.false
    assert B('IsDefinite', M([1, 2], [2, 1]), sp.Eq(sp.Symbol('query'), sp.Symbol('indefinite'))) == sp.true
    assert B('IsOrthogonal', M([0, 1], [-1, 0])) == sp.true
    assert B('IsMatrixShape', M([1, 2], [2, 1]), sp.Symbol('symmetric')) == sp.true


def test_map_evalf():
    A = M([1, 4], [9, 16])
    assert B('Map', lambda e: sp.sqrt(e), A) == M([1, 2], [3, 4])
    r = la.evalf_matrix(M([sp.pi, 1]), 5)
    assert abs(float(r[0]) - 3.1416) < 1e-4
