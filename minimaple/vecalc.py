"""VectorCalculus-pakket voor mini-Maple.

Vectorvelden zijn gewone sympy-kolomvectoren; in curvilineaire coordinaten zijn de componenten de
fysische (orthonormale) componenten.  Coordinaten staan in ctx.coords als (systeem, [symbolen]).
Maple-conventie: spherical[r,theta,phi]: x=r cos(theta) sin(phi), y=r sin(theta) sin(phi), z=r cos(phi).
"""
import sympy as sp
from .values import maple, split_opts, MList, MSet, Seq, Range, PACKAGES
from . import linalg as la

PKG = 'VectorCalculus'
SYSTEMS = {'cartesian', 'polar', 'cylindrical', 'spherical'}
DEFAULT_NAMES = {'cartesian': ['x', 'y', 'z'], 'polar': ['r', 'theta'],
                 'cylindrical': ['r', 'theta', 'z'], 'spherical': ['r', 'theta', 'phi']}


class VCError(ValueError):
    pass


def _sym(ctx, n):
    try:
        return ctx.sym(n)
    except Exception:
        return sp.Symbol(n)


def _parse_coord(ctx, a):
    """cartesian[x,y,z] / lijst [x,y,z] / Symbol / string -> (systeem, [symbolen])."""
    if isinstance(a, tuple) and len(a) == 2 and isinstance(a[0], str):
        return a[0], list(a[1])
    if isinstance(a, sp.Indexed):
        return str(a.base), list(a.indices)
    if isinstance(a, sp.core.function.AppliedUndef):
        return a.func.__name__, list(a.args)
    if isinstance(a, (list, tuple)) and not isinstance(a, str):
        return 'cartesian', list(a)
    if isinstance(a, sp.MatrixBase):
        return 'cartesian', list(a)
    s = str(a)
    if '[' in s and s.endswith(']'):
        name, inner = s[:-1].split('[', 1)
        return name.strip(), [sp.Symbol(t.strip()) for t in inner.split(',')]
    if s in DEFAULT_NAMES:
        return s, [_sym(ctx, n) for n in DEFAULT_NAMES[s]]
    if isinstance(a, sp.Symbol):
        return 'cartesian', [a]
    raise VCError(f'invalid coordinate system {a}')


def _coords(ctx, spec=None, opts=None):
    if opts and 'coords' in opts:
        spec = opts['coords']
    if spec is not None:
        sysname, syms = _parse_coord(ctx, spec)
        if not syms:
            syms = [_sym(ctx, n) for n in DEFAULT_NAMES.get(sysname, [])]
    else:
        cur = getattr(ctx, 'coords', None)
        if cur:
            sysname, syms = cur
        else:
            sysname, syms = 'cartesian', [_sym(ctx, n) for n in DEFAULT_NAMES['cartesian']]
    if sysname not in SYSTEMS:
        raise VCError(f'unknown coordinate system {sysname}')
    n_exp = {'polar': 2, 'cylindrical': 3, 'spherical': 3}.get(sysname)
    if n_exp and len(syms) != n_exp:
        raise VCError(f'{sysname} needs {n_exp} coordinates')
    return sysname, list(syms)


def _scale(sysname, q):
    """-> (h-lijst, oriëntatieteken s) voor orthogonale coordinaten."""
    n = len(q)
    if sysname == 'cartesian':
        return [sp.Integer(1)] * n, 1
    if sysname in ('polar', 'cylindrical'):
        h = [sp.Integer(1), q[0]] + ([sp.Integer(1)] if len(q) == 3 else [])
        return h, 1
    if sysname == 'spherical':
        r, th, ph = q
        return [sp.Integer(1), r * sp.sin(ph), r], -1    # (r,theta,phi) is linkshandig
    raise VCError('unknown system')


def _cart_map(sysname, q):
    """Cartesische coordinaten als functie van q."""
    if sysname == 'cartesian':
        return list(q)
    if sysname in ('polar', 'cylindrical'):
        r, th = q[0], q[1]
        return [r * sp.cos(th), r * sp.sin(th)] + ([q[2]] if len(q) == 3 else [])
    r, th, ph = q
    return [r * sp.cos(th) * sp.sin(ph), r * sp.sin(th) * sp.sin(ph), r * sp.cos(ph)]


