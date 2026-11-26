"""Generieke Maple-builtins (kern). Registratie via CORE; interp.install() voegt ze toe aan values.BUILTINS
zonder builtins van andere modules te overschrijven (behalve `convert`, dat samengevoegd wordt)."""
import math
import random
import re
import time as _time
import sympy as sp

from .values import BUILTINS, PACKAGES, MList, MSet, Seq, Range, Str, Table, Plot
from .objs import MapleError, MProc, DOp, PyFn, Composition, Repeat, TypeDecl, RangeB, mkset, same
from . import printer

CORE = {}
_PKG = {}
_installed_convert = False


def core(*names, pkg=None):
    def deco(fn):
        for n in names:
            CORE[n] = fn
            if pkg:
                _PKG.setdefault(pkg, []).append(n)
        return fn
    return deco


def install():
    global _installed_convert
    for n, fn in CORE.items():
        if n == "convert":
            continue
        if n not in BUILTINS:
            BUILTINS[n] = fn
    for pkg, names in _PKG.items():
        PACKAGES.setdefault(pkg, [])
        for n in names:
            if n not in PACKAGES[pkg]:
                PACKAGES[pkg].append(n)
    prev = BUILTINS.get("convert")
    if prev is not _convert_wrapper:
        _convert_wrapper.prev = prev
        BUILTINS["convert"] = _convert_wrapper


# ------------------------------------------------------------------ hulpfuncties
def flat(x):
    """container -> python-lijst van elementen."""
    if isinstance(x, sp.MatrixBase):
        return list(x)
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


def T(v):
    return printer.to_text(v)


def truth(ctx, v):
    f = getattr(ctx, "truth", None)
    if f:
        return f(v)
    return v is True or v is sp.true


def B(b):
    return sp.true if b else sp.false


def num(x):
    return isinstance(x, sp.Basic) and x.is_number


def is_int(x):
    return isinstance(x, sp.Integer)


def pyint(x, what="integer"):
    if isinstance(x, sp.Integer):
        return int(x)
    if isinstance(x, sp.Basic) and x.is_Integer:
        return int(x)
    raise MapleError(f"invalid input: {what} expected, but received {T(x)}")


def subs_value(e, pairs):
    """pairs: lijst (oud, nieuw)."""
    if not pairs:
        return e
    if isinstance(e, sp.Basic):
        try:
            cplx = [p for p in pairs if not isinstance(p[0], sp.Symbol)]
            if cplx and len(cplx) < len(pairs):
                e = e.subs(cplx, simultaneous=True)
                pairs = [p for p in pairs if isinstance(p[0], sp.Symbol)]
            return e.subs(pairs, simultaneous=True)
        except Exception:
            return e.subs(pairs)
    if isinstance(e, sp.MatrixBase):
        return e.applyfunc(lambda x: subs_value(x, pairs))
    if isinstance(e, MSet):
        return mkset([subs_value(x, pairs) for x in e])
    if isinstance(e, (MList, Seq)):
        return type(e)([subs_value(x, pairs) for x in e])
    if isinstance(e, sp.Equality) or (hasattr(e, "args") and type(e).__name__ in ("Equality", "Unequality")):
        l, r = subs_value(e.lhs, pairs), subs_value(e.rhs, pairs)
        if isinstance(l, sp.Basic) and isinstance(r, sp.Basic):
            return sp.Eq(l, r, evaluate=False)
        return sp.Basic.__new__(sp.Equality, l, r)
    return e


def eq_pairs(args):
    pairs = []
    for a in args:
        if isinstance(a, (list, tuple)):
            pairs.extend(eq_pairs(a))
        elif isinstance(a, sp.Equality) or type(a).__name__ == "Equality":
            pairs.append((a.lhs, a.rhs))
        else:
            raise MapleError("invalid substitution argument: equation or list/set of equations expected")
    return pairs


# ------------------------------------------------------------------ types
def check_type(ctx, v, t):
    if isinstance(t, (MSet, MList)):
        return any(check_type(ctx, v, x) for x in t)
    args = ()
    if isinstance(t, sp.Symbol):
        name = t.name
    elif isinstance(t, sp.core.function.AppliedUndef):
        name = t.func.__name__
        args = t.args
    elif isinstance(t, sp.Indexed):
        name = str(t.base)
    elif isinstance(t, str):
        name = str(t)
    elif isinstance(t, (sp.And, sp.Or, sp.Not)):
        return check_type(ctx, v, sp.Function(type(t).__name__)(*t.args))
    else:
        raise MapleError(f"invalid type specification: {T(t)}")
    if args or name in ("list", "set", "And", "Or", "Not", "Vector", "Matrix", "range", "specfunc", "function", "symbol"):
        if name == "list" and args:
            return isinstance(v, MList) and all(check_type(ctx, x, args[0]) for x in v)
        if name == "set" and args:
            return isinstance(v, MSet) and all(check_type(ctx, x, args[0]) for x in v)
        if name == "And":
            return all(check_type(ctx, v, a) for a in args)
        if name == "Or":
            return any(check_type(ctx, v, a) for a in args)
        if name == "Not":
            return not check_type(ctx, v, args[0])
        if name == "Vector" and args:
            return isinstance(v, sp.MatrixBase) and (v.cols == 1 or v.rows == 1) and all(check_type(ctx, x, args[0]) for x in v)
        if name == "Matrix" and args:
            return isinstance(v, sp.MatrixBase) and all(check_type(ctx, x, args[0]) for x in v)
        if name == "range":
            return isinstance(v, Range)
        if name in ("specfunc", "function") and args:
            if isinstance(v, sp.Function) or isinstance(v, sp.core.function.AppliedUndef):
                fn = args[-1] if name == "specfunc" else None
                return fn is None or v.func.__name__ == getattr(fn, "name", str(fn))
            return False
    isb = isinstance(v, sp.Basic)
    if name in ("anything",):
        return True
    if name == "integer":
        return isinstance(v, sp.Integer)
    if name == "posint":
        return isinstance(v, sp.Integer) and v > 0
    if name in ("negint",):
        return isinstance(v, sp.Integer) and v < 0
    if name in ("nonnegint",):
        return isinstance(v, sp.Integer) and v >= 0
    if name in ("nonposint",):
        return isinstance(v, sp.Integer) and v <= 0
    if name == "natural":
        return isinstance(v, sp.Integer) and v > 0
    if name == "even":
        return isinstance(v, sp.Integer) and v % 2 == 0
    if name == "odd":
        return isinstance(v, sp.Integer) and v % 2 == 1
    if name == "prime":
        return isinstance(v, sp.Integer) and sp.isprime(v)
    if name == "rational":
        return isinstance(v, sp.Rational)
    if name == "fraction":
        return isinstance(v, sp.Rational) and not isinstance(v, sp.Integer)
    if name == "float":
        return isinstance(v, sp.Float)
    if name == "numeric":
        return isinstance(v, (sp.Rational, sp.Float))
    if name in ("realcons", "real"):
        return isb and v.is_number and v.is_real is not False and (v.is_real or name == "real" and v.is_real)
    if name in ("complex", "complexcons"):
        return isb and v.is_number
    if name == "constant":
        return isb and v.is_number
    if name in ("algebraic", "algnum", "radnum"):
        return isb and not isinstance(v, (sp.core.relational.Relational, sp.logic.boolalg.Boolean)) or (isb and v in (sp.true, sp.false) and False)
    if name == "positive":
        return isb and v.is_number and v.is_real and v > 0 or (isb and v.is_positive is True)
    if name == "negative":
        return isb and v.is_number and v.is_real and v < 0 or (isb and v.is_negative is True)
    if name == "nonzero":
        return isb and v != 0
    if name in ("name", "symbol"):
        return isinstance(v, (sp.Symbol, sp.Indexed)) and not isinstance(v, sp.Dummy) or (name == "name" and isinstance(v, sp.Indexed))
    if name == "string":
        return isinstance(v, Str)
    if name == "list":
        return isinstance(v, MList)
    if name == "set":
        return isinstance(v, MSet)
    if name == "exprseq":
        return isinstance(v, Seq)
    if name in ("Matrix", "matrix"):
        return isinstance(v, sp.MatrixBase)
    if name in ("Vector", "vector"):
        return isinstance(v, sp.MatrixBase) and (v.cols == 1 or v.rows == 1)
    if name == "Array":
        return isinstance(v, sp.MatrixBase)
    if name == "table":
        return isinstance(v, Table)
    if name in ("function", "specfunc"):
        return isinstance(v, sp.Function) and not v.is_Number
    if name in ("procedure", "proc"):
        return isinstance(v, (MProc, PyFn, Composition, Repeat))
    if name in ("equation", "="):
        return isinstance(v, sp.Equality) or type(v).__name__ == "Equality"
    if name == "<>":
        return type(v).__name__ == "Unequality"
    if name in ("relation", "relational"):
        return isinstance(v, sp.core.relational.Relational)
    if name in ("boolean", "truefalse"):
        return v is sp.true or v is sp.false or isinstance(v, bool)
    if name in ("+", "`+`"):
        return isinstance(v, sp.Add)
    if name in ("*", "`*`"):
        return isinstance(v, sp.Mul)
    if name in ("^", "`^`"):
        return isinstance(v, sp.Pow)
    if name == "range":
        return isinstance(v, Range)
    if name == "atomic":
        return isb and v.is_Atom
    if name == "polynom":
        if not isb:
            return False
        try:
            return sp.Poly(v, *v.free_symbols).is_polynomial if v.free_symbols else True
        except Exception:
            return False
    if name == "rational_expr" or name == "ratpoly":
        return isb
    if name == "Heaviside":
        return isinstance(v, sp.Heaviside)
    if name == "trig":
        return isinstance(v, sp.TrigonometricFunction)
    if name == "NumericalType":
        return isb and v.is_number
    if name == "undefined":
        return v == sp.nan
    # onbekend type: functienaam?
    if isb and isinstance(v, sp.Function) and v.func.__name__ == name:
        return True
    return False


