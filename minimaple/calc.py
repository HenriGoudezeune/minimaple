"""Calculus, solve, dsolve, pdsolve, convert en integraaltransformaties voor mini-Maple (alleen SymPy-API)."""
import re
import numpy as np
import sympy as sp
from sympy.core.function import AppliedUndef
from .values import maple, MList, MSet, Seq, Range, Str, split_opts

oo = sp.oo
UNDEF = sp.Symbol('undefined')


class CalcError(ValueError):
    pass


# ------------------------------------------------------------------ hulpfuncties
def _digits(ctx):
    d = getattr(ctx, 'digits', None)
    return int(d) if d else 10


def _name(a):
    return str(a).strip("'\"`")


def _lr(a):
    """(lhs, rhs) van een Eq of Eq-achtig object (lhs/rhs-attributen) of tuple, anders None."""
    if isinstance(a, sp.Equality):
        return a.lhs, a.rhs
    if hasattr(a, 'lhs') and hasattr(a, 'rhs') and not isinstance(a, sp.Basic):
        return a.lhs, a.rhs
    if isinstance(a, tuple) and not isinstance(a, Seq) and len(a) == 2 and isinstance(a[1], Range):
        return a
    return None


def _as_range(r):
    """Range / (lo,hi)-achtig -> (lo, hi) of None."""
    if isinstance(r, Range):
        return r.lo, r.hi
    if isinstance(r, (sp.Tuple, tuple)) and not isinstance(r, Seq) and len(r) == 2:
        return r[0], r[1]
    if hasattr(r, 'lo') and hasattr(r, 'hi'):
        return r.lo, r.hi
    return None


def _var_range(a):
    """x=a..b -> (x, a, b); x=a -> (x, a, None); x -> (x, None, None)."""
    p = _lr(a)
    if p is None:
        return a, None, None
    v, r = p
    rg = _as_range(r)
    if rg:
        return v, rg[0], rg[1]
    return v, r, None


def _mapv(fn, e):
    if isinstance(e, MList):
        return MList(_mapv(fn, a) for a in e)
    if isinstance(e, MSet):
        return MSet(_mapv(fn, a) for a in e)
    if isinstance(e, Seq):
        return Seq(_mapv(fn, a) for a in e)
    if isinstance(e, (sp.MatrixBase,)):
        return e.applyfunc(lambda a: _mapv(fn, a))
    if isinstance(e, sp.Equality):
        return sp.Eq(_mapv(fn, e.lhs), _mapv(fn, e.rhs), evaluate=False)
    if isinstance(e, (int, float)):
        e = sp.sympify(e)
    return fn(e)


def _seq(vals):
    vals = list(vals)
    if len(vals) == 1:
        return vals[0]
    return Seq(vals)


def _rename_consts(e, prefix='C', new='_C'):
    pat = re.compile(r'^' + prefix + r'(\d+)$')
    d = {s: sp.Symbol(new + pat.match(s.name).group(1)) for s in e.free_symbols
         if isinstance(s, sp.Symbol) and pat.match(s.name)}
    return e.xreplace(d) if d else e


def _expr(e):
    """Eq -> lhs-rhs, rest ongewijzigd."""
    if isinstance(e, sp.Equality):
        return e.lhs - e.rhs
    return e


def _rhs_trig_infinite(e):
    return e


# ------------------------------------------------------------------ differentiëren, integreren
def _diff_one(f, vars_):
    if not vars_:
        return f
    return sp.diff(f, *vars_)


@maple('diff')
def diff(ctx, f, *vars_):
    vs = []
    for v in vars_:
        if isinstance(v, (MList, MSet, Seq)):
            vs.extend(v)
        else:
            vs.append(v)
    return _mapv(lambda e: _diff_one(e, vs), f)


@maple('Diff')
def Diff(ctx, f, *vars_):
    return sp.Derivative(f, *vars_)


def _risky_integrand(f):
    """Trig-machten met gebroken exponent laten sympy.integrate vaak eindeloos draaien."""
    for p in f.atoms(sp.Pow):
        if p.exp.is_Rational and not p.exp.is_Integer and p.base.has(sp.sin, sp.cos, sp.tan, sp.cot):
            return True
    return False


def _limited(fn, timeout=6.0):
    """Voer fn() uit in een gevorkt proces met tijdslimiet; None bij timeout of fout."""
    import multiprocessing as mp
    import pickle
    try:
        mpc = mp.get_context('fork')
    except ValueError:
        return fn()
    rcv, snd = mpc.Pipe(duplex=False)

    def work():
        try:
            snd.send_bytes(pickle.dumps(fn()))
        except BaseException:
            snd.send_bytes(pickle.dumps(None))
    pr = mpc.Process(target=work, daemon=True)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pr.start()
    out = None
    if rcv.poll(timeout):
        try:
            out = pickle.loads(rcv.recv_bytes())
        except Exception:
            out = None
    pr.kill()
    pr.join(1)
    return out


def _heav_piece(f):
    """Heaviside(g) -> Piecewise zodat sympy.integrate niet naar meijerg grijpt."""
    if not f.has(sp.Heaviside):
        return f
    return f.replace(lambda z: isinstance(z, sp.Heaviside),
                     lambda z: sp.Piecewise((1, z.args[0] > 0), (0, True)))


def _int_one(f, specs):
    f = _heav_piece(f) if any(a is not None for _, a, _ in specs) else f
    for v, a, b in specs:
        if a is None:
            f = sp.integrate(f, v)
        elif _risky_integrand(f):
            r = _limited(lambda: sp.integrate(f, (v, a, b), conds='none'))
            f = sp.Integral(f, (v, a, b)) if r is None else r
        else:
            f = sp.integrate(f, (v, a, b), conds='none')
        if isinstance(f, sp.Piecewise) and len(f.args) >= 1 and f.args[-1][1] == True:
            pass
    return f


@maple('int', 'integrate')
def int_(ctx, f, *rest):
    pos, _ = split_opts(rest)
    specs = []
    for a in pos:
        if isinstance(a, sp.Symbol) and a.name in ('CauchyPrincipalValue', 'continuous', 'numeric'):
            continue
        if isinstance(a, (MList, MSet)):
            specs.extend(_var_range(b) for b in a)
        else:
            v, lo, hi = _var_range(a)
            if lo is not None and hi is None:
                raise CalcError("int: bereik a..b verwacht")
            specs.append((v, lo, hi))
    if not specs:
        raise CalcError("int: integratievariabele ontbreekt")
    if len(specs) > 1:
        # int(f, x=a..b, y=c..d): binnenste eerst (eerste argument)
        pass
    return _mapv(lambda e: _int_one(e, specs), f)


@maple('Int')
def Int(ctx, f, *rest):
    specs = []
    for a in rest:
        v, lo, hi = _var_range(a)
        specs.append((v,) if lo is None else (v, lo, hi))
    return sp.Integral(f, *specs)


@maple('value')
def value(ctx, e):
    return _mapv(lambda a: a.doit() if hasattr(a, 'doit') else a, e)


