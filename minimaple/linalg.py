"""LinearAlgebra-pakket voor mini-Maple. Matrices = sympy.Matrix (kolomvector nx1, rijvector 1xn)."""
import sympy as sp
import numpy as np
from .values import maple, MList, MSet, Seq, Range, PACKAGES, MImage

PKG = 'LinearAlgebra'
LA_OPTS = {'shape', 'fill', 'output', 'orientation', 'datatype', 'storage', 'order', 'scan', 'readonly',
           'attributes', 'normalized', 'conjugate', 'inplace', 'compact', 'outputoptions', 'method', 'symbol'}


class LAError(ValueError):
    pass


# ---------------------------------------------------------------- hulpfuncties
def _opts(args):
    pos, opts = [], {}
    for a in args:
        if _is_eq(a) and isinstance(a.lhs, sp.Symbol) and a.lhs.name in LA_OPTS:
            opts[a.lhs.name] = a.rhs
        else:
            pos.append(a)
    return pos, opts


def _is_eq(a):
    return isinstance(a, sp.Equality) or (hasattr(a, 'lhs') and hasattr(a, 'rhs'))


def _name(x):
    return str(x).strip("'\"`")


def _is_mat(x):
    return isinstance(x, sp.MatrixBase)


def _mat(x):
    """Naar muteerbare sympy Matrix (lijst van lijsten, MList, scalar -> 1x1)."""
    if isinstance(x, sp.MatrixBase):
        return sp.Matrix(x)
    if isinstance(x, (list, tuple)):
        if x and all(isinstance(r, (list, tuple)) for r in x):
            return sp.Matrix([list(r) for r in x])
        return sp.Matrix(list(x))
    return sp.Matrix([[x]])


def _vec(x):
    """Naar kolomvector (rijvector wordt omgezet)."""
    M = _mat(x)
    if M.rows == 1 and M.cols > 1:
        return M.T
    return M


def _conj(e):
    """Complex toegevoegde (Maple: conjugate); symbolen zijn complex tenzij assume/real-declaratie, dus
    conjugate(a) blijft staan; getallen/reele symbolen blijven ongewijzigd."""
    e = sp.sympify(e)
    c = sp.conjugate(e)
    return c


def _hconj(M):
    return M.applyfunc(_conj).T


def _simp(e):
    return sp.simplify(e) if getattr(e, 'free_symbols', None) else e


def _msimp(M):
    return M.applyfunc(_simp)


def _has_float(M):
    return any(e.has(sp.Float) for e in M)


def _num(e):
    return complex(sp.N(e))


def _from_np(a):
    a = np.asarray(a)
    def cv(z):
        z = complex(z)
        if abs(z.imag) < 1e-12 * max(1.0, abs(z.real)):
            return sp.Float(z.real)
        return sp.Float(z.real) + sp.I * sp.Float(z.imag)
    return sp.Matrix(a.shape[0], a.shape[1] if a.ndim > 1 else 1,
                     [cv(z) for z in a.reshape(-1)])


def _to_np(M, real=True):
    a = np.array([[_num(M[i, j]) for j in range(M.cols)] for i in range(M.rows)], dtype=complex)
    if real and np.all(np.abs(a.imag) < 1e-300):
        a = a.real
    return a


def _call(ctx, f, *a):
    if callable(f) and not hasattr(f, 'func'):
        try:
            return f(*a)
        except TypeError:
            pass
    return ctx.call(f, *a)


def _get_range(r):
    if isinstance(r, Range):
        return r.lo, r.hi
    if isinstance(r, sp.Equality):
        return _get_range(r.rhs)
    raise LAError('invalid range')