def whattype(v):
    if isinstance(v, sp.Integer):
        return "integer"
    if isinstance(v, sp.Rational):
        return "fraction"
    if isinstance(v, sp.Float):
        return "float"
    if isinstance(v, Str):
        return "string"
    if isinstance(v, MList):
        return "list"
    if isinstance(v, MSet):
        return "set"
    if isinstance(v, Seq):
        return "exprseq"
    if isinstance(v, sp.MatrixBase):
        return "Matrix" if v.rows != 1 and v.cols != 1 else "Vector"
    if isinstance(v, Table):
        return "table"
    if isinstance(v, Range):
        return ".."
    if isinstance(v, (MProc, PyFn, Composition)):
        return "procedure"
    if isinstance(v, sp.Add):
        return "+"
    if isinstance(v, sp.Mul):
        return "*"
    if isinstance(v, sp.Pow):
        return "^"
    if isinstance(v, sp.Symbol):
        return "symbol"
    if isinstance(v, sp.Indexed):
        return "indexed"
    if isinstance(v, sp.Equality):
        return "="
    if isinstance(v, sp.core.relational.Relational):
        return {"StrictLessThan": "<", "LessThan": "<=", "Unequality": "<>"}.get(type(v).__name__, ">")
    if v is sp.true or v is sp.false:
        return "symbol"
    if isinstance(v, sp.Function):
        return "function"
    if isinstance(v, (sp.NumberSymbol,)) or v is sp.pi:
        return "symbol"
    if isinstance(v, sp.Basic):
        return type(v).__name__
    return type(v).__name__


@core("type")
def _type(ctx, e, t, *rest):
    return B(check_type(ctx, e, t))


@core("whattype")
def _whattype(ctx, e):
    return sp.Symbol(whattype(e))


@core("is")
def _is(ctx, e, prop=None):
    if prop is not None:
        if isinstance(e, sp.Symbol) or isinstance(e, sp.Basic):
            name = prop.name if isinstance(prop, sp.Symbol) else None
            attr = {"real": "is_real", "integer": "is_integer", "positive": "is_positive", "negative": "is_negative",
                    "rational": "is_rational", "nonnegative": "is_nonnegative", "nonpositive": "is_nonpositive",
                    "posint": None, "even": "is_even", "odd": "is_odd", "prime": "is_prime", "complex": "is_complex",
                    "nonzero": "is_nonzero", "irrational": "is_irrational", "zero": "is_zero"}.get(name, "")
            if attr:
                r = getattr(e, attr)
                return B(r) if r is not None else sp.Symbol("FAIL")
            if name == "posint":
                r = e.is_integer and e.is_positive
                return B(r) if r is not None else sp.Symbol("FAIL")
        return B(check_type(ctx, e, prop))
    t = truth(ctx, e)
    if t is None and isinstance(e, sp.core.relational.Relational) and getattr(ctx, "intervals", None):
        fs = list(e.free_symbols)
        if len(fs) == 1 and fs[0].name in ctx.intervals:
            x = fs[0]
            S = ctx.intervals[x.name]
            try:
                xs = sp.Symbol(x.name, real=True)
                sol = sp.solveset(e.xreplace({x: xs}), xs, S)
                if sol == S:
                    return sp.true
                if sol is sp.S.EmptySet:
                    return sp.false
            except Exception:
                pass
    if t is None:
        if isinstance(e, sp.core.relational.Relational):
            try:
                d = sp.simplify(e.lhs - e.rhs)
                if isinstance(e, sp.StrictGreaterThan):
                    r = d.is_positive
                elif isinstance(e, sp.GreaterThan):
                    r = d.is_nonnegative
                elif isinstance(e, sp.StrictLessThan):
                    r = d.is_negative
                elif isinstance(e, sp.LessThan):
                    r = d.is_nonpositive
                else:
                    r = None
                if r is not None:
                    return B(r)
            except Exception:
                pass
        return sp.Symbol("FAIL")
    return B(t)


@core("evalb")
def _evalb(ctx, e):
    t = truth(ctx, e)
    if t is None:
        if isinstance(e, sp.core.relational.Relational):
            raise MapleError(f"cannot evaluate boolean: {T(e)}")
        return e
    return B(t)


@core("has")
def _has(ctx, e, pats):
    ps = flat(pats) if isinstance(pats, (list, tuple)) else [pats]

    def h(x, p):
        if isinstance(x, sp.Basic):
            try:
                return x.has(p)
            except Exception:
                return False
        if isinstance(x, sp.MatrixBase):
            return any(h(y, p) for y in x)
        if isinstance(x, (list, tuple)):
            return any(h(y, p) for y in x)
        if isinstance(x, str) and isinstance(p, str):
            return str(p) in str(x)
        return same(x, p)
    return B(any(h(e, p) for p in ps))


# ------------------------------------------------------------------ structuur
@core("nops", "numelems")
def nops(ctx, e):
    if isinstance(e, (list, tuple)):
        return sp.Integer(len(e))
    if isinstance(e, sp.MatrixBase):
        return sp.Integer(e.rows * e.cols)
    if isinstance(e, Table):
        return sp.Integer(len(e))
    if isinstance(e, Str):
        return sp.Integer(1)
    if isinstance(e, Range):
        return sp.Integer(2)
    if isinstance(e, sp.Basic):
        if isinstance(e, sp.Rational) and not isinstance(e, sp.Integer):
            return sp.Integer(2)
        return sp.Integer(len(e.args) if e.args else 1)
    return sp.Integer(1)


def _operands(e):
    if isinstance(e, (list, tuple)):
        return list(e)
    if isinstance(e, sp.MatrixBase):
        return list(e)
    if isinstance(e, Range):
        return [e.lo, e.hi]
    if isinstance(e, Table):
        return [sp.Basic.__new__(sp.Equality, k, v) for k, v in e.items()]
    if isinstance(e, sp.Rational) and not isinstance(e, sp.Integer):
        return [sp.Integer(e.p), sp.Integer(e.q)]
    if isinstance(e, sp.Add):
        try:
            return list(e.as_ordered_terms())          # zelfde volgorde als de uitvoer (x^2 + 1)
        except Exception:
            return list(e.args)
    if isinstance(e, sp.Mul):
        try:
            return list(e.as_ordered_factors())
        except Exception:
            return list(e.args)
    if isinstance(e, sp.Basic):
        return list(e.args) if e.args else [e]
    return [e]