# ------------------------------------------------------------------ limieten
def _limit_core(f, x, a, direction=None):
    if a in (oo, -oo) or direction in ('+', '-'):
        try:
            r = sp.limit(f, x, a, direction or ('-' if a == oo else '+'))
        except Exception:
            return sp.Limit(f, x, a)
        return r
    try:
        l = sp.limit(f, x, a, '-')
        r = sp.limit(f, x, a, '+')
    except Exception:
        return sp.Limit(f, x, a)
    if l == r:
        return l
    return UNDEF


@maple('limit')
def limit(ctx, f, pt, *rest):
    v, a, b = _var_range(pt)
    if a is None:
        raise CalcError("limit: x=a verwacht")
    d = None
    for r in rest:
        nm = _name(r)
        if nm == 'right':
            d = '+'
        elif nm == 'left':
            d = '-'
    return _mapv(lambda e: _limit_core(sp.sympify(e), v, a, d), f)


@maple('Limit')
def Limit(ctx, f, pt, *rest):
    v, a, _ = _var_range(pt)
    d = '+-'
    for r in rest:
        nm = _name(r)
        if nm == 'right':
            d = '+'
        elif nm == 'left':
            d = '-'
    return sp.Limit(f, v, a, d)


# ------------------------------------------------------------------ sommen en producten
def _sum_prod(f, spec, which, inert=False):
    v, lo, hi = _var_range(spec)
    cls = sp.Sum if which == 'sum' else sp.Product
    if lo is None:
        res = cls(f, v)
        if inert:
            return res
        raise CalcError("sum: k=a..b verwacht")
    if hi is None:
        raise CalcError("sum: k=a..b verwacht")
    res = cls(f, (v, lo, hi))
    if inert:
        return res
    try:
        out = res.doit()
    except Exception:
        return res
    if isinstance(out, sp.Piecewise):
        out = out.args[0][0]
    if isinstance(out, (sp.Sum, sp.Product)):
        return out
    if out.free_symbols and out.is_rational_function():
        out = sp.factor(out)
    return out


@maple('sum')
def sum_(ctx, f, spec, *rest):
    return _mapv(lambda e: _sum_prod(e, spec, 'sum'), f)


@maple('Sum')
def Sum(ctx, f, spec, *rest):
    return _sum_prod(f, spec, 'sum', inert=True)


@maple('product')
def product_(ctx, f, spec, *rest):
    return _mapv(lambda e: _sum_prod(e, spec, 'prod'), f)


@maple('Product')
def Product(ctx, f, spec, *rest):
    return _sum_prod(f, spec, 'prod', inert=True)


# ------------------------------------------------------------------ reeksen
def _series_args(pt, n):
    if pt is None:
        raise CalcError("series: x=a verwacht")
    v, a, _ = _var_range(pt)
    if a is None:
        a = sp.Integer(0)
    nn = 6 if n is None else int(n)
    return v, a, nn


def _is_symbol_like(v):
    return isinstance(v, sp.Symbol)


@maple('series', 'taylor')
def series(ctx, f, pt=None, n=None, *rest):
    if pt is None:
        fs = sorted(getattr(f, 'free_symbols', []), key=str)
        pt = fs[0] if fs else sp.Symbol('x')
    v, a, nn = _series_args(pt, n)

    def one(e):
        e = sp.sympify(e)
        if a in (oo, -oo):
            return sp.series(e, v, a, nn)
        return sp.series(e, v, a, nn)
    return _mapv(one, f)


@maple('mtaylor')
def mtaylor(ctx, f, vars_, n=6, *rest):
    t = sp.Symbol('_tt')
    vs = list(vars_) if isinstance(vars_, (MList, MSet, Seq, list)) else [vars_]
    sub = {v: t * v for v in vs}
    s = sp.series(f.subs(sub, simultaneous=True), t, 0, int(n)).removeO()
    return sp.expand(s.subs(t, 1))


# ------------------------------------------------------------------ expressie-manipulatie
def _opt_names(rest):
    return [_name(r) for r in rest if isinstance(r, sp.Symbol)]


@maple('simplify')
def simplify(ctx, e, *rest):
    names = _opt_names(rest)

    def one(a):
        a = sp.sympify(a)
        if 'trig' in names:
            return sp.trigsimp(a)
        if 'exp' in names:
            return sp.powsimp(a)
        if 'ln' in names or 'log' in names:
            return sp.logcombine(a, force=True)
        if 'radical' in names or 'sqrt' in names:
            return sp.radsimp(a)
        return _tidy_minus_one_powers(sp.simplify(integer_exp_fix(a)))
    return _mapv(one, e)


def integer_exp_fix(a):
    """exp(I*Pi*k) met k geheel (via assumptions) -> (-1)^k, daarna vereenvoudigen."""
    if not isinstance(a, sp.Basic) or not a.has(sp.exp):
        return a

    def fix(z):
        q = sp.expand(z.args[0] / (sp.I * sp.pi))
        if q.is_integer and not q.is_number:
            return (-1) ** q
        return z
    b = a.replace(lambda z: isinstance(z, sp.exp), fix)
    if b != a:
        b = _tidy_minus_one_powers(sp.simplify(b))
    return b


def _tidy_minus_one_powers(a):
    """(-1)^(k+1/2) -> I*(-1)^k, zoals Maple het schrijft."""
    def fix(z):
        k = z.exp
        if z.base == -1:
            c = sp.expand(k)
            half = [t for t in sp.Add.make_args(c) if t.is_Rational and not t.is_Integer]
            if len(half) == 1 and half[0] in (sp.Rational(1, 2), sp.Rational(-1, 2)):
                rest = c - half[0]
                return (sp.I if half[0] > 0 else -sp.I) * (-1) ** rest
        return z
    return a.replace(lambda z: z.is_Pow and z.base == -1, fix) if a.has(sp.Pow) else a


@maple('expand')
def expand(ctx, e, *rest):
    def one(a):
        a = sp.sympify(a)
        return sp.expand(sp.expand_trig(a), complex=False)
    return _mapv(one, e)


@maple('factor')
def factor(ctx, e, *rest):
    ext = None
    for r in rest:
        if not (isinstance(r, sp.Symbol) and r.name in ('real', 'complex')):
            ext = r
        elif r.name == 'complex':
            ext = sp.I

    def one(a):
        a = sp.sympify(a)
        if a.is_Integer and abs(a) > 1:
            f = sp.factorint(a)
            return sp.Mul(*[sp.Pow(p, k, evaluate=False) for p, k in sorted(f.items())], evaluate=False) \
                if len(f) > 1 or list(f.values())[0] > 1 else a
        if ext is not None:
            return sp.factor(a, extension=ext)
        return sp.factor(a)
    return _mapv(one, e)


@maple('normal')
def normal(ctx, e, *rest):
    return _mapv(lambda a: sp.cancel(sp.together(sp.sympify(a))), e)


@maple('combine')
def combine(ctx, e, *rest):
    names = _opt_names(rest)

    def one(a):
        a = sp.sympify(a)
        if 'trig' in names:
            return sp.trigsimp(a)
        if 'exp' in names:
            return sp.powsimp(a)
        if 'ln' in names or 'log' in names:
            return sp.logcombine(a, force=True)
        if 'power' in names:
            return sp.powsimp(a, force=True)
        a = sp.powsimp(a, force=True)
        a = sp.logcombine(a, force=True)
        return sp.trigsimp(a)
    return _mapv(one, e)