def _S(e):
    return sp.simplify(e)


def _is_vec(x):
    return isinstance(x, sp.MatrixBase)


def _comp(F):
    return list(F)


def _col(lst):
    return sp.Matrix(list(lst))


def _tolist(x):
    return list(x)


# ---------------------------------------------------------------- operatoren
def grad(f, sysname, q):
    h, s = _scale(sysname, q)
    return _col([_S(sp.diff(f, qi) / hi) for qi, hi in zip(q, h)])


def div(F, sysname, q):
    h, s = _scale(sysname, q)
    comps = _comp(F)
    if len(comps) != len(q):
        raise VCError('Divergence: dimension mismatch')
    H = sp.Mul(*h)
    return _S(sum(sp.diff(H * c / hi, qi) for c, hi, qi in zip(comps, h, q)) / H)


def curl(F, sysname, q):
    h, s = _scale(sysname, q)
    c = _comp(F)
    if len(q) == 2 and len(c) == 2:
        h1, h2 = h
        return _S((sp.diff(h2 * c[1], q[0]) - sp.diff(h1 * c[0], q[1])) / (h1 * h2))
    if len(q) != 3 or len(c) != 3:
        raise VCError('Curl: needs 3-dimensional field')
    h1, h2, h3 = h
    f1, f2, f3 = [hh * cc for hh, cc in zip(h, c)]
    d = sp.diff
    r = [(d(f3, q[1]) - d(f2, q[2])) * h1 / (h1 * h2 * h3),
         (d(f1, q[2]) - d(f3, q[0])) * h2 / (h1 * h2 * h3),
         (d(f2, q[0]) - d(f1, q[1])) * h3 / (h1 * h2 * h3)]
    return _col([_S(s * e) for e in r])


def lap(f, sysname, q):
    if _is_vec(f):
        if sysname == 'cartesian':
            return f.applyfunc(lambda e: lap(e, sysname, q))
        g = grad(div(f, sysname, q), sysname, q)
        return _col([_S(a - b) for a, b in zip(g, curl(curl(f, sysname, q), sysname, q))])
    h, s = _scale(sysname, q)
    H = sp.Mul(*h)
    return _S(sum(sp.diff(H / hi ** 2 * sp.diff(f, qi), qi) for hi, qi in zip(h, q)) / H)


def _split(ctx, args):
    pos, opts = [], {}
    for a in args:
        if hasattr(a, 'lhs') and hasattr(a, 'rhs') and isinstance(a.lhs, sp.Symbol) and a.lhs.name == 'coords':
            opts['coords'] = a.rhs
        else:
            pos.append(a)
    return pos, opts


@maple('Gradient', pkg=PKG)
def Gradient(ctx, f, *rest):
    pos, o = _split(ctx, rest)
    sysname, q = _coords(ctx, pos[0] if pos else None, o)
    return grad(f, sysname, q)


@maple('Divergence', pkg=PKG)
def Divergence(ctx, F, *rest):
    pos, o = _split(ctx, rest)
    sysname, q = _coords(ctx, pos[0] if pos else None, o)
    return div(la._vec(F), sysname, q)


@maple('Curl', pkg=PKG)
def Curl(ctx, F, *rest):
    pos, o = _split(ctx, rest)
    sysname, q = _coords(ctx, pos[0] if pos else None, o)
    return curl(la._vec(F), sysname, q)


@maple('Laplacian', pkg=PKG)
def Laplacian(ctx, f, *rest):
    pos, o = _split(ctx, rest)
    sysname, q = _coords(ctx, pos[0] if pos else None, o)
    return lap(la._vec(f) if _is_vec(f) else f, sysname, q)


@maple('Del', 'Nabla', pkg=PKG)
def Del(ctx, f, *rest):
    """Del(f): gradient van een scalar, divergentie van een vectorveld."""
    return Divergence(ctx, f, *rest) if _is_vec(f) else Gradient(ctx, f, *rest)


@maple('VectorField', pkg=PKG)
def VectorField(ctx, F, *rest):
    return la._vec(F)