@core("op")
def op(ctx, *a):
    if len(a) == 1:
        r = _operands(a[0])
        return Seq(r)
    n, e = a[0], a[1]
    if isinstance(n, Range):
        r = _operands(e)
        lo, hi = pyint(n.lo), pyint(n.hi)
        return Seq(r[lo - 1:hi])
    i = pyint(n)
    if i == 0:
        if isinstance(e, (MList,)):
            return sp.Symbol("list")
        if isinstance(e, MSet):
            return sp.Symbol("set")
        if isinstance(e, sp.Add):
            return sp.Symbol("+")
        if isinstance(e, sp.Mul):
            return sp.Symbol("*")
        if isinstance(e, sp.Pow):
            return sp.Symbol("^")
        if isinstance(e, sp.Function):
            return sp.Symbol(e.func.__name__)
        return sp.Symbol(whattype(e))
    r = _operands(e)
    if i < 0:
        i += len(r) + 1
    if i < 1 or i > len(r):
        raise MapleError(f"invalid subscript selector")
    return r[i - 1]


@core("lhs")
def lhs(ctx, e):
    if isinstance(e, Range):
        return e.lo
    return e.lhs


@core("rhs")
def rhs(ctx, e):
    if isinstance(e, Range):
        return e.hi
    return e.rhs


def _call_bool(ctx, f, x, extra):
    r = ctx.call(f, x, *extra)
    t = truth(ctx, r)
    if t is None:
        raise MapleError(f"cannot determine if this expression is true or false: {T(r)}")
    return t


@core("map")
def map_(ctx, f, e, *extra):
    def one(x):
        return ctx.call(f, x, *extra)
    if isinstance(e, MList):
        return MList(_flatseq([one(x) for x in e]))
    if isinstance(e, MSet):
        return mkset(_flatseq([one(x) for x in e]))
    if isinstance(e, Seq):
        return Seq(_flatseq([one(x) for x in e]))
    if isinstance(e, sp.MatrixBase):
        return e.applyfunc(one)
    if isinstance(e, Table):
        t = Table()
        for k, v in e.items():
            t[k] = one(v)
        return t
    if isinstance(e, Range):
        return RangeB(one(e.lo), one(e.hi))
    if isinstance(e, sp.Basic) and e.args and not e.is_Atom:
        if isinstance(e, sp.Rational):
            return one(e)
        try:
            return e.func(*[one(a) for a in e.args])
        except Exception:
            return e.func(*[one(a) for a in e.args], evaluate=False)
    return one(e)


def _flatseq(items):
    out = []
    for x in items:
        if isinstance(x, Seq):
            out.extend(x)
        else:
            out.append(x)
    return out


@core("select")
def select(ctx, f, e, *extra):
    if isinstance(e, sp.Basic) and not isinstance(e, Range) and not isinstance(e, sp.Equality) and e.args and isinstance(e, (sp.Add, sp.Mul)):
        return e.func(*[x for x in e.args if _call_bool(ctx, f, x, extra)])
    items = flat(e) if not isinstance(e, sp.MatrixBase) else list(e)
    res = [x for x in items if _call_bool(ctx, f, x, extra)]
    return mkset(res) if isinstance(e, MSet) else (Seq(res) if isinstance(e, Seq) else MList(res))


@core("remove")
def remove(ctx, f, e, *extra):
    if isinstance(e, (sp.Add, sp.Mul)):
        return e.func(*[x for x in e.args if not _call_bool(ctx, f, x, extra)])
    items = flat(e)
    res = [x for x in items if not _call_bool(ctx, f, x, extra)]
    return mkset(res) if isinstance(e, MSet) else (Seq(res) if isinstance(e, Seq) else MList(res))


@core("selectremove")
def selectremove(ctx, f, e, *extra):
    return Seq([select(ctx, f, e, *extra), remove(ctx, f, e, *extra)])


@core("member")
def member(ctx, x, L, p=None):
    if isinstance(L, Str) and isinstance(x, Str):
        pos = str(L).find(str(x))
        found = pos >= 0
        pos += 1
    else:
        items = flat(L)
        pos = 0
        found = False
        for i, y in enumerate(items):
            if same(x, y) or (isinstance(x, sp.Basic) and isinstance(y, sp.Basic) and x.is_number and y.is_number and x == y):
                found, pos = True, i + 1
                break
    if found and isinstance(p, sp.Symbol):
        ctx.assign(p.name, sp.Integer(pos))
    return B(found)


def _skey(x):
    if isinstance(x, sp.Basic) and x.is_number and x.is_real:
        try:
            return (0, float(sp.N(x)), "")
        except Exception:
            pass
    if isinstance(x, str):
        return (1, 0.0, str(x))
    return (2, 0.0, sp.default_sort_key(x) if isinstance(x, sp.Basic) else str(x))


@core("sort")
def sort(ctx, L, f=None, *rest):
    if isinstance(L, (list, tuple)):
        import functools
        items = list(L)
        if f is None or (isinstance(f, sp.Symbol) and f.name in ("<", "<=")):
            items.sort(key=_skey)
        elif isinstance(f, sp.Symbol) and f.name in (">", ">="):
            items.sort(key=_skey, reverse=True)
        else:
            def cmp(a, b):
                if _call_bool(ctx, f, a, (b,)):
                    return -1
                if _call_bool(ctx, f, b, (a,)):
                    return 1
                return 0
            items.sort(key=functools.cmp_to_key(cmp))
        return type(L)(items) if not isinstance(L, MSet) else MList(items)
    return L


@core("zip")
def zip_(ctx, f, A, B_, default=None):
    a, b = flat(A), flat(B_)
    if default is not None:
        n = max(len(a), len(b))
        a += [default] * (n - len(a))
        b += [default] * (n - len(b))
    return MList([ctx.call(f, x, y) for x, y in zip(a, b)])


@core("unapply")
def unapply(ctx, expr, *vars_):
    vs = []
    for v in vars_:
        vs.extend(flat(v) if isinstance(v, (list, tuple)) else [v])
    names = [v.name if isinstance(v, sp.Symbol) else str(v) for v in vs]

    def py(c, *a, _e=expr, _v=vs):
        return subs_value(_e, list(zip(_v, a)))
    params = names[0] if len(names) == 1 else "(" + ", ".join(names) + ")"
    return MProc(params=[(n, None, None) for n in names], py=py, arrow=True, src=f"{params} -> {T(expr)}")


@core("subs")
def subs(ctx, *a):
    if len(a) < 2:
        raise MapleError("invalid input: subs expects at least 2 arguments")
    e = a[-1]
    for eqs in a[:-1]:
        e = subs_value(e, eq_pairs([eqs]))
    return e


@core("eval")
def eval_(ctx, e, *eqs):
    if not eqs:
        return e
    return subs_value(e, eq_pairs(list(eqs)))


@core("allvalues")
def allvalues(ctx, *a):
    return a[0] if len(a) == 1 else Seq(a)


@core("evalm", "Evalm")
def evalm(ctx, e):
    return e


# ------------------------------------------------------------------ evalf & getal
def _evalf(x, d):
    if isinstance(x, sp.MatrixBase):
        return x.applyfunc(lambda y: _evalf(y, d))
    if isinstance(x, (MList, MSet, Seq)):
        return type(x)([_evalf(y, d) for y in x])
    if isinstance(x, Range):
        return RangeB(_evalf(x.lo, d), _evalf(x.hi, d))
    if isinstance(x, sp.Equality):
        return sp.Eq(_evalf(x.lhs, d), _evalf(x.rhs, d), evaluate=False)
    if isinstance(x, sp.Basic):
        if x.is_Float and x._prec >= int(d * 3.32):
            return x
        if x.has(sp.Integral):
            x = x.xreplace({I: _num_integral(I, d) for I in x.atoms(sp.Integral)})
        return x.evalf(d)
    return x