@maple('collect')
def collect(ctx, e, x, *rest):
    names = _opt_names(rest)
    xs = list(x) if isinstance(x, (MList, MSet, Seq)) else x

    def one(a):
        a = sp.expand(sp.sympify(a))
        r = sp.collect(a, xs)
        if 'factor' in names:
            r = sp.collect(a, xs, evaluate=False)
            r = sp.Add(*[k * sp.factor(v) for k, v in r.items()])
        return r
    return _mapv(one, e)


def _pow_base(a):
    if isinstance(a, sp.Pow) and a.exp.is_Integer:
        return a.base, int(a.exp)
    return a, 1


@maple('coeff')
def coeff(ctx, p, x, n=None):
    p = sp.expand(sp.sympify(p))
    if n is None:
        b, k = _pow_base(x)
        return p.coeff(b, k) if k != 1 or isinstance(x, sp.Pow) else p.coeff(x, 1)
    return p.coeff(x, int(n)) if int(n) != 0 else p.coeff(x, 0)


@maple('coeffs')
def coeffs(ctx, p, *rest):
    p = sp.expand(sp.sympify(p))
    gens = [r for r in rest if isinstance(r, sp.Symbol)]
    gens2 = []
    for g in gens:
        gens2.append(g)
    name = None
    if len(rest) >= 2 and isinstance(rest[-1], sp.Symbol) and not _is_gen(rest[-1], p, rest[:-1]):
        name = rest[-1]
        gens2 = [g for g in gens2 if g is not name]
    if isinstance(rest[0] if rest else None, (MList, MSet, Seq)):
        gens2 = list(rest[0])
    if not gens2:
        gens2 = sorted(p.free_symbols, key=str)
    if not gens2:
        return p
    P = sp.Poly(p, *gens2)
    terms = sorted(P.terms(), key=lambda t: t[0])
    cs = [c for m, c in terms if c != 0]
    if name is not None:
        try:
            ctx.env[name.name] = Seq(sp.Mul(*[g ** k for g, k in zip(gens2, m)]) for m, c in terms if c != 0)
        except Exception:
            pass
    return Seq(cs)


def _is_gen(sym, p, others):
    return sym in p.free_symbols and len(others) == 0


@maple('degree')
def degree(ctx, p, x=None, *rest):
    p = sp.sympify(p)
    if p == 0:
        return -oo
    if x is None:
        gens = sorted(p.free_symbols, key=str)
        return sp.Poly(p, *gens).total_degree() if gens else sp.Integer(0)
    if isinstance(x, (MList, MSet, Seq)):
        return sp.Poly(p, *x).total_degree()
    return sp.degree(p, x)


@maple('ldegree')
def ldegree(ctx, p, x):
    P = sp.Poly(sp.expand(p), x)
    return min(m[0] for m in P.monoms())


@maple('numer')
def numer(ctx, e):
    return _mapv(lambda a: sp.fraction(sp.together(sp.sympify(a)))[0], e)


@maple('denom')
def denom(ctx, e):
    return _mapv(lambda a: sp.fraction(sp.together(sp.sympify(a)))[1], e)


@maple('evalf')
def evalf(ctx, e, n=None, *rest):
    dg = _digits(ctx) if n is None else int(n)
    from .core_fns import _num_integral

    def one(a):
        a = sp.sympify(a)
        if a.has(sp.Integral):
            a = a.xreplace({I: _num_integral(I, dg) for I in a.atoms(sp.Integral)})
        return a.evalf(dg)
    return _mapv(one, e)


@maple('evalc')
def evalc(ctx, e):
    def one(a):
        a = sp.sympify(a)
        d = {s: sp.Symbol(s.name, real=True) for s in a.free_symbols
             if isinstance(s, sp.Symbol) and s.is_real is None}
        back = {v: k for k, v in d.items()}
        r = sp.expand_complex(a.xreplace(d))
        return sp.simplify(r.xreplace(back)) if False else r.xreplace(back)
    return _mapv(one, e)


@maple('trigsimp')
def trigsimp(ctx, e, *rest):
    return _mapv(lambda a: sp.trigsimp(sp.sympify(a)), e)


# ------------------------------------------------------------------ convert
_SINCOS = {sp.tan: lambda a: sp.sin(a) / sp.cos(a), sp.cot: lambda a: sp.cos(a) / sp.sin(a),
           sp.sec: lambda a: 1 / sp.cos(a), sp.csc: lambda a: 1 / sp.sin(a)}


def _flat_items(e):
    if isinstance(e, (MList, MSet, Seq, list, tuple)):
        return list(e)
    if isinstance(e, sp.MatrixBase):
        return list(e)
    return [e]


@maple('convert')
def convert(ctx, e, typ, *rest):
    t = _name(typ)
    if t == 'list':
        if isinstance(e, sp.MatrixBase):
            return MList(e.tolist() if min(e.shape) > 1 else list(e))
        return MList(_flat_items(e))
    if t == 'set':
        out = MSet()
        for a in _flat_items(e):
            if a not in out:
                out.append(a)
        return out
    if t in ('Matrix', 'Vector', 'Vector[column]', 'Vector[row]'):
        items = _flat_items(e)
        if items and all(isinstance(r, (list, tuple, MList)) for r in items):
            return sp.Matrix([list(r) for r in items])
        if t == 'Matrix':
            return sp.Matrix([items])
        return sp.Matrix(items)
    if t in ('float', 'double'):
        dg = _digits(ctx)
        return _mapv(lambda a: sp.sympify(a).evalf(dg), e)
    if t == 'string':
        return Str(str(e))

    def one(a):
        a = sp.sympify(a)
        if t == 'polynom':
            return a.removeO() if hasattr(a, 'removeO') else a
        if t in ('parfrac', 'fullparfrac'):
            xs = [r for r in rest if isinstance(r, sp.Symbol) and r.name not in ('complex', 'real')]
            if xs:
                x = xs[0]
            else:
                fs = sorted(a.free_symbols, key=str)
                if not fs:
                    return a
                x = fs[0]
            if any(isinstance(r, sp.Symbol) and r.name == 'complex' for r in rest):
                return sp.apart(a, x, extension=sp.I)
            return sp.apart(a, x)
        if t in ('exp', 'expln'):
            return a.rewrite(sp.exp) if t == 'exp' else a.rewrite(sp.log)
        if t == 'ln':
            return a.rewrite(sp.log)
        if t == 'trig':
            return a.rewrite(sp.cos) if a.has(sp.exp) else a
        if t == 'sincos':
            return a.replace(lambda z: z.func in _SINCOS, lambda z: _SINCOS[z.func](*z.args)).rewrite(sp.sin) \
                if a.has(sp.exp) else a.replace(lambda z: z.func in _SINCOS, lambda z: _SINCOS[z.func](*z.args))
        if t == 'rational':
            return sp.nsimplify(a, rational=True)
        if t == 'radians':
            return a * sp.pi / 180
        if t == 'degrees':
            return a * 180 / sp.pi
        if t == 'horner':
            xs = [r for r in rest if isinstance(r, sp.Symbol)]
            return sp.horner(a, *xs) if xs else sp.horner(a)
        if t in ('GAMMA', 'gamma'):
            return a.rewrite(sp.gamma)
        if t == 'factorial':
            return a.rewrite(sp.factorial)
        if t == 'binomial':
            return a.rewrite(sp.binomial)
        if t == 'sqrt':
            return a.rewrite(sp.sqrt)
        if t == 'Heaviside':
            return a.rewrite(sp.Heaviside)
        if t == 'piecewise':
            return a.rewrite(sp.Piecewise)
        if t in ('arctan', 'arctrig'):
            return a.rewrite(sp.atan)
        raise CalcError(f"convert: onbekend type {t}")
    return _mapv(one, e)