# ---------------------------------------------------------------- constructors
def _build(ctx, r, c, init, opts):
    fill = opts.get('fill')
    shape = _name(opts['shape']) if 'shape' in opts else None
    M = sp.zeros(r, c)
    if 'symbol' in opts:
        nm = _name(opts['symbol'])
        if c == 1 or r == 1:
            return sp.Matrix(r, c, lambda i, j: sp.Symbol(f"{nm}[{i + j + 1}]"))
        return sp.Matrix(r, c, lambda i, j: sp.Symbol(f"{nm}[{i + 1},{j + 1}]"))
    if fill is not None:
        M = sp.Matrix(r, c, lambda i, j: fill)
    if init is None:
        pass
    elif _is_mat(init):
        for i in range(min(r, init.rows)):
            for j in range(min(c, init.cols)):
                M[i, j] = init[i, j]
    elif isinstance(init, (list, tuple)):
        if init and all(isinstance(e, (list, tuple)) for e in init):
            for i, row in enumerate(init):
                for j, e in enumerate(row):
                    if i < r and j < c:
                        M[i, j] = e
        else:
            flat = list(init)
            for k, e in enumerate(flat):
                if k < r * c:
                    M[k // c, k % c] = e
    elif isinstance(init, sp.Basic) and (init.is_Function or isinstance(init, sp.Lambda)) or callable(init):
        for i in range(r):
            for j in range(c):
                M[i, j] = _call(ctx, init, i + 1, j + 1)
    else:
        M = sp.Matrix(r, c, lambda i, j: init)
    if shape:
        M = _apply_shape(M, shape)
    return M


def _apply_shape(M, shape):
    n = M.rows
    if shape in ('symmetric',):
        return sp.Matrix(n, M.cols, lambda i, j: M[min(i, j), max(i, j)] if i != j else M[i, i])
    if shape in ('antisymmetric', 'skewsymmetric', 'skew-symmetric'):
        return sp.Matrix(n, M.cols, lambda i, j: 0 if i == j else (M[i, j] if i < j else -M[j, i]))
    if shape == 'diagonal':
        return sp.Matrix(n, M.cols, lambda i, j: M[i, j] if i == j else 0)
    if shape == 'identity':
        return sp.eye(n, M.cols)
    if shape == 'zero':
        return sp.zeros(n, M.cols)
    return M


@maple('Matrix', pkg=PKG)
def Matrix(ctx, *args):
    pos, opts = _opts(args)
    if not pos:
        return _build(ctx, 0, 0, None, opts)
    a = pos[0]
    if isinstance(a, MImage):
        from .imagetools import image_to_matrix
        a = image_to_matrix(a)
    if len(pos) == 1:
        if _is_mat(a) or isinstance(a, (list, tuple)):
            M = _mat(a)
            if isinstance(a, (list, tuple)) and a and not all(isinstance(r, (list, tuple)) for r in a):
                M = sp.Matrix([list(a)])      # Matrix([1,2,3]) = 1x3 (zoals Maple)
            return _build(ctx, M.rows, M.cols, M, opts) if opts else M
        n = int(a)
        return _build(ctx, n, n, None, opts)
    r = a
    if isinstance(r, Range):
        r = int(r.hi) - int(r.lo) + 1
    r = int(r)
    c = pos[1]
    if isinstance(c, Range):
        c = int(c.hi) - int(c.lo) + 1
    c = int(c)
    init = pos[2] if len(pos) > 2 else None
    return _build(ctx, r, c, init, opts)


def _vector(ctx, args, orient):
    pos, opts = _opts(args)
    if 'orientation' in opts:
        orient = _name(opts['orientation'])
    orient = 'row' if orient and orient.lower() == 'row' else 'column'
    if not pos:
        v = sp.zeros(0, 1)
    else:
        a = pos[0]
        init = pos[1] if len(pos) > 1 else None
        if isinstance(a, (list, tuple)) or _is_mat(a):
            v = _vec(a)
        else:
            n = int(a)
            fill = opts.get('fill')
            v = sp.Matrix(n, 1, lambda i, j: fill if fill is not None else 0)
            if init is None:
                pass
            elif isinstance(init, (list, tuple)) or _is_mat(init):
                lst = list(init) if not _is_mat(init) else list(init)
                for k, e in enumerate(lst[:n]):
                    v[k, 0] = e
            elif callable(init) or isinstance(init, (sp.Lambda,)) or (
                    isinstance(init, sp.Basic) and init.is_Function):
                for k in range(n):
                    v[k, 0] = _call(ctx, init, k + 1)
            else:
                v = sp.Matrix(n, 1, lambda i, j: init)
    return v.T if orient == 'row' else v


@maple('Vector', 'Vector[column]', 'Vector[Column]', pkg=PKG)
def Vector(ctx, *args):
    return _vector(ctx, args, 'column')


@maple('Vector[row]', 'Vector[Row]', 'RowVector', pkg=PKG)
def VectorRow(ctx, *args):
    return _vector(ctx, args, 'row')


@maple('Array', pkg=PKG)
def Array(ctx, *args):
    pos, opts = _opts(args)
    if pos and isinstance(pos[0], MImage):
        from .imagetools import image_to_matrix
        return image_to_matrix(pos[0])
    if pos and all(isinstance(p, Range) for p in pos[:2]) and pos:
        rs = [p for p in pos if isinstance(p, Range)]
        dims = [int(p.hi) - int(p.lo) + 1 for p in rs]
        init = pos[len(rs)] if len(pos) > len(rs) else None
        if len(dims) == 1:
            return _vector(ctx, [dims[0]] + ([init] if init is not None else []), 'column')
        return _build(ctx, dims[0], dims[1], init, opts)
    if pos and isinstance(pos[0], (list, tuple)):
        a = pos[0]
        if a and all(isinstance(r, (list, tuple)) for r in a):
            return sp.Matrix([list(r) for r in a])
        return sp.Matrix(list(a))
    return Matrix(ctx, *args)


def _blocks(args):
    return [_mat(a) if _is_mat(a) else sp.Matrix([[a]]) for a in args]


@maple('_vstack', pkg=PKG)
def _vstack(ctx, *args):
    """<a,b,c>: kolomvector / verticaal stapelen (smalle blokken worden met 0 aangevuld)."""
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        args = tuple(args[0])
    bl = _blocks(args)
    if not bl:
        return sp.zeros(0, 1)
    w = max(b.cols for b in bl)
    out = []
    for b in bl:
        if b.cols < w:
            b = b.row_join(sp.zeros(b.rows, w - b.cols))
        out.append(b)
    return sp.Matrix.vstack(*out)


@maple('_hstack', pkg=PKG)
def _hstack(ctx, *args):
    """<a|b|c>: horizontaal stapelen."""
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        args = tuple(args[0])
    bl = _blocks(args)
    if not bl:
        return sp.zeros(1, 0)
    h = max(b.rows for b in bl)
    out = []
    for b in bl:
        if b.rows < h:
            b = b.col_join(sp.zeros(h - b.rows, b.cols))
        out.append(b)
    return sp.Matrix.hstack(*out)


@maple('IdentityMatrix', pkg=PKG)
def IdentityMatrix(ctx, n, m=None, *rest):
    return sp.eye(int(n), int(m if m is not None and not isinstance(m, sp.Equality) else n))


@maple('ZeroMatrix', pkg=PKG)
def ZeroMatrix(ctx, r, c=None, *rest):
    return sp.zeros(int(r), int(c if c is not None and not isinstance(c, sp.Equality) else r))


@maple('ConstantMatrix', pkg=PKG)
def ConstantMatrix(ctx, k, r, c=None, *rest):
    c = r if c is None or isinstance(c, sp.Equality) else c
    return sp.Matrix(int(r), int(c), lambda i, j: k)


@maple('ZeroVector', pkg=PKG)
def ZeroVector(ctx, n, *rest):
    pos, o = _opts(rest)
    v = sp.zeros(int(n), 1)
    return v.T if _name(o.get('orientation', 'column')) == 'row' else v


@maple('ConstantVector', pkg=PKG)
def ConstantVector(ctx, k, n, *rest):
    pos, o = _opts(rest)
    v = sp.Matrix(int(n), 1, lambda i, j: k)
    return v.T if _name(o.get('orientation', 'column')) == 'row' else v


@maple('UnitVector', pkg=PKG)
def UnitVector(ctx, *args):
    pos, o = _opts(args)
    if len(pos) == 2:
        i, n = int(pos[0]), int(pos[1])
    else:
        n, i = int(pos[0]), 1
    v = sp.zeros(n, 1)
    v[i - 1, 0] = 1
    return v.T if _name(o.get('orientation', 'column')) == 'row' else v


@maple('Diagonal', 'DiagonalMatrix', pkg=PKG)
def DiagonalMatrix(ctx, d, *rest):
    pos, o = _opts(rest)
    if _is_mat(d) and d.rows > 1 and d.cols > 1:
        return sp.Matrix([d[i, i] for i in range(min(d.shape))])
    vals = list(d) if not _is_mat(d) else list(d)
    n = len(vals)
    r = int(pos[0]) if pos else n
    c = int(pos[1]) if len(pos) > 1 else r
    M = sp.zeros(r, c)
    for i, e in enumerate(vals[:min(r, c)]):
        M[i, i] = e
    return M


# ---------------------------------------------------------------- basis
@maple('Transpose', pkg=PKG)
def Transpose(ctx, M):
    return _mat(M).T


@maple('HermitianTranspose', pkg=PKG)
def HermitianTranspose(ctx, M):
    if not _is_mat(M):
        return _conj(M)          # scalar: gewoon de complex toegevoegde
    return _hconj(_mat(M))


@maple('Determinant', pkg=PKG)
def Determinant(ctx, M, *r):
    M = _mat(M)
    if M.rows != M.cols:
        raise LAError('Determinant: matrix must be square')
    return _simp(M.det(method='berkowitz'))


@maple('MatrixInverse', pkg=PKG)
def MatrixInverse(ctx, M, *r):
    M = _mat(M)
    if M.rows != M.cols:
        raise LAError('MatrixInverse: matrix must be square')
    if M.det() == 0:
        raise LAError('MatrixInverse: singular matrix')
    return _msimp(M.inv())


@maple('Trace', pkg=PKG)
def Trace(ctx, M):
    return _mat(M).trace()


@maple('Rank', pkg=PKG)
def Rank(ctx, M, *r):
    return sp.Integer(_mat(M).rank())


@maple('NullSpace', pkg=PKG)
def NullSpace(ctx, M, *r):
    return MSet(_mat(M).nullspace())


@maple('ColumnSpace', pkg=PKG)
def ColumnSpace(ctx, M, *r):
    return MSet(_mat(M).columnspace())


@maple('RowSpace', pkg=PKG)
def RowSpace(ctx, M, *r):
    M = _mat(M)
    R, piv = M.rref()
    return MSet([R[i, :] for i in range(len(piv))])


@maple('RowDimension', pkg=PKG)
def RowDimension(ctx, M):
    return sp.Integer(_mat(M).rows)


@maple('ColumnDimension', pkg=PKG)
def ColumnDimension(ctx, M):
    return sp.Integer(_mat(M).cols)


@maple('Dimension', 'Dimensions', pkg=PKG)
def Dimension(ctx, M):
    M = _mat(M)
    if M.cols == 1:
        return sp.Integer(M.rows)          # kolomvector -> n
    return Seq((sp.Integer(M.rows), sp.Integer(M.cols)))


def _idx(i, n):
    """1-based index of Range -> lijst 0-based."""
    if isinstance(i, Range):
        lo, hi = int(i.lo), int(i.hi)
        return list(range(lo - 1, hi))
    return [int(i) - 1]


@maple('Column', pkg=PKG)
def Column(ctx, M, i):
    M = _mat(M)
    idx = _idx(i, M.cols)
    return M[:, idx]


@maple('Row', pkg=PKG)
def Row(ctx, M, i):
    M = _mat(M)
    idx = _idx(i, M.rows)
    return M[idx, :]


@maple('Map', pkg=PKG)
def Map(ctx, f, M, *extra):
    if not _is_mat(M):
        return _call(ctx, f, M, *extra)
    return M.applyfunc(lambda e: _call(ctx, f, e, *extra))


def evalf_matrix(M, digits=15):
    """Voor evalf in de interpreter: elementgewijs numeriek."""
    return _mat(M).applyfunc(lambda e: sp.N(e, digits))


# ---------------------------------------------------------------- vermenigvuldigen
def _scalar(x):
    return not _is_mat(x)


def matmul(a, b):
    """Maple A.B / Matrix-product."""
    if _scalar(a) or _scalar(b):
        return a * b
    a, b = _mat(a), _mat(b)
    if a.cols != b.rows:
        raise LAError('Matrix dimensions do not match for multiplication')
    r = a * b
    return r


def dotprod(a, b):
    """De `.`-operator: matrixproduct; kolom.kolom (zelfde lengte) = a^T b (scalair);
    rij.kolom geeft scalair."""
    if _scalar(a) or _scalar(b):
        return a * b
    a, b = _mat(a), _mat(b)
    if a.cols == b.rows:
        r = a * b
        if r.shape == (1, 1) and a.rows == 1 and (a.cols > 1 or b.cols == 1) and b.cols == 1:
            return r[0, 0]
        return r
    if a.cols == 1 and b.cols == 1 and a.rows == b.rows:
        return (a.T * b)[0, 0]
    if a.rows == 1 and b.rows == 1 and a.cols == b.cols:
        return (a * b.T)[0, 0]
    raise LAError('Matrix dimensions do not match for multiplication')


def matpow(a, n):
    if _scalar(a):
        return a ** n
    a = _mat(a)
    if a.rows != a.cols:
        raise LAError('MatrixPower: matrix must be square')
    if isinstance(n, (int, sp.Integer)) or (hasattr(n, 'is_Integer') and n.is_Integer):
        n = int(n)
        if n >= 0:
            return a ** n
        if a.det() == 0:
            raise LAError('MatrixPower: singular matrix')
        return _msimp(a.inv() ** (-n))
    # niet-geheel (symbolisch) via Jordanvorm
    P, J = a.jordan_form()
    return _msimp(P * J ** n * P.inv())


@maple('MatrixPower', pkg=PKG)
def MatrixPower(ctx, A, n):
    return matpow(A, n)


@maple('MatrixMatrixMultiply', 'MatrixVectorMultiply', 'VectorMatrixMultiply', pkg=PKG)
def MatrixMatrixMultiply(ctx, A, B, *r):
    return matmul(A, B)


@maple('MatrixScalarMultiply', 'VectorScalarMultiply', 'ScalarMultiply', pkg=PKG)
def MatrixScalarMultiply(ctx, A, k, *r):
    return _mat(A) * k


@maple('MatrixAdd', 'VectorAdd', pkg=PKG)
def MatrixAdd(ctx, A, B, c1=1, c2=1, *r):
    return _mat(A) * c1 + _mat(B) * c2


@maple('KroneckerProduct', pkg=PKG)
def KroneckerProduct(ctx, A, B, *r):
    from sympy.matrices.expressions.kronecker import kronecker_product
    return sp.Matrix(kronecker_product(_mat(A), _mat(B)))


@maple('MatrixExponential', pkg=PKG)
def MatrixExponential(ctx, A, t=None, *r):
    A = _mat(A)
    if t is not None:
        A = A * t
    syms = sorted(A.free_symbols, key=str)
    pos = {x: sp.Dummy(x.name, positive=True) for x in syms if x.is_real is not False and not x.assumptions0.get('positive')}
    back = {v: k for k, v in pos.items()}

    def f(e):
        e = sp.simplify(e)
        if e.has(sp.I):
            e = sp.simplify(sp.expand_complex(sp.expand(e)))
        return sp.simplify(sp.radsimp(e))
    E = A.xreplace(pos).exp().applyfunc(f)
    return E.xreplace(back)


@maple('OuterProductMatrix', pkg=PKG)
def OuterProductMatrix(ctx, u, v):
    return _vec(u) * _vec(v).T


@maple('Adjoint', pkg=PKG)
def Adjoint(ctx, A):
    return _mat(A).adjugate()


# ---------------------------------------------------------------- stelsels
@maple('GaussianElimination', pkg=PKG)
def GaussianElimination(ctx, A, *r):
    M = _mat(A)
    m, n = M.shape
    row = 0
    for col in range(n):
        if row >= m:
            break
        p = next((i for i in range(row, m) if sp.simplify(M[i, col]) != 0), None)
        if p is None:
            continue
        if p != row:
            M.row_swap(p, row)
        for i in range(row + 1, m):
            if M[i, col] != 0:
                f = M[i, col] / M[row, col]
                M[i, :] = (M[i, :] - f * M[row, :]).applyfunc(sp.simplify)
        row += 1
    return M


@maple('ReducedRowEchelonForm', pkg=PKG)
def ReducedRowEchelonForm(ctx, A, *r):
    return _mat(A).rref()[0]


@maple('LinearSolve', pkg=PKG)
def LinearSolve(ctx, A, b, *r):
    A = _mat(A)
    b = _mat(b)
    if _has_float(A) or _has_float(b):
        if A.rows == A.cols and A.det() != 0:
            return A.LUsolve(b)
    try:
        sol, params = A.gauss_jordan_solve(b)
    except ValueError:
        raise LAError('LinearSolve: no solutions')
    if len(params):
        sub = {p: sp.Symbol(f'_t{i + 1}') for i, p in enumerate(params)}
        sol = sol.subs(sub)
    return _msimp(sol)


@maple('LeastSquares', pkg=PKG)
def LeastSquares(ctx, A, b, *r):
    A, b = _mat(A), _mat(b)
    AH = _hconj(A)
    try:
        if (AH * A).det() != 0:
            return _msimp((AH * A).LUsolve(AH * b))
    except Exception:
        pass
    return _msimp(A.pinv() * b)


# ---------------------------------------------------------------- eigen
def _eig_order(e):
    try:
        v = complex(sp.N(e))
        return (v.real, v.imag)
    except Exception:
        return (0.0, 0.0)


def _eigs_numeric(M):
    w, V = np.linalg.eig(_to_np(M))
    return w, V


@maple('Eigenvalues', pkg=PKG)
def Eigenvalues(ctx, A, *r):
    A = _mat(A)
    if A.rows != A.cols:
        raise LAError('Eigenvalues: matrix must be square')
    if _has_float(A):
        w, _ = _eigs_numeric(A)
        w = sorted(w, key=lambda z: (z.real, z.imag))
        return _from_np(np.array(w).reshape(-1, 1))
    ev = A.eigenvals()
    vals = []
    for k, m in ev.items():
        vals += [sp.simplify(k)] * int(m)
    vals.sort(key=_eig_order)
    return sp.Matrix(vals)


@maple('Eigenvectors', pkg=PKG)
def Eigenvectors(ctx, A, *r):
    A = _mat(A)
    if A.rows != A.cols:
        raise LAError('Eigenvectors: matrix must be square')
    n = A.rows
    if _has_float(A):
        w, V = _eigs_numeric(A)
        order = sorted(range(n), key=lambda i: (w[i].real, w[i].imag))
        W = np.array([w[i] for i in order]).reshape(-1, 1)
        V = V[:, order]
        return Seq((_from_np(W), _from_np(V)))
    data = sorted(A.eigenvects(), key=lambda t: _eig_order(t[0]))
    vals, cols = [], []
    for ev, mult, vecs in data:
        ev = sp.simplify(ev)
        for k in range(int(mult)):
            vals.append(ev)
            cols.append(sp.simplify(vecs[k]) if k < len(vecs) else sp.zeros(n, 1))
    return Seq((sp.Matrix(vals), sp.Matrix.hstack(*cols)))


@maple('Diagonalize', 'DiagonalizeMatrix', pkg=PKG)
def Diagonalize(ctx, A, *r):
    """Seq(P, D) met A = P D P^-1."""
    P, D = _mat(A).diagonalize()
    return Seq((P, D))


@maple('IsDiagonalizable', pkg=PKG)
def IsDiagonalizable(ctx, A):
    return sp.true if _mat(A).is_diagonalizable() else sp.false


@maple('CharacteristicPolynomial', pkg=PKG)
def CharacteristicPolynomial(ctx, A, lam=None, *r):
    A = _mat(A)
    lam = lam if lam is not None else sp.Symbol('lambda')
    return sp.expand((lam * sp.eye(A.rows) - A).det(method='berkowitz'))


@maple('MinimalPolynomial', pkg=PKG)
def MinimalPolynomial(ctx, A, lam=None, *r):
    A = _mat(A)
    lam = lam if lam is not None else sp.Symbol('lambda')
    P, J = A.jordan_form()
    expo = {}
    for blk in _jordan_blocks(J):
        ev, size = blk
        expo[ev] = max(expo.get(ev, 0), size)
    return sp.expand(sp.Mul(*[(lam - ev) ** s for ev, s in expo.items()]))


def _jordan_blocks(J):
    n = J.rows
    blocks, i = [], 0
    while i < n:
        j = i
        while j + 1 < n and J[j, j + 1] == 1:
            j += 1
        blocks.append((J[i, i], j - i + 1))
        i = j + 1
    return blocks


@maple('JordanForm', pkg=PKG)
def JordanForm(ctx, A, *r):
    """JordanForm(A) -> J; met output=['J','Q'] -> J, Q met A = Q J Q^-1."""
    pos, o = _opts(r)
    P, J = _mat(A).jordan_form()
    if 'output' in o:
        out = o['output']
        out = [_name(x) for x in (out if isinstance(out, (list, tuple, sp.Tuple)) else [out])]
        res = [J if k == 'J' else P for k in out]
        return res[0] if len(res) == 1 else Seq(tuple(res))
    return J


# ---------------------------------------------------------------- normen, hoeken
def _norm_p(p):
    if p is None:
        return sp.oo
    s = str(p)
    if s in ('infinity', 'oo', 'inf'):
        return sp.oo
    if s in ('Euclidean',):
        return sp.Integer(2)
    if s == 'Frobenius':
        return 'fro'
    return p


def _vnorm(v, p):
    ent = list(v)
    if p == sp.oo:
        return sp.Max(*[sp.Abs(e) for e in ent]) if len(ent) > 1 else sp.Abs(ent[0])
    if p == 1:
        return sum(sp.Abs(e) for e in ent)
    if p == 2:
        return sp.sqrt(sp.simplify(sum(e * _conj(e) for e in ent)))
    return sum(sp.Abs(e) ** p for e in ent) ** (1 / sp.sympify(p))


@maple('Norm', pkg=PKG)
def Norm(ctx, A, p=None, *r):
    M = _mat(A)
    p = _norm_p(p)
    isvec = M.cols == 1 or M.rows == 1
    if isvec and p != 'fro':
        return _simp(_vnorm(M, p))
    if p == 'fro' or (isvec and p == 'fro'):
        return _simp(sp.sqrt(sum(e * _conj(e) for e in M)))
    if p == 1:
        return sp.Max(*[sum(sp.Abs(M[i, j]) for i in range(M.rows)) for j in range(M.cols)])
    if p == sp.oo:
        return sp.Max(*[sum(sp.Abs(M[i, j]) for j in range(M.cols)) for i in range(M.rows)])
    if p == 2:
        G = _hconj(M) * M
        ev = [sp.simplify(e) for e in G.eigenvals()]
        ev.sort(key=_eig_order)
        return _simp(sp.sqrt(ev[-1]))
    raise LAError('Norm: unsupported norm')


@maple('VectorNorm', pkg=PKG)
def VectorNorm(ctx, v, p=None, *r):
    return _simp(_vnorm(_mat(v), _norm_p(p) if p is not None else sp.oo))


@maple('Normalize', pkg=PKG)
def Normalize(ctx, v, p=None, *r):
    M = _mat(v)
    p = _norm_p(p) if p is not None else sp.Integer(2)
    n = _vnorm(M, p)
    if n == 0:
        return M
    return M.applyfunc(lambda e: _simp(e / n))


@maple('DotProduct', pkg=PKG)
def DotProduct(ctx, a, b, *r):
    """Maple: a^H b (eerste argument geconjugeerd); met conjugate=false de bilineaire a^T b."""
    _, o = _opts(r)
    conj = str(o.get('conjugate', 'true')).lower() != 'false'
    a, b = _vec(a), _vec(b)
    if a.rows != b.rows:
        raise LAError('DotProduct: vectors must have the same dimension')
    return _simp(sp.expand(sum((_conj(x) if conj else x) * y for x, y in zip(a, b))))


@maple('CrossProduct', pkg=PKG)
def CrossProduct(ctx, a, b, *r):
    ra = _mat(a).rows == 1
    a, b = _vec(a), _vec(b)
    if a.rows != 3 or b.rows != 3:
        raise LAError('CrossProduct: vectors must be 3-dimensional')
    c = a.cross(b).applyfunc(sp.expand)
    return c.T if ra else c


@maple('VectorAngle', pkg=PKG)
def VectorAngle(ctx, a, b, *r):
    a, b = _vec(a), _vec(b)
    d = DotProduct(None, a, b)
    return _simp(sp.acos(sp.simplify(d / (_vnorm(a, 2) * _vnorm(b, 2)))))


@maple('GramSchmidt', pkg=PKG)
def GramSchmidt(ctx, vs, *r):
    normalized = False
    for x in r:
        if isinstance(x, sp.Symbol) and x.name == 'normalized':
            normalized = True
        if isinstance(x, sp.Equality) and str(x.lhs) == 'normalized':
            normalized = x.rhs in (True, sp.true) or str(x.rhs) == 'true'
    vecs = [_vec(v) for v in vs]
    out = []
    for v in vecs:
        w = v
        for u in out:
            uu = DotProduct(None, u, u)
            if uu != 0:
                w = w - u * (DotProduct(None, u, v) / uu)
        out.append(w.applyfunc(sp.simplify))
    if normalized:
        out = [Normalize(None, u) for u in out]
    return MList(out)


@maple('QRDecomposition', pkg=PKG)
def QRDecomposition(ctx, A, *r):
    pos, o = _opts(r)
    A = _mat(A)
    if _has_float(A):
        Q, R = np.linalg.qr(_to_np(A))
        Q, R = _from_np(Q), _from_np(R)
    else:
        Q, R = A.QRdecomposition()
        Q, R = _msimp(Q), _msimp(R)
    out = ['Q', 'R']
    if 'output' in o:
        v = o['output']
        out = [_name(x) for x in (v if isinstance(v, (list, tuple, sp.Tuple)) else [v])]
    res = [Q if k == 'Q' else R for k in out]
    return res[0] if len(res) == 1 else Seq(tuple(res))


@maple('LUDecomposition', pkg=PKG)
def LUDecomposition(ctx, A, *r):
    """Seq(P, L, U) met A = P L U."""
    A = _mat(A)
    L, U, perm = A.LUdecomposition()
    n = A.rows
    Pm = sp.zeros(n, n)
    order = list(range(n))
    for i, j in perm:
        order[i], order[j] = order[j], order[i]
    for i, j in enumerate(order):
        Pm[j, i] = 1
    return Seq((Pm, L, U))


@maple('CholeskyDecomposition', pkg=PKG)
def CholeskyDecomposition(ctx, A, *r):
    return _msimp(_mat(A).cholesky())


def _svd_exact_ok(A):
    return not _has_float(A) and A.rows * A.cols <= 9 and not any(e.free_symbols for e in A)


@maple('SingularValues', pkg=PKG)
def SingularValues(ctx, A, *r):
    """Standaard: Vector van singuliere waarden (aflopend). output=['U','S','Vt'] -> numeriek."""
    pos, o = _opts(r)
    A = _mat(A)
    out = ['S']
    if 'output' in o:
        v = o['output']
        out = [_name(x) for x in (v if isinstance(v, (list, tuple, sp.Tuple)) else [v])]
    k = min(A.rows, A.cols)
    if out == ['S'] and _svd_exact_ok(A):
        G = _hconj(A) * A if A.rows >= A.cols else A * _hconj(A)
        ev = []
        for e, m in G.eigenvals().items():
            ev += [sp.simplify(e)] * int(m)
        ev.sort(key=_eig_order, reverse=True)
        return sp.Matrix([sp.sqrt(e) for e in ev[:k]])
    U, S, Vt = np.linalg.svd(_to_np(A), full_matrices=True)
    res = []
    for key in out:
        if key == 'U':
            res.append(_from_np(U))
        elif key == 'S':
            res.append(_from_np(S.reshape(-1, 1)))
        elif key in ('Vt', 'VT', 'V^T'):
            res.append(_from_np(Vt))
        elif key == 'V':
            res.append(_from_np(Vt.conj().T))
        else:
            raise LAError(f'SingularValues: unknown output {key}')
    return res[0] if len(res) == 1 else Seq(tuple(res))


@maple('svd', 'MTM:-svd', pkg='MTM')
def mtm_svd(ctx, A, *r):
    """MTM:-svd(A): Vector van singuliere waarden; bij `U,S,V := svd(A)` de reeks U,S,V (S diagonaalmatrix m x n)."""
    A = _mat(A)
    econ = bool(r) and _num(r[0]) == 0
    U, S, Vt = np.linalg.svd(_to_np(A), full_matrices=not econ)
    if getattr(ctx, '_nout', 1) < 2:
        return _from_np(S.reshape(-1, 1))
    Sm = np.zeros((U.shape[1], Vt.shape[0]))
    Sm[:len(S), :len(S)] = np.diag(S)
    return Seq((_from_np(U), _from_np(Sm), _from_np(Vt.conj().T)))


@maple('diag', pkg='MTM')
def mtm_diag(ctx, *a):
    """diag(M) -> kolomvector met de diagonaal; diag(v) -> diagonaalmatrix; diag(a,b,..) -> diagonaalmatrix."""
    if len(a) == 1 and _is_mat(a[0]):
        M = a[0]
        if M.rows > 1 and M.cols > 1:
            return sp.Matrix([M[i, i] for i in range(min(M.shape))])
        return DiagonalMatrix(ctx, list(M))
    vals = []
    for x in a:
        vals += list(x) if isinstance(x, (list, tuple, sp.MatrixBase)) else [x]
    return DiagonalMatrix(ctx, vals)


@maple('ConditionNumber', pkg=PKG)
def ConditionNumber(ctx, A, *r):
    return sp.Float(np.linalg.cond(_to_np(_mat(A))))


# ---------------------------------------------------------------- predicaten
def _tf(b):
    return sp.true if b else sp.false


@maple('IsDefinite', pkg=PKG)
def IsDefinite(ctx, A, *r):
    pos, o = _opts(r)
    q = 'positive_definite'
    for x in list(r):
        if isinstance(x, sp.Equality) and str(x.lhs) == 'query':
            q = _name(x.rhs)
    A = _mat(A)
    ev = list(Eigenvalues(ctx, (A + _hconj(A)) / 2))
    try:
        vals = [float(sp.re(sp.N(e))) for e in ev]
    except TypeError:
        raise LAError('IsDefinite: cannot decide for symbolic matrix')
    tol = 1e-12
    res = {'positive_definite': all(v > tol for v in vals),
           'positive_semidefinite': all(v > -tol for v in vals),
           'negative_definite': all(v < -tol for v in vals),
           'negative_semidefinite': all(v < tol for v in vals),
           'indefinite': any(v > tol for v in vals) and any(v < -tol for v in vals)}
    return _tf(res.get(q, False))


@maple('IsOrthogonal', pkg=PKG)
def IsOrthogonal(ctx, A):
    A = _mat(A)
    return _tf(A.rows == A.cols and sp.simplify(A.T * A - sp.eye(A.rows)) == sp.zeros(A.rows, A.rows))


@maple('IsUnitary', pkg=PKG)
def IsUnitary(ctx, A):
    A = _mat(A)
    return _tf(A.rows == A.cols and sp.simplify(_hconj(A) * A - sp.eye(A.rows)) == sp.zeros(A.rows, A.rows))


@maple('IsMatrixShape', pkg=PKG)
def IsMatrixShape(ctx, A, shape, *r):
    A = _mat(A)
    s = _name(shape)
    z = lambda M: M.applyfunc(sp.simplify) == sp.zeros(*M.shape)
    sq = A.rows == A.cols
    if s == 'symmetric':
        return _tf(sq and z(A - A.T))
    if s in ('antisymmetric', 'skewsymmetric'):
        return _tf(sq and z(A + A.T))
    if s == 'hermitian':
        return _tf(sq and z(A - _hconj(A)))
    if s == 'diagonal':
        return _tf(A.is_diagonal())
    if s == 'identity':
        return _tf(sq and A == sp.eye(A.rows))
    if s == 'zero':
        return _tf(A == sp.zeros(*A.shape))
    if s in ('upper', 'upper_triangular', 'triangular[upper]'):
        return _tf(A.is_upper)
    if s in ('lower', 'lower_triangular', 'triangular[lower]'):
        return _tf(A.is_lower)
    if s == 'orthogonal':
        return IsOrthogonal(ctx, A)
    return sp.false


@maple('IsZero', pkg=PKG)
def IsZero(ctx, A):
    return _tf(all(sp.simplify(e) == 0 for e in _mat(A)))