def _num_integral(I, d):
    """Numerieke waarde van een (herhaalde) bepaalde integraal, ook met van elkaar afhankelijke grenzen."""
    import mpmath
    limits = [l for l in reversed(I.limits)]          # buitenste integraal eerst
    if any(len(l) != 3 for l in limits):
        return I
    old = mpmath.mp.dps
    mpmath.mp.dps = max(d, 15) + 5

    def num(e, env):
        return mpmath.mpmathify(sp.N(sp.sympify(e).subs(env), mpmath.mp.dps))

    def level(k, env):
        v, a, b = limits[k]
        lo, hi = num(a, env), num(b, env)
        if k == len(limits) - 1:
            return mpmath.quad(sp.lambdify(v, I.function.subs(env), "mpmath"), [lo, hi])
        return mpmath.quad(lambda t: level(k + 1, {**env, v: sp.Float(t, mpmath.mp.dps)}), [lo, hi])
    try:
        val = level(0, {})
        re_, im_ = mpmath.re(val), mpmath.im(val)
        out = sp.Float(re_, d)
        return out if abs(im_) < mpmath.mpf(10) ** (-d) else out + sp.I * sp.Float(im_, d)
    except Exception:
        return I
    finally:
        mpmath.mp.dps = old


@core("evalf")
def evalf(ctx, x, d=None):
    dd = pyint(d) if d is not None else ctx.digits
    return _evalf(x, dd)


@core("irem")
def irem(ctx, a, b, q=None):
    ai, bi = pyint(a), pyint(b)
    if bi == 0:
        raise MapleError("numeric exception: division by zero")
    qq = abs(ai) // abs(bi) * (1 if (ai >= 0) == (bi > 0) else -1)
    r = ai - bi * qq
    if isinstance(q, sp.Symbol):
        ctx.assign(q.name, sp.Integer(qq))
    return sp.Integer(r)


@core("iquo")
def iquo(ctx, a, b, r=None):
    ai, bi = pyint(a), pyint(b)
    if bi == 0:
        raise MapleError("numeric exception: division by zero")
    qq = abs(ai) // abs(bi) * (1 if (ai >= 0) == (bi > 0) else -1)
    if isinstance(r, sp.Symbol):
        ctx.assign(r.name, sp.Integer(ai - bi * qq))
    return sp.Integer(qq)


@core("modp")
def modp(ctx, a, n):
    return sp.Integer(pyint(a) % pyint(n))