# ------------------------------------------------------------------ solve
def _is_ineq(e):
    return isinstance(e, sp.core.relational._Inequality)


def _gather(arg):
    if isinstance(arg, (MList, MSet, Seq, list, tuple)):
        return list(arg)
    return [arg]


def _to_eq(v, val):
    return sp.Eq(v, val, evaluate=False)


def _maple_root_order(sols):
    """Maple-achtige volgorde van numerieke wortels: toenemende modulus, bij gelijke modulus eerst
    positief reeel deel en positief imaginair deel (x^2-4 -> 2, -2; x^4-1 -> 1, -1, I, -I)."""
    try:
        if len(sols) < 2 or not all(isinstance(q, sp.Basic) and q.is_number for q in sols):
            return sols
        def key(q):
            v = complex(sp.N(q, 20))
            return (round(abs(v), 9), abs(v.imag) > 1e-9, -round(v.real, 9), -round(v.imag, 9))
        return sorted(sols, key=key)
    except Exception:
        return sols


@maple('solve')
def solve(ctx, eqs, *rest):
    rest = [r for r in rest if not (isinstance(r, sp.Equality) and isinstance(r.lhs, sp.Symbol)
                                    and r.lhs.name in ('explicit', 'useassumptions', 'parameters'))]
    vars_arg = rest[0] if rest else None
    eq_list = _gather(eqs)
    if not isinstance(eqs, (MList, MSet, Seq, list, tuple)) and False:
        pass
    # ongelijkheden
    if any(_is_ineq(q) or isinstance(q, (sp.And, sp.Or)) for q in eq_list):
        vs = _gather(vars_arg) if vars_arg is not None else None
        ineqs = [q for q in eq_list if _is_ineq(q)]
        if len(eq_list) == 1 and len(ineqs) == 1:
            q = ineqs[0]
            x = vs[0] if vs else sorted(q.free_symbols, key=str)[0]
            return sp.solve_univariate_inequality(q, x, relational=True)
        x = vs[0] if vs else sorted(set().union(*[q.free_symbols for q in eq_list]), key=str)[0]
        return sp.reduce_inequalities(eq_list, x)
    exprs = []
    for q in eq_list:
        if q is sp.true or q == sp.true:
            continue
        if q is sp.false:
            return Seq()
        exprs.append(_expr(q))
    set_mode = isinstance(vars_arg, (MList, MSet, Seq, list, tuple)) or \
        (vars_arg is None and (isinstance(eqs, (MList, MSet)) or
                               len(set().union(*[sp.sympify(q).free_symbols for q in exprs])) > 1
                               if exprs else False))
    if vars_arg is None:
        fs = set().union(*[sp.sympify(q).free_symbols for q in exprs]) if exprs else set()
        vs = sorted(fs, key=str)
    else:
        vs = _gather(vars_arg)
    if not set_mode:
        x = vs[0] if vs else None
        if x is None:
            return Seq()
        try:
            sols = sp.solve(exprs if len(exprs) > 1 else exprs[0], x, dict=False)
        except NotImplementedError:
            raise CalcError("solve: geen exacte oplossing gevonden (probeer fsolve)")
        if isinstance(sols, dict):
            sols = [sols[x]] if x in sols else []
        if sols and isinstance(sols[0], (tuple, list)):
            sols = [s[0] for s in sols]
        sols = _maple_root_order(sols)
        return Seq(sols) if len(sols) != 1 else sols[0]
    try:
        sols = sp.solve(exprs, vs, dict=True)
    except NotImplementedError:
        raise CalcError("solve: geen exacte oplossing gevonden (probeer fsolve)")
    out = []
    for d in sols:
        keys = [v for v in vs if v in d] + [k for k in d if k not in vs]
        out.append([_to_eq(k, d[k]) for k in keys])
    is_list = isinstance(vars_arg, MList)
    if is_list:
        return MList(MList(o) for o in out)
    res = [MSet(o) for o in out]
    if not res:
        return Seq()
    return _seq(res)


@maple('isolate')
def isolate(ctx, eq, x, *rest):
    expr = _expr(eq)
    if isinstance(x, sp.Symbol):
        sols = sp.solve(expr, x)
        if not sols:
            raise CalcError("isolate: niet oplosbaar")
        return _to_eq(x, sols[0])
    d = sp.Dummy('d')
    e2 = expr.subs(x, d)
    sols = sp.solve(e2, d)
    return _to_eq(x, sols[0])