@maple('ScalarPotential', pkg=PKG)
def ScalarPotential(ctx, F, *rest):
    pos, o = _split(ctx, rest)
    sysname, q = _coords(ctx, pos[0] if pos else None, o)
    if sysname != 'cartesian':
        raise VCError('ScalarPotential: only cartesian supported')
    F = _comp(la._vec(F))
    phi = sp.Integer(0)
    for k, (c, v) in enumerate(zip(F, q)):
        rest_k = sp.simplify(c - sp.diff(phi, v))
        if any(rest_k.has(w) for w in q[:k]):
            return sp.Symbol('FAIL')
        phi += sp.integrate(rest_k, v)
    if any(sp.simplify(sp.diff(phi, v) - c) != 0 for c, v in zip(F, q)):
        return sp.Symbol('FAIL')
    return sp.simplify(phi)


@maple('ConvertCoordinates', pkg=PKG)
def ConvertCoordinates(ctx, pt, frm, to=None, *rest):
    """ConvertCoordinates([a,b,c], van, naar): punt of expressielijst naar een ander stelsel."""
    if to is None:
        to, frm = frm, 'cartesian'
    f, _ = _parse_coord(ctx, frm)
    t, _ = _parse_coord(ctx, to)
    p = list(pt)
    if f == 'cartesian':
        c = p
    else:
        c = _cart_map(f, p)
    if t == 'cartesian':
        out = c
    elif t == 'polar':
        out = [sp.sqrt(c[0] ** 2 + c[1] ** 2), sp.atan2(c[1], c[0])]
    elif t == 'cylindrical':
        out = [sp.sqrt(c[0] ** 2 + c[1] ** 2), sp.atan2(c[1], c[0]), c[2]]
    else:
        r = sp.sqrt(c[0] ** 2 + c[1] ** 2 + c[2] ** 2)
        out = [r, sp.atan2(c[1], c[0]), sp.acos(c[2] / r)]
    out = [sp.simplify(e) for e in out]
    return MList(out) if isinstance(pt, (list, tuple)) else _col(out)


@maple('VectorPotential', pkg=PKG)
def VectorPotential(ctx, F, *rest):
    pos, o = _split(ctx, rest)
    sysname, q = _coords(ctx, pos[0] if pos else None, o)
    if sysname != 'cartesian' or len(q) != 3:
        raise VCError('VectorPotential: only cartesian 3D supported')
    P, Q, R = _comp(la._vec(F))
    if sp.simplify(sum(sp.diff(c, v) for c, v in zip((P, Q, R), q))) != 0:
        return sp.Symbol('FAIL')
    x, y, z = q
    w = sp.Dummy('w')
    Ax = sp.integrate(Q.subs(z, w), (w, 0, z))
    Ay = -sp.integrate(P.subs(z, w), (w, 0, z)) + sp.integrate(R.subs(z, 0).subs(x, w), (w, 0, x))
    return _col([_S(Ax), _S(Ay), sp.Integer(0)])


# ---------------------------------------------------------------- matrix-achtige
def _varlist(ctx, v):
    if v is None:
        return _coords(ctx)[1]
    if isinstance(v, (list, tuple)):
        return list(v)
    if _is_vec(v):
        return list(v)
    return [v]


def _flag(rest, name):
    return any(isinstance(x, sp.Symbol) and x.name == name for x in rest) or any(
        isinstance(x, sp.Equality) and str(x.lhs) == name and str(x.rhs) == 'true' for x in rest)


@maple('Jacobian', pkg=PKG)
def Jacobian(ctx, F, vars=None, *rest):
    F = list(F) if isinstance(F, (list, tuple)) or _is_vec(F) else [F]
    J = sp.Matrix(F).jacobian(_varlist(ctx, vars))
    return _S(J.det()) if _flag(rest, 'determinant') else J


@maple('Hessian', pkg=PKG)
def Hessian(ctx, f, vars=None, *rest):
    H = sp.hessian(f, _varlist(ctx, vars))
    return _S(H.det()) if _flag(rest, 'determinant') else H


@maple('Wronskian', pkg=PKG)
def Wronskian(ctx, fs, x, *rest):
    fs = list(fs)
    n = len(fs)
    W = sp.Matrix(n, n, lambda i, j: sp.diff(fs[j], x, i) if i else fs[j])
    return _S(W.det()) if _flag(rest, 'determinant') else W