@core("mods")
def mods(ctx, a, n):
    n_ = pyint(n)
    r = pyint(a) % n_
    return sp.Integer(r - n_ if r > n_ // 2 else r)


@core("gcd")
def gcd(ctx, *a):
    r = a[0]
    for x in a[1:]:
        r = sp.gcd(r, x)
    return r


@core("lcm")
def lcm(ctx, *a):
    r = a[0]
    for x in a[1:]:
        r = sp.lcm(r, x)
    return r


@core("igcd")
def igcd(ctx, *a):
    return sp.Integer(math.gcd(*[pyint(x) for x in a]))


@core("ilcm")
def ilcm(ctx, *a):
    return sp.Integer(math.lcm(*[pyint(x) for x in a]))


@core("isprime")
def isprime(ctx, n):
    return B(sp.isprime(pyint(n)))


@core("nextprime")
def nextprime(ctx, n):
    return sp.nextprime(pyint(n))


@core("prevprime")
def prevprime(ctx, n):
    return sp.prevprime(pyint(n))


@core("ithprime")
def ithprime(ctx, n):
    return sp.prime(pyint(n))


@core("isqrt")
def isqrt(ctx, n):
    return sp.Integer(math.isqrt(pyint(n)))


@core("ifactor")
def ifactor(ctx, n):
    k = pyint(n)
    if k in (0, 1, -1):
        return sp.Integer(k)
    f = sp.factorint(abs(k))
    parts = []
    for p, e in sorted(f.items()):
        parts.append(sp.Pow(p, e, evaluate=False) if e > 1 else sp.Integer(p))
    if k < 0:
        parts.insert(0, sp.Integer(-1))
    return sp.Mul(*parts, evaluate=False) if len(parts) > 1 else parts[0]


@core("ifactors")
def ifactors(ctx, n):
    k = pyint(n)
    f = sp.factorint(abs(k))
    return MList([sp.Integer(1 if k >= 0 else -1), MList([MList([sp.Integer(p), sp.Integer(e)]) for p, e in sorted(f.items())])])


@core("factorial")
def factorial(ctx, n):
    return sp.factorial(n)


@core("binomial")
def binomial(ctx, n, k):
    return sp.binomial(n, k)


@core("phi", pkg="numtheory")
def phi(ctx, n):
    return sp.totient(n)


@core("sigma", pkg="numtheory")
def sigma(ctx, n):
    return sp.divisor_sigma(n, 1)


@core("tau", pkg="numtheory")
def tau(ctx, n):
    return sp.divisor_count(n)


@core("divisors", pkg="numtheory")
def divisors(ctx, n):
    return MSet([sp.Integer(d) for d in sp.divisors(pyint(n))])


@core("mobius", pkg="numtheory")
def mobius(ctx, n):
    return sp.mobius(n)


def _items(args):
    out = []
    for a in args:
        if isinstance(a, (list, tuple, sp.MatrixBase)):
            out.extend(list(a))
        else:
            out.append(a)
    return out


@core("max")
def max_(ctx, *a):
    it = _items(a)
    if not it:
        return -sp.oo
    return sp.Max(*it) if len(it) > 1 else it[0]


@core("min")
def min_(ctx, *a):
    it = _items(a)
    if not it:
        return sp.oo
    return sp.Min(*it) if len(it) > 1 else it[0]


@core("abs")
def abs_(ctx, x):
    if isinstance(x, sp.MatrixBase):
        return x.applyfunc(sp.Abs)
    return sp.Abs(x)


@core("floor")
def floor(ctx, x):
    return sp.floor(x)


@core("ceil")
def ceil(ctx, x):
    return sp.ceiling(x)


@core("round")
def round_(ctx, x):
    if isinstance(x, sp.Basic) and x.is_number and x.is_real:
        return sp.floor(x + sp.Rational(1, 2)) if x >= 0 else -sp.floor(-x + sp.Rational(1, 2))
    return sp.Function("round")(x)


@core("trunc")
def trunc(ctx, x):
    if isinstance(x, sp.Basic) and x.is_number and x.is_real:
        return sp.floor(x) if x >= 0 else sp.ceiling(x)
    return sp.Function("trunc")(x)


@core("frac")
def frac(ctx, x):
    return x - trunc(ctx, x)


@core("sqrt")
def sqrt(ctx, x):
    return sp.sqrt(x)


@core("root")
def root(ctx, x, n=2):
    return x ** (sp.Integer(1) / n)


@core("surd")
def surd(ctx, x, n):
    return sp.real_root(x, n)


@core("exp")
def exp(ctx, x):
    if isinstance(x, sp.MatrixBase):
        from .values import BUILTINS
        return BUILTINS["MatrixExponential"](ctx, x)
    return sp.exp(x)


@core("ln")
def ln(ctx, x):
    return sp.log(x)


@core("log")
def log(ctx, x, b=None):
    if b is not None:
        return sp.log(b, x)  # log(b, x) in Maple: log_b(x)? gebruik log[b](x); hier: log(x, b)
    return sp.log(x)


@core("log10")
def log10(ctx, x):
    return sp.log(x, 10)


@core("log2")
def log2(ctx, x):
    return sp.log(x, 2)


def _fn(name, f):
    def g(ctx, *a):
        return f(*a)
    g.__name__ = name
    CORE[name] = g


for _n, _f in {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "cot": sp.cot, "sec": sp.sec, "csc": sp.csc,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "coth": sp.coth, "sech": sp.sech, "csch": sp.csch,
    "arcsin": sp.asin, "arccos": sp.acos, "arcsinh": sp.asinh, "arccosh": sp.acosh, "arctanh": sp.atanh,
    "arccoth": sp.acoth, "arcsec": sp.asec, "arccsc": sp.acsc, "arcsech": sp.asech, "arccsch": sp.acsch,
    "Re": sp.re, "Im": sp.im, "conjugate": sp.conjugate, "argument": sp.arg, "signum": sp.sign,
    "erf": sp.erf, "erfc": sp.erfc, "erfi": sp.erfi, "Zeta": sp.zeta, "LambertW": sp.LambertW,
    "Si": sp.Si, "Ci": sp.Ci, "Ei": sp.Ei, "AiryAi": sp.airyai, "AiryBi": sp.airybi, "Beta": sp.beta,
    "HermiteH": sp.hermite, "LaguerreL": sp.laguerre, "ChebyshevT": sp.chebyshevt, "ChebyshevU": sp.chebyshevu,
    "BesselJ": sp.besselj, "BesselY": sp.bessely, "BesselI": sp.besseli, "BesselK": sp.besselk,
    "Psi": lambda *a: sp.polygamma(0, a[0]) if len(a) == 1 else sp.polygamma(a[0], a[1]),
    "Heaviside": sp.Heaviside, "csgn": sp.sign, "Ssi": sp.Si,
}.items():
    _fn(_n, _f)


@core("arctan")
def arctan(ctx, y, x=None):
    if x is not None:
        return sp.atan2(y, x)
    return sp.atan(y)


@core("arccot")
def arccot(ctx, x):
    if isinstance(x, sp.Basic) and x.is_number:
        return sp.pi / 2 - sp.atan(x)
    return sp.acot(x)


@core("signum")
def signum(ctx, x):
    return sp.sign(x)


@core("sign")
def sign(ctx, x):
    return sp.sign(x)


@core("Dirac")
def dirac(ctx, *a):
    if len(a) == 2:
        return sp.DiracDelta(a[1], a[0])
    return sp.DiracDelta(a[0])


@core("GAMMA", "Gamma")
def gamma(ctx, a, x=None):
    if x is not None:
        return sp.uppergamma(a, x)
    return sp.gamma(a)


@core("LegendreP")
def legendre(ctx, n, *a):
    if len(a) == 1:
        return sp.legendre(n, a[0])
    return sp.assoc_legendre(n, a[0], a[1])


@core("piecewise")
def piecewise(ctx, *a):
    pairs = []
    i = 0
    while i + 1 < len(a):
        c, v = a[i], a[i + 1]
        if c is True:
            c = sp.true
        else:
            t = truth(ctx, c)
            if t is True:
                c = sp.true
            elif t is False:
                c = sp.false
        pairs.append((v, c))
        i += 2
    if i < len(a):
        pairs.append((a[i], sp.true))
    return sp.Piecewise(*pairs)


@core("rand")
def rand(ctx, *a):
    if not a:
        return sp.Integer(random.randrange(10 ** 12))
    r = a[0]
    if isinstance(r, Range) and (isinstance(r.lo, sp.Float) or isinstance(r.hi, sp.Float)):
        lo, hi = float(r.lo), float(r.hi)
        return PyFn(lambda c, *_: sp.Float(random.uniform(lo, hi)))
    if isinstance(r, Range):
        lo, hi = pyint(r.lo), pyint(r.hi)
        return PyFn(lambda c, *_: sp.Integer(random.randint(lo, hi)))
    n = pyint(r)
    return PyFn(lambda c, *_: sp.Integer(random.randrange(n)))


@core("time")
def time_(ctx, *a):
    return sp.Float(_time.process_time(), 10)


@core("NULL")
def null(ctx, *a):
    return Seq()


@core("randomize", "kernelopts", "interface", "forget", "gc", "libname", "unwith", "showtime", "infolevel")
def noop(ctx, *a):
    return Seq()


@core("assume")
def assume(ctx, *args):
    return _assume(ctx, args, True)


@core("additionally")
def additionally(ctx, *args):
    return _assume(ctx, args, False)


def _assume(ctx, args, replace):
    specs = []
    for a in args:
        if isinstance(a, (list, tuple)):
            specs.extend(a)
        else:
            specs.append(a)
    if len(specs) == 2 and isinstance(specs[0], sp.Symbol) and isinstance(specs[1], sp.Symbol):
        specs = [TypeDecl(specs[0], specs[1])]
    try:
        ctx.add_assumptions(specs, replace=replace)
    except TypeError:
        ctx.add_assumptions(specs)
    return Seq()


@core("about")
def about(ctx, x):
    if isinstance(x, sp.Symbol):
        kw = {k: v for k, v in x.assumptions0.items() if v and k in
              ("real", "integer", "positive", "negative", "nonnegative", "nonpositive", "rational", "nonzero")}
        ctx.out(f"{x.name}:\n   {'Properties: ' + ', '.join(kw) if kw else 'nothing known about this object'}\n")
    return Seq()


def arrow_from_expr(names, d):
    """Pijlfunctie (names) -> d als MProc (py-implementatie via substitutie)."""
    syms = [sp.Symbol(n) for n in names]
    p = ", ".join(names)
    pt = names[0] if len(names) == 1 else f"({p})"
    return MProc(params=[(n, None, None) for n in names], arrow=True, src=f"{pt} -> {T(d)}",
                 py=lambda c, *a, _d=d, _s=syms: subs_value(_d, list(zip(_s, a))))


def _op_names(f):
    if isinstance(f, MProc):
        return [p[0] for p in f.params]
    return ["x"]


@core("D")
def D(ctx, f, *rest):
    idx = getattr(ctx, "_index_ctx", None) or []
    orders = [pyint(i) - 1 for i in idx]
    if isinstance(f, DOp):
        return DOp(f.name, f.order + 1)
    if isinstance(f, (MProc, Composition, Repeat)):
        names = _op_names(f)
        syms = [sp.Symbol(n) for n in names]
        d = ctx.call(f, *syms)
        for o in (orders or [0]):
            if not 0 <= o < len(syms):
                raise MapleError("invalid input: D[i] index out of range")
            d = sp.diff(d, syms[o])
        return arrow_from_expr(names, d)
    if isinstance(f, sp.Symbol):
        fn = BUILTINS.get(f.name)
        x = sp.Symbol("x")
        if fn is not None and f.name not in ("y", "f", "g", "u", "v", "w") and f.name in CORE or f.name in (
                "sin", "cos", "tan", "exp", "ln", "sqrt", "arctan", "arcsin", "arccos", "sinh", "cosh", "tanh", "erf"):
            try:
                d = BUILTINS[f.name](ctx, x)
                for _ in (orders or [0]):
                    d = sp.diff(d, x)
                return arrow_from_expr(["x"], d)
            except Exception:
                pass
        return DOp(f.name)
    if isinstance(f, sp.MatrixBase):
        return f.applyfunc(lambda e: D(ctx, e))
    if isinstance(f, sp.Basic):
        # D op een expressie: afgeleide naar de (enige) vrije veranderlijke; D[i] kiest de i-de (alfabetisch)
        fs = sorted(f.free_symbols, key=lambda s: s.name)
        if not fs:
            return sp.Integer(0)
        if not orders and len(fs) > 1:
            raise MapleError("invalid input: D of an expression with several variables needs an index D[i]")
        d = f
        for o in (orders or [0]):
            if not 0 <= o < len(fs):
                raise MapleError("invalid input: D[i] index out of range")
            d = sp.diff(d, fs[o])
        return d
    raise MapleError("invalid input to D")


# ------------------------------------------------------------------ tabellen
@core("table")
def table(ctx, init=None):
    t = Table()
    if init is not None:
        if isinstance(init, (list, tuple)):
            if init and all(isinstance(x, sp.Equality) or type(x).__name__ == "Equality" for x in init):
                for e in init:
                    t[e.lhs] = e.rhs
            else:
                for i, x in enumerate(init):
                    t[sp.Integer(i + 1)] = x
    return t


@core("indices")
def indices(ctx, t, *a):
    return Seq([MList(list(k) if isinstance(k, Seq) else [k]) for k in t.keys()])


@core("entries")
def entries(ctx, t, *a):
    return Seq([MList([v]) for v in t.values()])


# ------------------------------------------------------------------ strings en uitvoer
def _text(v):
    if isinstance(v, Str):
        return str(v)
    if isinstance(v, str):
        return str(v)
    return T(v)


@core("cat")
def cat(ctx, *a):
    """Maple: het resultaat heeft het type van het eerste argument (string -> string, anders naam)."""
    s = "".join(_text(x) for x in a)
    if a and isinstance(a[0], Str):
        return Str(s)
    if not a:
        return Str("")
    return sp.Symbol(s)


@core("length")
def length(ctx, s):
    return sp.Integer(len(_text(s)))


@core("substring")
def substring(ctx, s, r):
    t = _text(s)
    if isinstance(r, Range):
        return Str(t[pyint(r.lo) - 1:pyint(r.hi)])
    return Str(t[pyint(r) - 1])


@core("print")
def print_(ctx, *a):
    ctx.out(", ".join(T(x) for x in a) + "\n")
    return Seq()


@core("lprint")
def lprint(ctx, *a):
    ctx.out(" ".join(_text(x) if isinstance(x, Str) else T(x).replace("\n", " ") for x in a) + "\n")
    return Seq()


_FMT = re.compile(r"%([-+ 0#]*)(\d+|\*)?(?:\.(\d+|\*))?([a-zA-Z%])")


def _format(ctx, fmt, args):
    fmt = _text(fmt)
    it = iter(args)

    def nxt():
        try:
            return next(it)
        except StopIteration:
            raise MapleError("printf: too few arguments for format") from None

    def rep(m):
        flags, width, prec, conv = m.groups()
        if conv == "%":
            return "%"
        if width == "*":
            width = str(pyint(nxt()))
        if prec == "*":
            prec = str(pyint(nxt()))
        spec = "%" + (flags or "") + (width or "") + ("." + prec if prec is not None else "")
        v = nxt()
        if conv in "di":
            if not isinstance(v, sp.Integer):
                if isinstance(v, sp.Basic) and v.is_number and v.is_real:
                    raise MapleError(f"integer expected for d format, but received {T(v)}")
                raise MapleError(f"integer expected for d format, but received {T(v)}")
            return (spec + "d") % int(v)
        if conv in "xXo":
            return (spec + conv) % pyint(v)
        if conv in "feEgG":
            if isinstance(v, sp.Basic) and v.is_number:
                x = complex(sp.N(v, 17))
                if abs(x.imag) > 0:
                    raise MapleError(f"floating-point expected for {conv} format, but received {T(v)}")
                return (spec + conv) % x.real
            raise MapleError(f"floating-point expected for {conv} format, but received {T(v)}")
        if conv in "aAqQ":
            return (spec + "s") % T(v)
        if conv == "s":
            return (spec + "s") % _text(v)
        if conv == "c":
            return _text(v)[:1]
        raise MapleError(f"invalid format specifier %{conv}")
    return _FMT.sub(rep, fmt)


@core("printf")
def printf(ctx, fmt, *a):
    ctx.out(_format(ctx, fmt, a))
    return Seq()


@core("fprintf")
def fprintf(ctx, fd, fmt, *a):
    ctx.out(_format(ctx, fmt, a))
    return Seq()


@core("sprintf", "nprintf")
def sprintf(ctx, fmt, *a):
    return Str(_format(ctx, fmt, a))


# ------------------------------------------------------------------ algebra-fallbacks
@core("expand")
def expand(ctx, e, *a):
    if isinstance(e, sp.Basic):
        return sp.expand(e)
    if isinstance(e, sp.MatrixBase):
        return e.applyfunc(sp.expand)
    return e


@core("simplify")
def simplify(ctx, e, *a):
    if isinstance(e, sp.MatrixBase):
        return e.applyfunc(sp.simplify)
    return sp.simplify(e) if isinstance(e, sp.Basic) else e


@core("factor")
def factor(ctx, e, *a):
    return sp.factor(e)


@core("normal")
def normal(ctx, e, *a):
    return sp.cancel(e)


@core("numer")
def numer(ctx, e):
    return sp.fraction(sp.together(e))[0]


@core("denom")
def denom(ctx, e):
    return sp.fraction(sp.together(e))[1]


@core("collect")
def collect(ctx, e, x, *a):
    return sp.collect(e, x)


@core("degree")
def degree(ctx, e, x=None):
    return sp.degree(e, x) if x is not None else sp.degree(e)


@core("coeff")
def coeff(ctx, e, x, n=1):
    return sp.expand(e).coeff(x, n)


# ------------------------------------------------------------------ convert
_CORE_TARGETS = {"list", "set", "listlist", "float", "numeric", "rational", "fraction", "string", "name", "symbol",
                 "degrees", "radians", "exp", "sin", "cos", "ln", "parfrac", "polynom", "binary", "octal", "hex",
                 "base", "decimal", "Matrix", "Vector", "Vector[column]", "Vector[row]", "horner", "radical", "tan"}


def _convert_core(ctx, x, t, rest):
    name = t.name if isinstance(t, sp.Symbol) else (str(t.base) + "[" + str(t.indices[0]) + "]" if isinstance(t, sp.Indexed) else str(t))
    if name in ("list",):
        if isinstance(x, sp.MatrixBase):
            if x.rows == 1 or x.cols == 1:
                return MList(list(x))
            return MList([MList([x[i, j] for j in range(x.cols)]) for i in range(x.rows)])
        if isinstance(x, (list, tuple)):
            return MList(x)
        if isinstance(x, sp.Basic) and x.args:
            return MList(x.args)
        return MList([x])
    if name == "set":
        return mkset(flat(x) if not isinstance(x, sp.Basic) or isinstance(x, sp.MatrixBase) else (list(x.args) if x.args else [x]))
    if name == "listlist":
        if isinstance(x, sp.MatrixBase):
            return MList([MList([x[i, j] for j in range(x.cols)]) for i in range(x.rows)])
        return MList(x)
    if name in ("float", "numeric"):
        return _evalf(x, ctx.digits)
    if name in ("rational", "fraction"):
        d = pyint(rest[0]) if rest and isinstance(rest[0], sp.Integer) else None
        return sp.nsimplify(x, rational=True) if d is None else sp.nsimplify(x, rational=True, tolerance=sp.Rational(1, 10 ** d))
    if name == "string":
        return Str(_text(x))
    if name in ("name", "symbol"):
        return sp.Symbol(_text(x))
    if name == "degrees":
        return x * 180 / sp.pi
    if name == "radians":
        return x * sp.pi / 180
    if name == "exp":
        return sp.expand(x.rewrite(sp.exp)) if isinstance(x, sp.Basic) else x
    if name in ("sin", "cos", "tan"):
        return x.rewrite(getattr(sp, name))
    if name == "ln":
        return x.rewrite(sp.log)
    if name == "parfrac":
        v = rest[0] if rest and isinstance(rest[0], sp.Symbol) else None
        cplx = any(isinstance(r, sp.Symbol) and r.name == "complex" for r in rest)
        kw = {"extension": sp.I} if cplx else {}
        return sp.apart(x, v, **kw) if v is not None else sp.apart(x, **kw)
    if name == "polynom":
        return x.removeO() if hasattr(x, "removeO") else x
    if name in ("binary", "octal", "hex"):
        base = {"binary": 2, "octal": 8, "hex": 16}[name]
        n = pyint(x)
        digs = "0123456789ABCDEF"
        s = ""
        k = abs(n)
        while k:
            s = digs[k % base] + s
            k //= base
        return sp.Integer(int(s or "0")) if name != "hex" else sp.Symbol(("-" if n < 0 else "") + (s or "0"))
    if name == "base":
        n, b = pyint(x), pyint(rest[0])
        out = []
        k = abs(n)
        while k:
            out.append(sp.Integer(k % b))
            k //= b
        return MList(out or [sp.Integer(0)])
    if name == "decimal":
        return _evalf(x, ctx.digits)
    if name in ("Matrix", "Vector", "Vector[column]", "Vector[row]"):
        fn = BUILTINS.get(name if name != "Vector" else "Vector")
        if fn is None:
            raise MapleError("LinearAlgebra not available")
        return fn(ctx, x)
    if name == "horner":
        return sp.horner(x)
    if name == "radical":
        return x
    raise MapleError(f"invalid input: unknown conversion target {name}")


def _convert_wrapper(ctx, x, t, *rest):
    name = t.name if isinstance(t, sp.Symbol) else None
    if isinstance(t, sp.Indexed):
        name = str(t.base) + "[" + str(t.indices[0]) + "]"
    prev = _convert_wrapper.prev
    if name in _CORE_TARGETS and not (prev is not None and name in ("Matrix", "Vector") and False):
        # eigen implementatie eerst voor lijst/set/float/...; calc-versie voor de rest
        if name in ("Matrix", "Vector", "Vector[column]", "Vector[row]") and prev is not None:
            return prev(ctx, x, t, *rest)
        return _convert_core(ctx, x, t, rest)
    if prev is not None:
        return prev(ctx, x, t, *rest)
    return _convert_core(ctx, x, t, rest)


_convert_wrapper.prev = None


# ------------------------------------------------------------------ operatoren als functies: `+`(a,b), `if`(...)
def _binop_fn(op):
    def f(ctx, *a):
        if op in ("+", "*") and not a:
            return sp.Integer(0 if op == "+" else 1)
        if op == "-" and len(a) == 1:
            return -a[0]
        if len(a) == 1 and op in ("+", "*"):
            return a[0]
        acc = a[0]
        for x in a[1:]:
            acc = ctx.binop(op, acc, x)
        return acc
    return f


for _op in ("+", "*", "-", "/", "^", "=", "<>", "<", "<=", ">", ">=", "union", "intersect", "minus", ".", "@", "mod",
            "subset", "in"):
    CORE[_op] = _binop_fn(_op)


@core("and")
def _and_fn(ctx, *a):
    return ctx.ev(("bin", "and", ("_v", a[0]), ("_v", a[1]))) if len(a) == 2 else B(all(truth(ctx, x) for x in a))


@core("or")
def _or_fn(ctx, *a):
    return ctx.ev(("bin", "or", ("_v", a[0]), ("_v", a[1]))) if len(a) == 2 else B(any(truth(ctx, x) for x in a))


@core("not")
def _not_fn(ctx, x):
    t = truth(ctx, x)
    return sp.Not(x) if t is None else B(not t)


@core("[]")
def _list_fn(ctx, *a):
    return MList(a)


@core("{}")
def _set_fn(ctx, *a):
    return mkset(a)


@core("..")
def _range_fn(ctx, a, b):
    return RangeB(a, b)


@core("!")
def _fact_fn(ctx, a):
    return sp.factorial(a)


# ------------------------------------------------------------------ subsop
@core("subsop")
def subsop(ctx, *a):
    if len(a) < 2:
        raise MapleError("invalid input: subsop expects at least two arguments")
    e = a[-1]
    for spec in a[:-1]:
        if not (isinstance(spec, sp.Equality) or type(spec).__name__ == "Equality"):
            raise MapleError(f"invalid input: subsop expects equations i = value, but received {T(spec)}")
        idx, val = spec.args[0], spec.args[1]
        path = list(idx) if isinstance(idx, (list, tuple)) else [idx]
        e = _subsop1(e, [pyint(i) for i in path], val)
    return e


def _subsop1(e, path, val):
    i = path[0]
    if len(path) > 1:
        sub = op(None, sp.Integer(i), e)
        val = _subsop1(sub, path[1:], val)
    if isinstance(e, (MList, MSet)):
        items = list(e)
        j = i + len(items) + 1 if i < 0 else i
        if not 1 <= j <= len(items):
            raise MapleError("improper op or subscript selector")
        new = items[:j - 1] + (list(val) if isinstance(val, Seq) else [val]) + items[j:]
        return MList(new) if isinstance(e, MList) else mkset(new)
    if isinstance(e, sp.Basic):
        if i == 0:
            if isinstance(val, sp.Symbol):
                fn = {"+": sp.Add, "*": sp.Mul, "^": sp.Pow}.get(val.name) or sp.Function(val.name)
                return fn(*e.args)
            return val(*e.args) if callable(val) else e
        ops = _operands(e)
        j = i + len(ops) + 1 if i < 0 else i
        if not 1 <= j <= len(ops):
            raise MapleError("improper op or subscript selector")
        ops[j - 1] = val
        if isinstance(e, sp.Rational) and not isinstance(e, sp.Integer):
            return sp.Rational(ops[0], ops[1]) if all(isinstance(x, sp.Integer) for x in ops) else ops[0] / ops[1]
        if isinstance(e, (sp.Equality,)) or type(e).__name__ in ("Equality", "Unequality"):
            return type(e)(*ops, evaluate=False) if isinstance(e, sp.Basic) else e
        if isinstance(e, sp.core.relational.Relational):
            return type(e)(*ops)
        try:
            return e.func(*ops)
        except Exception as ex:
            raise MapleError(f"subsop: cannot substitute: {ex}")
    raise MapleError("invalid input: subsop")


# ------------------------------------------------------------------ rtable-grenzen
@core("upperbound")
def _ubound(ctx, A, d=None):
    return _bounds(ctx, A, d, True)


@core("lowerbound")
def _lbound(ctx, A, d=None):
    return _bounds(ctx, A, d, False)


def _bounds(ctx, A, d, upper):
    if isinstance(A, sp.MatrixBase):
        if A.cols == 1 or A.rows == 1:
            dims = [A.rows * A.cols]
        else:
            dims = [A.rows, A.cols]
    elif isinstance(A, (MList, Str)):
        dims = [len(A)]
    else:
        raise MapleError(f"invalid input: expected an rtable, but received {T(A)}")
    vals = [sp.Integer(n if upper else 1) for n in dims]
    if d is not None:
        return vals[pyint(d) - 1]
    return Seq(vals) if len(vals) > 1 else vals[0]


# ------------------------------------------------------------------ StringTools
def _s(x):
    if isinstance(x, Str) or isinstance(x, str):
        return str(x)
    if isinstance(x, sp.Symbol):
        return x.name
    return T(x)


def _st(names):
    return core(*names, pkg="StringTools")


@_st(["Length"])
def st_length(ctx, s):
    return sp.Integer(len(_s(s)))


@_st(["SubString"])
def st_substring(ctx, s, r):
    t = _s(s)
    n = len(t)
    if isinstance(r, Range):
        lo = 1 if r.lo is None else pyint(r.lo)
        hi = n if r.hi is None else pyint(r.hi)
    else:
        lo = hi = pyint(r)
    lo = lo + n + 1 if lo < 0 else lo
    hi = hi + n + 1 if hi < 0 else hi
    return Str(t[max(lo, 1) - 1:max(hi, 0)])


@_st(["Split"])
def st_split(ctx, s, sep=None):
    t = _s(s)
    if sep is None:
        return MList([Str(x) for x in t.split()])
    seps = _s(sep)
    out, cur = [], ""
    for ch in t:
        if ch in seps:
            out.append(Str(cur))
            cur = ""
        else:
            cur += ch
    out.append(Str(cur))
    return MList(out)


@_st(["Join"])
def st_join(ctx, L, sep=Str(" ")):
    if all(isinstance(x, str) for x in L) and isinstance(sep, str):
        return Str(_s(sep).join(_s(x) for x in L))
    out = []                                        # ListTools:-Join(L, x): x tussen de elementen
    for i, x in enumerate(L):
        if i:
            out.append(sep)
        out.append(x)
    return MList(out)


@_st(["Search", "SearchText"])
def st_search(ctx, pat, s, *rest):
    if isinstance(s, (MList, sp.MatrixBase)):            # ListTools:-Search(x, L)
        for i, x in enumerate(list(s)):
            if same(x, pat):
                return sp.Integer(i + 1)
        return sp.Integer(0)
    return sp.Integer(_s(s).find(_s(pat)) + 1)


@_st(["SearchAll"])
def st_searchall(ctx, pat, s):
    if isinstance(s, (MList, sp.MatrixBase)):
        return Seq([sp.Integer(i + 1) for i, x in enumerate(list(s)) if same(x, pat)])
    t, p_, out, i = _s(s), _s(pat), [], 0
    while p_:
        j = t.find(p_, i)
        if j < 0:
            break
        out.append(sp.Integer(j + 1))
        i = j + 1
    return Seq(out)


@_st(["UpperCase"])
def st_upper(ctx, s, *r):
    return Str(_s(s).upper())


@_st(["LowerCase"])
def st_lower(ctx, s, *r):
    return Str(_s(s).lower())


@_st(["Reverse"])
def st_reverse(ctx, s):
    if isinstance(s, MList):                              # ListTools:-Reverse
        return MList(list(s)[::-1])
    return Str(_s(s)[::-1])


@_st(["Substitute"])
def st_subst(ctx, s, a, b):
    return Str(_s(s).replace(_s(a), _s(b), 1))


@_st(["SubstituteAll"])
def st_substall(ctx, s, a, b):
    return Str(_s(s).replace(_s(a), _s(b)))


@_st(["IsPrefix"])
def st_isprefix(ctx, a, s):
    return B(_s(s).startswith(_s(a)))


@_st(["IsSuffix"])
def st_issuffix(ctx, a, s):
    return B(_s(s).endswith(_s(a)))


@_st(["Trim"])
def st_trim(ctx, s):
    return Str(_s(s).strip())


@_st(["TrimLeft"])
def st_triml(ctx, s):
    return Str(_s(s).lstrip())


@_st(["TrimRight"])
def st_trimr(ctx, s):
    return Str(_s(s).rstrip())


@_st(["Explode"])
def st_explode(ctx, s):
    return MList([Str(c) for c in _s(s)])


@_st(["Implode"])
def st_implode(ctx, L):
    return Str("".join(_s(x) for x in L))


@_st(["Repeat"])
def st_repeat(ctx, s, n):
    return Str(_s(s) * pyint(n))


@_st(["Ord"])
def st_ord(ctx, s):
    return sp.Integer(ord(_s(s)[0]))


@_st(["Char"])
def st_char(ctx, n):
    return Str(chr(pyint(n)))


@_st(["Has"])
def st_has(ctx, s, p_):
    return B(_s(p_) in _s(s))


@_st(["CountCharacterOccurrences"])
def st_count(ctx, s, c):
    return sp.Integer(_s(s).count(_s(c)))


@_st(["IsDigit"])
def st_isdigit(ctx, s):
    return B(_s(s).isdigit() and len(_s(s)) > 0)


@_st(["IsAlpha"])
def st_isalpha(ctx, s):
    return B(_s(s).isalpha())


@_st(["Capitalize"])
def st_cap(ctx, s):
    t = _s(s)
    return Str(t[:1].upper() + t[1:])


@_st(["FormatMessage"])
def st_formatmessage(ctx, *a):
    a = list(a[0]) if len(a) == 1 and isinstance(a[0], Seq) else list(a)
    if a and isinstance(a[0], (Str, str)):
        return Str(ctx.format_msg(a))
    return Str(" ".join(_s(x) for x in a))


@_st(["Fill"])
def st_fill(ctx, c, n):
    return Str(_s(c) * pyint(n))


# ------------------------------------------------------------------ ListTools
def _lt(names):
    return core(*names, pkg="ListTools")


def _flatten(L, once=False):
    out = []
    for x in L:
        if isinstance(x, MList):
            out.extend(list(x) if once else _flatten(x))
        else:
            out.append(x)
    return out


@_lt(["Flatten"])
def lt_flatten(ctx, L, *depth):
    return MList(_flatten(L))


@_lt(["FlattenOnce"])
def lt_flatten1(ctx, L):
    return MList(_flatten(L, once=True))


@_lt(["MakeUnique"])
def lt_unique(ctx, L, *r):
    out = []
    for x in L:
        if not any(same(x, y) for y in out):
            out.append(x)
    return MList(out)


@_lt(["Rotate"])
def lt_rotate(ctx, L, n=sp.Integer(1)):
    k = pyint(n) % len(L) if len(L) else 0
    return MList(list(L)[k:] + list(L)[:k])


@_lt(["PartialSums"])
def lt_psums(ctx, L):
    out, acc = [], sp.Integer(0)
    for x in L:
        acc = acc + x
        out.append(acc)
    return MList(out)


@_lt(["Enumerate"])
def lt_enum(ctx, L):
    return MList([MList([sp.Integer(i + 1), x]) for i, x in enumerate(L)])


@_lt(["Interleave"])
def lt_interleave(ctx, *Ls):
    out = []
    for i in range(max(len(L) for L in Ls)):
        for L in Ls:
            if i < len(L):
                out.append(L[i])
    return MList(out)


@_lt(["Occurrences"])
def lt_occ(ctx, x, L):
    return sp.Integer(sum(1 for y in L if same(x, y)))


@_lt(["SelectFirst"])
def lt_selfirst(ctx, *a):
    if isinstance(a[0], sp.Integer) and len(a) >= 3:
        n, f, L = pyint(a[0]), a[1], a[2]
    else:
        n, f, L = None, a[0], a[1]
    out = []
    for x in L:
        if truth(ctx, ctx.call(f, x)):
            out.append(x)
            if n is None or len(out) >= n:
                break
    if n is None:
        return out[0] if out else Seq()
    return MList(out)


@_lt(["BinarySearch"])
def lt_bsearch(ctx, L, x, *r):
    for i, y in enumerate(L):
        if same(x, y):
            return sp.Integer(i + 1)
    return sp.Integer(0)


@_lt(["Transpose"])
def lt_transpose(ctx, L):
    if isinstance(L, sp.MatrixBase):
        return L.T
    return MList([MList(list(r)) for r in zip(*L)])


@_lt(["LengthSplit"])
def lt_lsplit(ctx, L, n):
    k = pyint(n)
    return Seq([MList(list(L)[i:i + k]) for i in range(0, len(L), k)])


@_lt(["FindRepetitions"])
def lt_reps(ctx, L, *r):
    out = []
    for x in L:
        if sum(1 for y in L if same(x, y)) > 1 and not any(same(x, y) for y in out):
            out.append(x)
    return MList(out)


@_lt(["Sorted"])
def lt_sorted(ctx, L, *r):
    try:
        return B(all(bool(a <= b) for a, b in zip(list(L), list(L)[1:])))
    except TypeError:
        return sp.Symbol("FAIL")


@_lt(["Categorize"])
def lt_categorize(ctx, f, L):
    groups = []
    for x in L:
        for g in groups:
            if truth(ctx, ctx.call(f, x, g[0])):
                g.append(x)
                break
        else:
            groups.append([x])
    return Seq([MList(g) for g in groups])


@_lt(["Classify"])
def lt_classify(ctx, f, L):
    t = Table()
    for x in L:
        k = ctx.call(f, x)
        t.setdefault(k, MSet())
        if not any(same(x, y) for y in t[k]):
            t[k].append(x)
    return t


@_lt(["DotProduct"])
def lt_dot(ctx, a, b):
    return sum((x * y for x, y in zip(a, b)), sp.Integer(0))


@_lt(["Group"])
def lt_group(ctx, L, f=None):
    out = []
    for x in L:
        if out and (truth(ctx, ctx.call(f, out[-1][-1], x)) if f is not None else same(out[-1][-1], x)):
            out[-1].append(x)
        else:
            out.append([x])
    return MList([MList(g) for g in out])


PACKAGES_EXTRA_ALIASES = {"ListTools": ["Reverse", "Search", "SearchAll", "Join"]}
for _pk, _ns in PACKAGES_EXTRA_ALIASES.items():
    for _n in _ns:
        if _n not in _PKG.setdefault(_pk, []):
            _PKG[_pk].append(_n)