@maple('fsolve')
def fsolve(ctx, eqs, *rest):
    dg = _digits(ctx)
    rest = [r for r in rest if not (isinstance(r, sp.Equality) and isinstance(r.lhs, sp.Symbol) and r.lhs.name in
                                     ('maxsols', 'complex', 'avoid', 'fulldigits'))
            and not (isinstance(r, sp.Symbol) and r.name in ('complex', 'maxsols', 'fulldigits'))]
    vars_arg = rest[0] if rest else None
    eq_list = [_expr(q) for q in _gather(eqs)]
    system = len(eq_list) > 1 or isinstance(vars_arg, (MList, MSet))
    if vars_arg is None:
        fs = sorted(set().union(*[q.free_symbols for q in eq_list]), key=str)
        vlist = [(v, None, None) for v in fs]
    else:
        vlist = [_var_range(v) for v in _gather(vars_arg)]
    if not system:
        f = eq_list[0]
        x, lo, hi = vlist[0]
        if hi is None and lo is not None:
            guess = lo
            lo = None
        else:
            guess = None
        p = None
        try:
            p = sp.Poly(f, x)
        except Exception:
            p = None
        if p is not None and p.degree() >= 1 and guess is None:
            roots = [sp.re(r) for r in p.nroots(n=dg, maxsteps=200) if abs(sp.im(r)) < 10 ** (-dg + 2)]
            if lo is not None:
                roots = [r for r in roots if lo <= r <= hi]
            roots = sorted(roots)
            if not roots:
                return Seq()
            return _seq([sp.Float(r, dg) for r in roots])
        fl = sp.lambdify(x, f, 'mpmath')
        import mpmath
        mpmath.mp.dps = dg + 5
        if guess is not None:
            try:
                return sp.Float(mpmath.findroot(fl, float(guess)), dg)
            except Exception:
                raise CalcError("fsolve: geen oplossing gevonden")
        a, b = (float(lo), float(hi)) if lo is not None else (-20.0, 20.0)
        xs = np.linspace(a, b, 2001)
        fn = sp.lambdify(x, f, 'numpy')
        with np.errstate(all='ignore'):
            ys = np.asarray(fn(xs), dtype=float) * np.ones_like(xs)
        roots = []
        for i in range(len(xs) - 1):
            if np.isfinite(ys[i]) and np.isfinite(ys[i + 1]) and ys[i] * ys[i + 1] <= 0:
                try:
                    r = mpmath.findroot(fl, (xs[i], xs[i + 1]), solver='anderson')
                    roots.append(float(r))
                except Exception:
                    pass
        if lo is None and not roots:
            for g in (0.5, 1, -1, 2, -2, 3, 5, 10):
                try:
                    roots.append(float(mpmath.findroot(fl, g)))
                    break
                except Exception:
                    pass
        roots = sorted(set(round(r, dg) for r in roots))
        if not roots:
            raise CalcError("fsolve: geen oplossing gevonden")
        if lo is None:
            roots = roots[:1] if len(roots) > 0 and hi is None and vars_arg is not None and False else roots[:1]
        return _seq([sp.Float(r, dg) for r in roots])
    # stelsel
    vs = [v for v, _, _ in vlist]
    guess = []
    for v, lo, hi in vlist:
        if lo is not None and hi is None:
            guess.append(lo)
        elif lo is not None:
            guess.append((lo + hi) / 2)
        else:
            guess.append(1)
    sol = None
    import itertools
    tries = [guess] + [[g + d for g in guess] for d in (0.5, -1, 2)]
    for g in tries:
        try:
            sol = sp.nsolve(eq_list, vs, g, prec=dg + 5)
            break
        except Exception:
            continue
    if sol is None:
        raise CalcError("fsolve: geen oplossing gevonden")
    sol = list(sol)
    items = [_to_eq(v, sp.Float(s, dg)) for v, s in zip(vs, sol)]
    return MList(items) if isinstance(vars_arg, MList) else MSet(items)


# ------------------------------------------------------------------ dsolve
def _apps(e):
    return [a for a in e.atoms(AppliedUndef)]


def _find_funcs(exprs):
    fs = []
    for e in exprs:
        for a in e.atoms(AppliedUndef):
            if a.args and all(isinstance(g, sp.Symbol) for g in a.args) and a not in fs:
                fs.append(a)
    return fs


def _is_ic(q):
    if not isinstance(q, sp.Equality):
        return False
    l = q.lhs
    if isinstance(l, AppliedUndef) and all(g.is_number for g in l.args):
        return True
    if isinstance(l, sp.Subs) and isinstance(l.expr, sp.Derivative):
        return all(p.is_number for p in l.point)
    return False


def _ic_key(l, f):
    """Maple-IC-lhs -> sympy-ICsleutel voor functie f(x)."""
    x = f.args[0]
    if isinstance(l, AppliedUndef):
        return l.func(*l.args)
    d = l.expr
    g = d.expr
    n = sum(c for _, c in d.variable_count)
    return sp.Derivative(g.func(x), (x, n)).subs(x, l.point[0])


def _split_dsolve_args(ctx, ode, fn):
    """-> (odes, ics_eqs, funcs)"""
    items = _gather(ode)
    odes, ics = [], []
    for q in items:
        (ics if _is_ic(q) else odes).append(q)
    if fn is None:
        funcs = _find_funcs([_expr(q) for q in odes])
    else:
        funcs = [f for f in _gather(fn)]
    return odes, ics, funcs


def _ics_dict(ics, funcs):
    d = {}
    for q in ics:
        l = q.lhs
        if isinstance(l, AppliedUndef):
            f = next((g for g in funcs if g.func == l.func), None)
        else:
            f = next((g for g in funcs if g.func == l.expr.expr.func), None)
        if f is None:
            continue
        d[_ic_key(l, f)] = q.rhs
    return d


def _trigify(rhs):
    """_C1*exp(-I*w*t)+_C2*exp(I*w*t) -> _C1*sin(w*t)+_C2*cos(w*t) (constanten opnieuw gedefinieerd)."""
    cs = sorted([c for c in rhs.free_symbols if re.match(r'^_?C\d+$', c.name)], key=lambda c: c.name)
    if not any(isinstance(z, sp.exp) and z.args[0].has(sp.I) for z in rhs.atoms(sp.exp)):
        return rhs
    if not cs:
        new = sp.simplify(rhs.rewrite(sp.cos))
        return rhs if any(isinstance(z, sp.exp) and z.args[0].has(sp.I) for z in new.atoms(sp.exp)) else new
    new = sp.expand(rhs.rewrite(sp.cos))
    trig = sorted(new.atoms(sp.sin, sp.cos), key=lambda z: (isinstance(z, sp.cos), str(z)))
    if not trig:
        return rhs
    pieces = sp.collect(new, trig, evaluate=False)
    out, k = 0, 1
    for z in trig:
        c = pieces.pop(z, None)
        if c is None:
            continue
        cc = sp.simplify(c)
        if cc.has(*cs) and not (cc.free_symbols - set(cs)) and not cc.has(sp.I) or \
                (cc.has(*cs) and (cc.free_symbols - set(cs)) == set()):
            out += sp.Symbol(f"_C{k}") * z
            k += 1
        else:
            out += cc * z
    rest = sum(pieces.values()) if pieces else 0
    if any(isinstance(z, sp.exp) and z.args[0].has(sp.I) for z in sp.sympify(out + rest).atoms(sp.exp)):
        return rhs
    return out + rest


def _fix_fun_consts(e):
    e = _rename_consts(e)
    if isinstance(e, sp.Equality) and not isinstance(e.rhs, (list, tuple)):
        try:
            e = sp.Eq(e.lhs, _trigify(e.rhs), evaluate=False)
        except Exception:
            pass
    return e