@maple('SetCoordinates', pkg=PKG)
def SetCoordinates(ctx, spec=None, *rest):
    if spec is None:
        spec = sp.Symbol('cartesian')
    sysname, syms = _parse_coord(ctx, spec)
    if not syms:
        syms = [_sym(ctx, n) for n in DEFAULT_NAMES[sysname]]
    _coords(ctx, (sysname, syms))        # valideren
    ctx.coords = (sysname, list(syms))
    return sp.Symbol(sysname)


# ---------------------------------------------------------------- integralen
def _rng(r):
    """t=a..b -> (t, a, b)."""
    if isinstance(r, (tuple, list)) and len(r) == 2 and isinstance(r[1], Range):
        return r[0], r[1].lo, r[1].hi
    lhs, rhs = getattr(r, 'lhs', None), getattr(r, 'rhs', None)
    if lhs is None:
        raise VCError('expected parameter range t=a..b')
    if isinstance(rhs, Range):
        return lhs, rhs.lo, rhs.hi
    if isinstance(rhs, (sp.Tuple, tuple, list)):
        return lhs, rhs[0], rhs[1]
    if isinstance(rhs, sp.Interval):
        return lhs, rhs.start, rhs.end
    raise VCError('expected parameter range t=a..b')


def _is_range(x):
    try:
        _rng(x)
        return True
    except Exception:
        return False


def _on_path(ctx, F, r, q):
    return F.subs(dict(zip(q, r)), simultaneous=True)


def _path_args(ctx, rest):
    pos, o = _split(ctx, rest)
    ranges = [a for a in pos if _is_range(a)]
    other = [a for a in pos if not _is_range(a)]
    sysname, q = _coords(ctx, other[0] if other else None, o)
    return [_rng(r) for r in ranges], sysname, q


def _line(ctx, F, path, rest):
    ranges, sysname, q = _path_args(ctx, rest)
    if len(ranges) != 1:
        raise VCError('LineInt: need one parameter range')
    t, a, b = ranges[0]
    r = _comp(la._vec(path))
    dr = [sp.diff(c, t) for c in r]
    sub = dict(zip(q, r))
    if _is_vec(F):
        integrand = sum(c.subs(sub, simultaneous=True) * d for c, d in zip(la._vec(F), dr))
    else:
        integrand = F.subs(sub, simultaneous=True) * sp.sqrt(sum(d ** 2 for d in dr))
    return _S(sp.integrate(sp.simplify(integrand), (t, a, b)))


@maple('LineInt', pkg=PKG)
def LineInt(ctx, F, path, *rest):
    """LineInt(F, r(t), t=a..b [, coords]) (cartesisch): veld F (vector) of scalar f langs parametrisatie r(t)."""
    return _line(ctx, F, path, rest)


@maple('Circulation', pkg=PKG)
def Circulation(ctx, F, path, *rest):
    return _line(ctx, F, path, rest)


def _surface(ctx, F, surf, rest, flux):
    ranges, sysname, q = _path_args(ctx, rest)
    if len(ranges) != 2:
        raise VCError('need two parameter ranges u=a..b, v=c..d')
    (u, a, b), (v, c, d) = ranges
    r = _comp(la._vec(surf))
    ru = sp.Matrix([sp.diff(e, u) for e in r])
    rv = sp.Matrix([sp.diff(e, v) for e in r])
    n = ru.cross(rv)
    sub = dict(zip(q, r))
    if flux:
        Fc = la._vec(F)
        integrand = sum(Fc[i].subs(sub, simultaneous=True) * n[i] for i in range(3))
    else:
        integrand = F.subs(sub, simultaneous=True) * sp.sqrt(sp.simplify(n.dot(n)))
    inner = sp.integrate(sp.simplify(integrand), (u, a, b))
    return _S(sp.integrate(inner, (v, c, d)))


@maple('SurfaceInt', pkg=PKG)
def SurfaceInt(ctx, F, surf, *rest):
    """SurfaceInt(f, r(u,v), u=a..b, v=c..d [, coords]); vectorveld -> flux."""
    return _surface(ctx, F, surf, rest, _is_vec(F))


@maple('Flux', pkg=PKG)
def Flux(ctx, F, surf, *rest):
    return _surface(ctx, F, surf, rest, True)


# DotProduct / CrossProduct zijn ook onderdeel van VectorCalculus
for _n in ('DotProduct', 'CrossProduct'):
    if _n not in PACKAGES.setdefault(PKG, []):
        PACKAGES[PKG].append(_n)