def _numsol(ctx, odes, icd, funcs, rng):
    from scipy.integrate import solve_ivp
    x = funcs[0].args[0]
    names = [f.func for f in funcs]
    order = {}
    for q in odes:
        for dv in _expr(q).atoms(sp.Derivative):
            if isinstance(dv.expr, AppliedUndef):
                order[dv.expr.func] = max(order.get(dv.expr.func, 0), sum(c for _, c in dv.variable_count))
    for n in names:
        order.setdefault(n, 0)
    state = []
    for f in funcs:
        for k in range(order[f.func]):
            state.append((f, k))
    sym = {}
    for f, k in state:
        sym[(f.func, k)] = sp.Dummy(f"{f.func}_{k}")
    top = {}
    eqs = []
    for q in odes:
        e = _expr(q)
        eqs.append(e)
    highs = [sp.Dummy(f"{f.func}_h") for f in funcs]
    hsub = {}
    for f, h in zip(funcs, highs):
        o = order[f.func]
        if o:
            hsub[sp.Derivative(f, (x, o))] = h
    def to_sym(e):
        e = e.subs(hsub)
        for f, k in reversed(state):
            if k >= 1:
                e = e.subs(sp.Derivative(f, (x, k)), sym[(f.func, k)])
        for f, k in state:
            if k == 0:
                e = e.subs(f, sym[(f.func, 0)])
        return e
    eqs2 = [to_sym(e) for e in eqs]
    solh = sp.solve(eqs2, highs, dict=True)
    if not solh:
        raise CalcError("dsolve numeric: kan hoogste afgeleiden niet isoleren")
    solh = solh[0]
    rhs_exprs = []
    for f, k in state:
        if k < order[f.func] - 1:
            rhs_exprs.append(sym[(f.func, k + 1)])
        else:
            rhs_exprs.append(solh[highs[funcs.index(f)]])
    svars = [sym[(f.func, k)] for f, k in state]
    fn = sp.lambdify([x] + svars, rhs_exprs, 'numpy')
    y0 = []
    x0 = None
    for f, k in state:
        key = f if k == 0 else sp.Derivative(f, (x, k))
        val = None
        for kk, vv in icd.items():
            if isinstance(kk, AppliedUndef) and k == 0 and kk.func == f.func:
                val, x0c = vv, kk.args[0]
            elif isinstance(kk, sp.Subs) and k > 0 and kk.expr.expr.func == f.func and \
                    sum(c for _, c in kk.expr.variable_count) == k:
                val, x0c = vv, kk.point[0]
            elif isinstance(kk, sp.Derivative):
                pass
            else:
                continue
            if val is not None:
                x0 = x0c if x0 is None else x0
                break
        if val is None:
            raise CalcError("dsolve numeric: beginvoorwaarden onvolledig")
        y0.append(float(val))
    x0 = float(x0)
    dg = _digits(ctx)

    from .objs import PyFn

    class NumSol(PyFn):
        """Resultaat van dsolve(..., numeric): oproepbaar, geeft [x=.., y(x)=..]."""
        def __init__(s):
            PyFn.__init__(s, lambda c, *a: s(*a), "proc(x) ... end proc")
            s.x0, s.var, s.funcs, s.state = x0, x, funcs, state
            s.range = rng

        def eval(s, xv, n=400):
            xv = float(xv)
            if xv == s.x0:
                return np.array(y0)
            r = solve_ivp(lambda t, y: fn(t, *y), (s.x0, xv), y0, rtol=1e-10, atol=1e-12, method='LSODA')
            if not r.success:
                raise CalcError("dsolve numeric: integratie mislukt")
            return r.y[:, -1]

        def curve(s, a, b, n=400):
            ts = np.linspace(a, b, n)
            r = solve_ivp(lambda t, y: fn(t, *y), (s.x0, b if b >= s.x0 else a), y0, rtol=1e-10, atol=1e-12,
                          dense_output=True, method='LSODA')
            return ts, r.sol(ts)

        def __call__(s, xv, *a):
            vals = s.eval(xv)
            out = [_to_eq(s.var, sp.Float(float(xv), dg))]
            for i, (f, k) in enumerate(s.state):
                if k == 0:
                    out.append(_to_eq(f.func(s.var), sp.Float(float(vals[i]), dg)))
            return MList(out)
    return NumSol()


@maple('dsolve')
def dsolve(ctx, ode, *rest):
    pos, opts = split_opts(list(rest))
    names = [_name(r) for r in pos if isinstance(r, sp.Symbol)]
    fn = next((r for r in pos if not (isinstance(r, sp.Symbol))), None)
    if fn is None and any(isinstance(r, sp.Symbol) and r not in () and False for r in pos):
        pass
    numeric = 'numeric' in names or _name(opts.get('type', '')) == 'numeric'
    method = _name(opts.get('method', '')) if 'method' in opts else ''
    if method == 'numeric':
        numeric = True
    odes, ics, funcs = _split_dsolve_args(ctx, ode, fn)
    if isinstance(fn, sp.Basic) and isinstance(fn, AppliedUndef):
        funcs = [fn]
    if not funcs:
        raise CalcError("dsolve: onbekende functie niet gevonden")
    icd = _ics_dict(ics, funcs)
    exprs = [q if isinstance(q, sp.Equality) else sp.Eq(q, 0) for q in odes]
    if numeric:
        rng = opts.get('range')
        return _numsol(ctx, exprs, icd, funcs, rng)
    if method == 'laplace':
        return _dsolve_laplace(exprs, icd, funcs)
    multi = len(exprs) > 1 or isinstance(ode, (MSet, MList)) and len(funcs) > 1
    try:
        if len(funcs) > 1 or len(exprs) > 1:
            sol = sp.dsolve(exprs, funcs, ics=icd or None)
        else:
            sol = sp.dsolve(exprs[0], funcs[0], ics=icd or None)
    except NotImplementedError as ex:
        raise CalcError(f"dsolve: geen oplossing gevonden ({ex})")
    if isinstance(sol, (list, tuple)):
        sol = [_fix_fun_consts(s) for s in sol]
        if len(funcs) > 1 or len(exprs) > 1:
            return MSet(sol)
        return _seq(sol)
    return _fix_fun_consts(sol)


def _dsolve_laplace(exprs, icd, funcs):
    x = funcs[0].args[0]
    s = sp.Symbol('s', positive=True)
    Ys = {f.func: sp.Symbol('Y_' + str(f.func)) for f in funcs}
    eqs = []
    for q in exprs:
        e = _expr(q)
        L = sp.laplace_transform(sp.expand(e), x, s, noconds=True)
        L = L.replace(lambda z: isinstance(z, sp.LaplaceTransform) and isinstance(z.args[0], AppliedUndef),
                      lambda z: Ys[z.args[0].func])
        eqs.append(L)
    atoms = set()
    for L in eqs:
        for a in L.atoms(AppliedUndef):
            if all(g.is_number for g in a.args):
                atoms.add(a)
        for a in L.atoms(sp.Subs):
            atoms.add(a)
    sub = {}
    for a in atoms:
        if isinstance(a, AppliedUndef):
            key = a
            nm = f"{a.func}({a.args[0]})"
        else:
            g = a.expr.expr
            n = sum(c for _, c in a.expr.variable_count)
            key = sp.Derivative(g.func(x), (x, n)).subs(x, a.point[0])
            nm = f"D{'' if n == 1 else '^' + str(n)}({g.func})({a.point[0]})"
            nm = f"({'D' if n == 1 else '@@'.join(['D'] * n)})({g.func})({a.point[0]})" if n > 1 else \
                f"D({g.func})({a.point[0]})"
        sub[a] = icd.get(key, sp.Symbol(nm))
    eqs = [L.xreplace(sub) for L in eqs]
    sol = sp.solve(eqs, list(Ys.values()), dict=True)
    if not sol:
        raise CalcError("dsolve laplace: geen oplossing")
    sol = sol[0]
    out = []
    for f in funcs:
        F = sol[Ys[f.func]]
        r = _invlaplace_core(sp.simplify(F), s, x)
        out.append(sp.Eq(f, r, evaluate=False))
    return MSet(out) if len(out) > 1 else out[0]


# ------------------------------------------------------------------ pdsolve
@maple('pdsolve')
def pdsolve(ctx, pde, *rest):
    pos, opts = split_opts(list(rest))
    fn = next((r for r in pos if isinstance(r, AppliedUndef)), None)
    items = _gather(pde)
    pdes = [q for q in items if isinstance(q, sp.Equality) and not _pde_cond(q)] or \
           [q for q in items if not isinstance(q, sp.Equality)]
    conds = [q for q in items if isinstance(q, sp.Equality) and _pde_cond(q)]
    if not pdes:
        raise CalcError("pdsolve: PDE ontbreekt")
    eq = _expr(pdes[0])
    if fn is None:
        fs = [a for a in eq.atoms(AppliedUndef) if len(a.args) >= 2]
        if not fs:
            raise CalcError("pdsolve: onbekende functie niet gevonden")
        fn = fs[0]
    u = fn
    if len(u.args) != 2:
        res = sp.pdsolve(eq, u)
        return _rename_pde(res)
    x, t = u.args
    d = {}
    derivs = {}
    for a, nm in [((x,), 'x'), ((t,), 't'), ((x, x), 'xx'), ((t, t), 'tt'), ((x, t), 'xt')]:
        derivs[nm] = sp.Derivative(u, *a)
    ssym = {nm: sp.Dummy(nm) for nm in derivs}
    e2 = sp.expand(eq)
    for nm in ('xx', 'tt', 'xt', 'x', 't'):
        e2 = e2.subs(derivs[nm], ssym[nm])
    u0 = sp.Dummy('u0')
    e2 = e2.subs(u, u0)
    co = {nm: e2.coeff(ssym[nm]) for nm in derivs}
    co['u'] = e2.coeff(u0)
    rest0 = sp.simplify(e2 - sum(co[nm] * ssym[nm] for nm in derivs) - co['u'] * u0)
    linear = rest0 == 0 and co['xt'] == 0
    if conds and linear and co['u'] == 0 and co['x'] == 0:
        r = _pde_series(ctx, co, u, x, t, conds)
        if r is not None:
            return r
    if not linear or (co['xx'] == 0 and co['tt'] == 0):
        res = sp.pdsolve(eq, u)
        return _rename_pde(res)
    return _pde_separate(co, u, x, t)


def _pde_cond(q):
    l = q.lhs
    if isinstance(l, AppliedUndef):
        return any(a.is_number for a in l.args)
    if isinstance(l, sp.Subs):
        return True
    return False


def _rename_pde(res):
    def f(z):
        return isinstance(z, AppliedUndef) and z.func.__name__ == 'F'
    out = res.replace(f, lambda z: sp.Function('_F1')(*z.args))
    return _rename_consts(out)


def _pde_separate(co, u, x, t):
    F1, F2 = sp.Function('_F1'), sp.Function('_F2')
    c = sp.Symbol('_c1')
    X, T = F1(x), F2(t)
    xt = sum(co[k] * sp.Derivative(X, (x, n)) for k, n in (('x', 1), ('xx', 2)))
    tt = sum(co[k] * sp.Derivative(T, (t, n)) for k, n in (('t', 1), ('tt', 2)))
    if co['u'] != 0:
        xt = xt + co['u'] * X
    ode_x = sp.Eq(xt + c * X, 0, evaluate=False) if True else None
    ode_t = sp.Eq(tt - c * T, 0, evaluate=False)
    # (xt/X) + (tt/T) = 0  ->  xt/X = -_c1 ; tt/T = _c1
    # voor stabiele uitvoer: xt = -c*X, tt = c*T
    ode_x = sp.Eq(xt, -c * X, evaluate=False)
    ode_t = sp.Eq(tt, c * T, evaluate=False)
    return Seq([sp.Eq(u, X * T, evaluate=False), MSet([ode_x, ode_t])])


def _dirichlet(conds, u, x, t):
    bx = []
    for q in conds:
        l = q.lhs
        if isinstance(l, AppliedUndef) and l.func == u.func and l.args[0].is_number and l.args[1] == t \
                and sp.simplify(q.rhs) == 0:
            bx.append(l.args[0])
    return sorted(set(bx), key=lambda z: float(z)) if len(set(bx)) == 2 else None


def _pde_series(ctx, co, u, x, t, conds):
    bx = _dirichlet(conds, u, x, t)
    if bx is None:
        return None
    a, b = bx
    L = b - a
    n = sp.Symbol('n', integer=True, positive=True)
    f0 = g0 = None
    for q in conds:
        l = q.lhs
        if isinstance(l, AppliedUndef) and l.args[1].is_number and l.args[0] == x:
            f0 = q.rhs
        elif isinstance(l, sp.Subs) and isinstance(l.expr, sp.Derivative):
            dv = l.expr
            if dv.variables == (t,) and dv.expr.args[0] == x:
                g0 = q.rhs
    if f0 is None:
        return None
    phi = sp.sin(n * sp.pi * (x - a) / L)
    def coef(g):
        return sp.simplify(2 / L * sp.integrate(g * phi, (x, a, b)))
    if co['t'] != 0 and co['tt'] == 0:
        k = sp.simplify(-co['xx'] / co['t'])
        Bn = coef(f0)
        term = Bn * phi * sp.exp(-k * (n * sp.pi / L) ** 2 * t)
    elif co['tt'] != 0 and co['t'] == 0:
        c2 = sp.simplify(-co['xx'] / co['tt'])
        c = sp.sqrt(c2)
        w = c * n * sp.pi / L
        An = coef(f0)
        term = An * sp.cos(w * t) * phi
        if g0 is not None and g0 != 0:
            Bn = sp.simplify(coef(g0) / w)
            term = term + Bn * sp.sin(w * t) * phi
    else:
        return None
    return sp.Eq(u, sp.Sum(term, (n, 1, oo)), evaluate=False)


# ------------------------------------------------------------------ inttrans
def _laplace_core(f, t, s):
    try:
        r = sp.laplace_transform(f, t, s, noconds=True)
    except Exception:
        return None
    if isinstance(r, sp.LaplaceTransform) or r.has(sp.LaplaceTransform):
        if isinstance(r, sp.LaplaceTransform) and r.args[0] == f:
            return None
    return r


@maple('laplace', pkg='inttrans')
def laplace(ctx, f, t, s):
    def one(e):
        e = sp.sympify(e)
        r = _laplace_core(e, t, s)
        if r is None:
            return sp.LaplaceTransform(e, t, s)
        if r.has(sp.I):
            r = sp.simplify(r)
            if r.is_rational_function(s):
                r = sp.factor(r)
        return r
    return _mapv(one, f)


def _strip_heaviside(e, t):
    return e.replace(lambda z: isinstance(z, sp.Heaviside) and z.args[0] == t, lambda z: sp.Integer(1))


def _invlaplace_core(F, s, t):
    try:
        r = sp.inverse_laplace_transform(F, s, t)
        if r.has(sp.InverseLaplaceTransform):
            raise ValueError
    except Exception:
        r = None
        try:
            ap = sp.apart(F, s)
            parts = [sp.inverse_laplace_transform(a, s, t) for a in sp.Add.make_args(ap)]
            if not any(p.has(sp.InverseLaplaceTransform) for p in parts):
                r = sp.Add(*parts)
        except Exception:
            r = None
        if r is None:
            return sp.InverseLaplaceTransform(F, s, t)
    r = _strip_heaviside(r, t)
    return sp.simplify(r) if r.has(sp.exp) and False else r


@maple('invlaplace', pkg='inttrans')
def invlaplace(ctx, F, s, t):
    return _mapv(lambda e: _invlaplace_core(sp.sympify(e), s, t), F)


def _exp_lin(term, t):
    """term = c*exp(I*a*t) -> (c, a) of None."""
    c, rest = term.as_independent(t, as_Add=False)
    if rest == 1:
        return c, sp.Integer(0)
    if isinstance(rest, sp.exp):
        arg = sp.expand(rest.args[0])
        a = sp.simplify(arg / (sp.I * t))
        if not a.has(t) and not a.has(sp.I) or (not a.has(t) and a.is_real):
            return c, a
        if not a.has(t):
            return c, a
    return None


def _fourier_core(f, t, w):
    f = sp.sympify(f)
    if f.has(sp.sin) and f.has(t):
        m = sp.simplify(f * t)
        ca, aa = sp.Wild('ca', exclude=[t]), sp.Wild('aa', exclude=[t])
        mm = m.match(ca * sp.sin(aa * t))
        if mm is not None and mm[aa] != 0:
            a_ = abs(mm[aa]) if mm[aa].is_number else mm[aa]
            return sp.pi * mm[ca] * (sp.Heaviside(w + a_, sp.Rational(1, 2)) - sp.Heaviside(w - a_, sp.Rational(1, 2)))
    parts = sp.Add.make_args(sp.expand(f.rewrite(sp.exp))) if f.has(sp.sin, sp.cos) else sp.Add.make_args(f)
    out = []
    for p in parts:
        c0, h0 = p.as_independent(t, as_Add=False)
        if isinstance(h0, sp.Heaviside) and h0.args[0] == t:
            out.append(c0 * (sp.pi * sp.DiracDelta(w) - sp.I / w))
            continue
        if isinstance(h0, sp.sign) and h0.args[0] == t:
            out.append(-2 * sp.I * c0 / w)
            continue
        ex = _exp_lin(p, t)
        if ex is not None and (p.has(sp.exp) or p.is_number or not p.has(t)):
            c, a = ex
            out.append(2 * sp.pi * c * sp.DiracDelta(w - a))
            continue
        r = None
        try:
            k = sp.Dummy('k')
            r0 = sp.fourier_transform(p, t, k)
            if not r0.has(sp.FourierTransform):
                r = r0.subs(k, w / (2 * sp.pi))
        except Exception:
            r = None
        if r is None:
            try:
                r = sp.integrate(p * sp.exp(-sp.I * w * t), (t, -oo, oo), conds='none')
                if r.has(sp.Integral):
                    r = None
            except Exception:
                r = None
        if r is None:
            return sp.FourierTransform(f, t, w)
        out.append(r)
    return sp.simplify(sp.Add(*out))


@maple('fourier', pkg='inttrans')
def fourier(ctx, f, t, w):
    return _mapv(lambda e: _fourier_core(e, t, w), f)


def _invfourier_core(F, w, t):
    F = sp.sympify(F)
    parts = sp.Add.make_args(sp.expand(F))
    out = []
    for p in parts:
        if p.has(sp.DiracDelta):
            c, rest = p.as_independent(sp.DiracDelta, as_Add=False)
            if isinstance(rest, sp.DiracDelta) and len(rest.args) == 1:
                arg = rest.args[0]
                lin = sp.Poly(arg, w)
                if lin.degree() == 1:
                    m, q = lin.all_coeffs()
                    w0 = -q / m
                    out.append(c / (2 * sp.pi * abs(m)) * sp.exp(sp.I * w0 * t))
                    continue
        r = None
        try:
            k = sp.Dummy('k')
            r0 = sp.inverse_fourier_transform(p.subs(w, 2 * sp.pi * k), k, t)
            if not r0.has(sp.InverseFourierTransform):
                r = r0
        except Exception:
            r = None
        if r is None:
            try:
                r = sp.integrate(p * sp.exp(sp.I * w * t), (w, -oo, oo), conds='none') / (2 * sp.pi)
                if r.has(sp.Integral):
                    r = None
            except Exception:
                r = None
        if r is None:
            return sp.InverseFourierTransform(F, w, t)
        out.append(r)
    return sp.simplify(sp.Add(*out))


@maple('invfourier', pkg='inttrans')
def invfourier(ctx, F, w, t):
    return _mapv(lambda e: _invfourier_core(e, w, t), F)


@maple('fouriercos', pkg='inttrans')
def fouriercos(ctx, f, t, w):
    def one(e):
        if not sp.sympify(e).has(t):
            return sp.sqrt(sp.pi / 2) * e * sp.DiracDelta(w)
        r = sp.integrate(sp.sqrt(2 / sp.pi) * e * sp.cos(w * t), (t, 0, oo), conds='none')
        if r.has(sp.Integral):
            k = sp.Dummy('k')
            r = sp.cosine_transform(e, t, k).subs(k, w / (2 * sp.pi))
        return sp.simplify(r)
    return _mapv(one, f)


@maple('fouriersin', pkg='inttrans')
def fouriersin(ctx, f, t, w):
    def one(e):
        if not sp.sympify(e).has(t):
            return sp.simplify(sp.sqrt(2 / sp.pi) * e / w)
        r = sp.integrate(sp.sqrt(2 / sp.pi) * e * sp.sin(w * t), (t, 0, oo), conds='none')
        if r.has(sp.Integral):
            k = sp.Dummy('k')
            r = sp.sine_transform(e, t, k).subs(k, w / (2 * sp.pi))
        return sp.simplify(r)
    return _mapv(one, f)


# ------------------------------------------------------------------ FFT / DFT
def _to_np(a):
    if isinstance(a, sp.MatrixBase):
        return np.array([complex(z) for z in a], dtype=complex), 'M', a.shape
    return np.array([complex(z) for z in a], dtype=complex), 'L', None


def _from_np(v, kind, shape):
    def conv(z):
        z = complex(z)
        if abs(z.imag) < 1e-12 * max(1.0, abs(z.real)):
            return sp.Float(z.real)
        return sp.Float(z.real) + sp.I * sp.Float(z.imag)
    items = [conv(z) for z in v]
    if kind == 'M':
        return sp.Matrix(items).reshape(*shape)
    return MList(items)


@maple('FourierTransform', 'FFT', 'DFT', pkg='DiscreteTransforms')
def fft(ctx, a, *rest):
    v, k, sh = _to_np(a)
    return _from_np(np.fft.fft(v), k, sh)


@maple('InverseFourierTransform', 'iFFT', 'IDFT', pkg='DiscreteTransforms')
def ifft(ctx, a, *rest):
    v, k, sh = _to_np(a)
    return _from_np(np.fft.ifft(v), k, sh)
