"""PDV's met randvoorwaarden voor mini-Maple: scheiding van variabelen met exacte Fouriercoefficienten.

Ondersteund (lineair, constante coefficienten):
  * warmte u_t = k u_xx + r u + s(x) en golf u_tt = c^2 u_xx + r u + s(x) op [a,b], met Dirichlet, Neumann
    en gemengde randen (constante randwaarden worden via een stationaire oplossing afgesplitst);
  * hetzelfde in 2D (u(x,y,t)) op een rechthoek, homogene randen;
  * Laplace u_xx+u_yy=0 op een rechthoek (Dirichlet/Neumann per zijde, superpositie van 4 deelproblemen);
  * Laplace op de schijf u_rr+u_r/r+u_thth/r^2=0 (Dirichlet of Neumann, theta in [0,2 Pi]);
  * radiale warmte-/golfvergelijking op een schijf/trommel (Bessel; nulpunten als BesselJZeros(nu,n)).
Niet ondersteund: Robin-randen, tijdsafhankelijke randwaarden, convectie/demping, niet-radiale trommel.
Alleen SymPy-API; geen Maple-code.
"""
import sympy as sp
from sympy.core.function import AppliedUndef

oo = sp.oo
BesselJZeros = sp.Function('BesselJZeros')


class PdeError(ValueError):
    pass


def _idx(name):
    return sp.Symbol(name, integer=True, positive=True)


def _finite(e):
    return not (e.has(sp.nan) or e.has(sp.zoo) or e.has(sp.oo) or e.has(-sp.oo))


# ------------------------------------------------------------------ lineaire ontleding
def _lin_atoms(expr, u):
    """expr (lineair in u en zijn afgeleiden op een punt) -> ([(coef, {argindex: orde}, punt)], rest)."""
    expr = sp.expand(expr)
    rep, info = {}, {}
    for s in expr.atoms(sp.Subs):
        e = s.expr
        if isinstance(e, sp.Derivative) and isinstance(e.expr, AppliedUndef) and e.expr.func == u.func:
            sub = dict(zip(s.variables, s.point))
            pt = tuple(a.xreplace(sub) for a in e.expr.args)
            orders = {}
            for v, c in e.variable_count:
                if v not in e.expr.args:
                    raise PdeError("pdsolve: onbegrepen afgeleide in voorwaarde")
                orders[e.expr.args.index(v)] = orders.get(e.expr.args.index(v), 0) + int(c)
            d = sp.Dummy('d')
            rep[s] = d
            info[d] = (orders, pt)
    expr = expr.xreplace(rep)
    for a in expr.atoms(AppliedUndef):
        if a.func == u.func:
            d = sp.Dummy('d')
            rep[a] = d
            info[d] = ({}, tuple(a.args))
    expr = sp.expand(expr.xreplace({k: v for k, v in rep.items() if isinstance(k, AppliedUndef)}))
    out, rest = [], expr
    for d, (orders, pt) in info.items():
        c = expr.coeff(d)
        if c != 0:
            out.append((c, orders, pt))
            rest = rest - c * d
    rest = sp.expand(rest)
    if any(rest.has(d) for d in info):
        raise PdeError("pdsolve: voorwaarde is niet lineair")
    return out, rest


def is_pde(q, u):
    """Is Eq q een PDV (bevat een niet-gepunte afgeleide van u) en geen rand-/beginvoorwaarde?"""
    z = q.xreplace({s: sp.Integer(0) for s in q.atoms(sp.Subs)})
    return any(isinstance(d.expr, AppliedUndef) and d.expr.func == u.func for d in z.atoms(sp.Derivative))


def classify_cond(q, u):
    """-> (pinned index, positie, {orde: coef}, rhs)."""
    atoms, rest = _lin_atoms(q.lhs - q.rhs, u)
    if not atoms:
        raise PdeError("pdsolve: voorwaarde zonder u")
    pin, pos, terms = None, None, {}
    for c, orders, pt in atoms:
        pinned = [i for i, (p, a) in enumerate(zip(pt, u.args)) if p != a]
        if len(pinned) != 1:
            raise PdeError("pdsolve: voorwaarde moet op een rand of begintijdstip gesteld zijn: %s" % q)
        i = pinned[0]
        if any(j != i for j in orders):
            raise PdeError("pdsolve: gemengde afgeleiden in voorwaarden niet ondersteund")
        if pin is None:
            pin, pos = i, pt[i]
        elif pin != i or sp.simplify(pos - pt[i]) != 0:
            raise PdeError("pdsolve: voorwaarde met meerdere punten niet ondersteund")
        o = orders.get(i, 0)
        terms[o] = terms.get(o, 0) + c
    return pin, pos, terms, sp.simplify(-rest)


def pde_coeffs(eq, u):
    """eq (=0) -> ({orden-tuple: coef}, rest) of None als niet-lineair."""
    n = len(u.args)
    expr = sp.expand(eq)
    rep, key = {}, {}
    for d in sorted(expr.atoms(sp.Derivative), key=lambda z: -sum(c for _, c in z.variable_count)):
        if not (isinstance(d.expr, AppliedUndef) and d.expr.func == u.func and d.expr.args == u.args):
            return None
        o = [0] * n
        for v, c in d.variable_count:
            o[u.args.index(v)] += int(c)
        dm = sp.Dummy('D')
        rep[d] = dm
        key[dm] = tuple(o)
    expr = expr.xreplace(rep)
    um = sp.Dummy('U')
    expr = sp.expand(expr.xreplace({u: um}))
    key[um] = (0,) * n
    co, rest = {}, expr
    for dm, k in key.items():
        c = expr.coeff(dm)
        co[k] = sp.simplify(c)
        rest = rest - c * dm
    rest = sp.expand(rest)
    if any(rest.has(dm) for dm in key):
        return None
    return co, sp.simplify(rest)


# ------------------------------------------------------------------ basisfuncties
class Basis:
    """Eigenfuncties van -X'' = lam X op [lo,hi]: phi(i), wavenumber kk(i), kwadr. norm; eventueel nulmodus."""

    def __init__(self, var, lo, hi, kinds, name):
        self.var, self.lo, self.hi, self.kinds = var, lo, hi, kinds
        self.L = sp.simplify(hi - lo)
        L, xi = self.L, var - lo
        self.sym = _idx(name)
        ka, kb = kinds
        self.zero = False
        self.norm = L / 2
        self.znorm = L
        if (ka, kb) == ('D', 'D'):
            self.phi = lambda i: sp.sin(i * sp.pi * xi / L)
            self.kk = lambda i: i * sp.pi / L
        elif (ka, kb) == ('N', 'N'):
            self.phi = lambda i: sp.cos(i * sp.pi * xi / L)
            self.kk = lambda i: i * sp.pi / L
            self.zero = True
        elif (ka, kb) == ('D', 'N'):
            self.phi = lambda i: sp.sin((2 * i - 1) * sp.pi * xi / (2 * L))
            self.kk = lambda i: (2 * i - 1) * sp.pi / (2 * L)
        else:
            self.phi = lambda i: sp.cos((2 * i - 1) * sp.pi * xi / (2 * L))
            self.kk = lambda i: (2 * i - 1) * sp.pi / (2 * L)
        self.weight = 1


class PeriodicBasis(Basis):
    """cos(n th) (met nulmodus) of sin(n th) op [0, 2 Pi]."""

    def __init__(self, var, kind, name):
        self.var, self.lo, self.hi = var, sp.Integer(0), 2 * sp.pi
        self.L = 2 * sp.pi
        self.sym = _idx(name)
        self.norm = sp.pi
        self.znorm = 2 * sp.pi
        self.zero = kind == 'cos'
        self.phi = (lambda i: sp.cos(i * var)) if kind == 'cos' else (lambda i: sp.sin(i * var))
        self.kk = lambda i: i
        self.weight = 1


class BesselBasis(Basis):
    """J0(alpha_n r/R) met J_nu-nulpunten (Dirichlet: nu=0 -> J0(alpha)=0; Neumann: J0'=-J1 nul -> nu=1)."""

    def __init__(self, var, R, kind, name):
        self.var, self.lo, self.hi, self.L = var, sp.Integer(0), R, R
        self.sym = _idx(name)
        self.kind = kind
        nu = 0 if kind == 'D' else 1
        self.alpha = lambda i: BesselJZeros(nu, i)
        self.phi = lambda i: sp.besselj(0, self.alpha(i) * var / R)
        self.kk = lambda i: self.alpha(i) / R
        self.zero = kind == 'N'
        self.weight = var
        if kind == 'D':
            self.nrm = lambda i: R ** 2 / 2 * sp.besselj(1, self.alpha(i)) ** 2
        else:
            self.nrm = lambda i: R ** 2 / 2 * sp.besselj(0, self.alpha(i)) ** 2
        self.znorm = R ** 2 / 2
        self.norm = None


def _norm(B, i):
    return B.nrm(i) if getattr(B, 'nrm', None) else B.norm


# ------------------------------------------------------------------ coefficienten (stukken)
def _integrate(f, var, lo, hi):
    try:
        return sp.integrate(f, (var, lo, hi))
    except Exception:
        return sp.Integral(f, (var, lo, hi))


def _clean(e):
    e = sp.simplify(e)
    return e


def _dim_pieces(g, B):
    """Coefficientstukken van g(var) in basis B: lijst van (coef, mode); mode = ('gen',) | ('zero',) | ('pt', n0)."""
    if g == 0:
        return []
    out = []
    var, n = B.var, B.sym
    if B.zero:
        c0 = _integrate(g * B.weight, var, B.lo, B.hi) / B.znorm
        c0 = _clean(c0)
        if c0 != 0:
            out.append((c0, ('zero',)))
    if isinstance(B, BesselBasis):
        al = sp.Dummy('al', positive=True)
        I = _integrate(g * sp.besselj(0, al * var / B.L) * var, var, B.lo, B.hi)
        if I.has(sp.hyper) or I.has(sp.meijerg):
            I = sp.Integral(g * B.phi(n) * var, (var, B.lo, B.hi))
        else:
            I = I.xreplace({al: B.alpha(n)})
        out.append((_clean(I / _norm(B, n)) if not I.has(sp.Integral) else I / _norm(B, n), ('gen',)))
        return out
    gen_sum, extras_d = 0, {}
    for term in sp.Add.make_args(sp.expand(g)):
        I = _integrate(term * B.phi(n), var, B.lo, B.hi)
        generic, extras = I, []
        if isinstance(I, sp.Piecewise):
            gens, spec, nes, tail, bad = [], [], [], None, False
            for e, c in I.args:
                if isinstance(c, sp.Equality):
                    sol = sp.solve(c, n)
                    if len(sol) == 1 and sol[0].is_Integer:
                        spec.append((sol[0], e))
                        continue
                    bad = True
                elif isinstance(c, sp.Unequality) and c.lhs == n and c.rhs.is_Integer:
                    gens.append(e)
                    nes.append(c.rhs)
                elif c == True:
                    if nes:
                        tail = e
                    else:
                        gens.append(e)
                else:
                    bad = True
            if nes and tail is not None:
                spec += [(k, tail) for k in nes]
            if not bad and len(gens) == 1:
                gen0 = gens[0]
                if all(_finite(sp.sympify(gen0).subs(n, n0)) for n0, _ in spec):
                    generic = gen0
                    extras = [(n0, val - sp.sympify(gen0).subs(n, n0)) for n0, val in spec]
        gen_sum = gen_sum + generic
        for n0, d in extras:
            extras_d[n0] = extras_d.get(n0, 0) + d
    c = _clean(gen_sum / B.norm)
    if c != 0:
        out.append((c, ('gen',)))
    for n0, val in extras_d.items():
        d = _clean(val / B.norm)
        if d != 0:
            out.append((d, ('pt', n0)))
    return out


def _split_factors(term, vars_):
    """term -> (const, [g per var]) of None als niet te splitsen."""
    parts = [sp.Integer(1)] * len(vars_)
    const = sp.Integer(1)
    for f in sp.Mul.make_args(term):
        deps = [i for i, v in enumerate(vars_) if f.has(v)]
        if not deps:
            const *= f
        elif len(deps) == 1:
            parts[deps[0]] *= f
        else:
            return None
    return const, parts


def _pieces(g, dims):
    """Lijst (coef, modes-tuple) voor g(vars) in het product van de basissen (gelijke modes samengenomen)."""
    raw = _pieces_raw(g, dims)
    merged = {}
    for c, m in raw:
        merged[m] = merged.get(m, 0) + c
    out = []
    for m, c in merged.items():
        c = c if c.has(sp.Integral) else _clean(c)
        if c != 0:
            out.append((c, m))
    return out


def _pieces_raw(g, dims):
    out = []
    g = sp.expand(g)
    for term in sp.Add.make_args(g):
        if term == 0:
            continue
        if len(dims) == 1:
            out += [(c, (m,)) for c, m in _dim_pieces(term, dims[0])]
            continue
        sp_ = _split_factors(term, [B.var for B in dims])
        if sp_ is not None:
            const, parts = sp_
            lists = [_dim_pieces(p, B) for p, B in zip(parts, dims)]
            combos = [(const, ())]
            for lst in lists:
                combos = [(c * c2, ms + (m,)) for c, ms in combos for c2, m in lst]
            out += [(sp.simplify(c), ms) for c, ms in combos]
        else:
            combos = [((), ())]
            for B in dims:
                opts = [(('gen',), B.phi(B.sym), _norm(B, B.sym))]
                if B.zero:
                    opts.append((('zero',), sp.Integer(1), B.znorm))
                combos = [(ms + (m,), (ph + (p,)), None) for ms, ph, _ in combos for m, p, _n in opts]
            # eenvoudige herberekening (geen weeg-/resonantie-afhandeling)
            for ms, ph, _ in combos:
                f = term
                den = sp.Integer(1)
                for B, m, p in zip(dims, ms, ph):
                    f = f * p
                    den = den * (B.znorm if m == ('zero',) else B.norm)
                val = f
                for B in dims:
                    val = _integrate(val, B.var, B.lo, B.hi)
                out.append((sp.simplify(val / den) if not val.has(sp.Integral) else val / den, ms))
    return out


def _mode_index(B, m):
    if m[0] == 'gen':
        return B.sym
    if m[0] == 'pt':
        return sp.Integer(m[1])
    return sp.Integer(0)


def _assemble(items, dims):
    """items: [(modes, summand)] -> som van expliciete termen en Sums, gegroepeerd per type."""
    groups = {}
    order = []
    for modes, term in items:
        if modes not in groups:
            groups[modes] = 0
            order.append(modes)
        groups[modes] = groups[modes] + term
    zero_t, sums, pts = [], [], []
    for modes in order:
        t = groups[modes]
        syms = [B.sym for B, m in zip(dims, modes) if m[0] == 'gen']
        if syms:
            S = t
            for sy in reversed(syms):
                S = sp.Sum(S, (sy, 1, oo))
            sums.append(S)
        elif all(m[0] == 'zero' for m in modes):
            zero_t.append(t)
        else:
            pts.append(t)
    return sp.Add(*zero_t, *sums, *pts, evaluate=False) if len(zero_t) + len(sums) + len(pts) > 1 else \
        (sums + zero_t + pts)[0] if (sums + zero_t + pts) else sp.Integer(0)


def _phi_for(B, m):
    if m[0] == 'zero':
        return sp.Integer(1)
    return B.phi(_mode_index(B, m))


def _prod_phi(dims, modes):
    p = sp.Integer(1)
    for B, m in zip(dims, modes):
        p = p * _phi_for(B, m)
    return p


# ------------------------------------------------------------------ randen
def _side(bcs, var):
    """Lijst voorwaarden op var -> (a, b, (ka,kb), (va,vb)) met a<b."""
    byp = []
    for pos, terms, rhs in bcs:
        if len(terms) != 1 and sum(1 for c in terms.values() if c != 0) != 1:
            raise PdeError("pdsolve: Robin-randvoorwaarden worden niet ondersteund")
        (o, c), = [(o, c) for o, c in terms.items() if c != 0]
        if o not in (0, 1):
            raise PdeError("pdsolve: randvoorwaarde met afgeleide van orde %d niet ondersteund" % o)
        byp.append((pos, 'D' if o == 0 else 'N', sp.simplify(rhs / c)))
    if len(byp) != 2 or sp.simplify(byp[0][0] - byp[1][0]) == 0:
        raise PdeError("pdsolve: precies een randvoorwaarde op elk van de twee randen van %s nodig" % var)
    p, q = byp
    d = sp.simplify(q[0] - p[0])
    if d.is_positive is False or (d.is_positive is None and (p[0] != 0 and q[0] == 0)):
        p, q = q, p
    return p, q


def _steady(k, r, s, x, p, q):
    """Stationaire v(x): k v'' + r v + s = 0 met randwaarden (alleen als nodig)."""
    vals = [p[2], q[2]]
    if s == 0 and all(v == 0 for v in vals):
        return sp.Integer(0)
    if r != 0:
        raise PdeError("pdsolve: inhomogene randen/bron met term r*u niet ondersteund")
    c1, c2 = sp.symbols('_c1 _c2')
    v = -sp.integrate(sp.integrate(s / k, x), x) + c1 * x + c2
    eqs = []
    for (pos, kind, val) in (p, q):
        eqs.append(sp.Eq(v.subs(x, pos) if kind == 'D' else sp.diff(v, x).subs(x, pos), val))
    sol = sp.solve(eqs, [c1, c2], dict=True)
    if not sol or c1 not in sol[0] and c2 not in sol[0]:
        raise PdeError("pdsolve: geen stationaire toestand voor deze randvoorwaarden/bron")
    sol = sol[0]
    if c1 not in sol or c2 not in sol:
        raise PdeError("pdsolve: geen eenduidige stationaire toestand (Neumann-Neumann met inhomogeniteit)")
    return sp.simplify(v.subs(sol))


def _sqrt(c2):
    return sp.powdenest(sp.sqrt(c2), force=True)


# ------------------------------------------------------------------ evolutie (1D en 2D rechthoek)
def _evolution(kind, co, rest, u, bcs, ics):
    nsp = len(u.args) - 1
    t = u.args[-1]
    spat = list(u.args[:-1])
    kt = (0,) * nsp + ((1,) if kind == 'heat' else (2,))
    T = co.get(kt, 0)
    A = {}
    for i in range(nsp):
        o = [0] * (nsp + 1)
        o[i] = 2
        A[i] = sp.simplify(-co.get(tuple(o), 0) / T)
    r = sp.simplify(-co.get((0,) * (nsp + 1), 0) / T)
    s = sp.simplify(-rest / T)
    if s.has(t):
        raise PdeError("pdsolve: tijdsafhankelijke bron niet ondersteund")
    bases = []
    sides = []
    for i, x in enumerate(spat):
        p, q = _side(bcs.get(i, []), x)
        sides.append((p, q))
        bases.append(Basis(x, p[0], q[0], (p[1], q[1]), 'nmk'[i]))
    v = sp.Integer(0)
    if nsp == 1:
        v = _steady(A[0], r, s, spat[0], *sides[0])
    else:
        if s != 0 or any(sd[2] != 0 for pq in sides for sd in pq):
            raise PdeError("pdsolve: 2D met inhomogene randen of bron niet ondersteund")
    f = ics.get(0)
    if f is None:
        raise PdeError("pdsolve: beginvoorwaarde u(.,0)=f ontbreekt")
    g = ics.get(1)
    if kind == 'heat' and g is not None:
        raise PdeError("pdsolve: warmtevergelijking heeft maar een beginvoorwaarde")
    f = sp.simplify(f - v) if v != 0 else f
    fp = _pieces(f, bases)
    items = []

    def lam_of(modes):
        lam = 0
        for i, (B, m) in enumerate(zip(bases, modes)):
            kk = B.kk(_mode_index(B, m)) if m[0] != 'zero' else sp.Integer(0)
            lam = lam + A[i] * kk ** 2
        return lam

    if kind == 'heat':
        for c, modes in fp:
            lam = lam_of(modes)
            items.append((modes, c * _prod_phi(bases, modes) * sp.exp(sp.Mul(-t, sp.factor_terms(sp.expand(lam - r)), evaluate=False))))
    else:
        gp = _pieces(g, bases) if g is not None else []
        allz = lambda modes: all(m[0] == 'zero' for m in modes)
        cc = _sqrt(A[0])
        iso = all(sp.simplify(A[i] - A[0]) == 0 for i in A)

        def omega(modes):
            if r == 0 and nsp == 1:
                B, m = bases[0], modes[0]
                return cc * B.kk(_mode_index(B, m))
            if iso and r == 0:
                return cc * sp.sqrt(sum(B.kk(_mode_index(B, m)) ** 2 for B, m in zip(bases, modes) if m[0] != 'zero'))
            return sp.sqrt(sp.simplify(lam_of(modes) - r))
        for c, modes in fp:
            if allz(modes) and r == 0:
                items.append((modes, c * _prod_phi(bases, modes)))
            else:
                items.append((modes, c * _prod_phi(bases, modes) * sp.cos(omega(modes) * t)))
        for c, modes in gp:
            if allz(modes):
                if r != 0:
                    raise PdeError("pdsolve: nulmodus van golfvergelijking met term r*u niet ondersteund")
                items.append((modes, c * _prod_phi(bases, modes) * t))
            else:
                w = omega(modes)
                items.append((modes, c * _prod_phi(bases, modes) * sp.sin(w * t) / w))
    body = _assemble(items, bases)
    expr = body if v == 0 else sp.Add(v, body, evaluate=False)
    return sp.Eq(u, expr, evaluate=False)


# ------------------------------------------------------------------ Laplace op rechthoek
def _laplace_rect(u, bcs):
    x, y = u.args
    sidedata = {}
    for i in (0, 1):
        p, q = _side(bcs.get(i, []), u.args[i])
        sidedata[i] = (p, q)
    total = []
    for i in (0, 1):          # i = richting langs de zijde (basis), j = transversaal
        j = 1 - i
        (pa, pb) = sidedata[i]
        B = Basis(u.args[i], pa[0], pb[0], (pa[1], pb[1]), 'n')
        s = u.args[j]
        (qa, qb) = sidedata[j]
        for dat, hom in ((qb, qa), (qa, qb)):
            val = dat[2]
            if val == 0:
                continue
            sgn = 1 if (dat[0] - hom[0]).is_positive is not False else -1
            ss = (s - hom[0]) * sgn
            Hh = sp.simplify(sgn * (dat[0] - hom[0]))
            nd = dat[1]
            h = hom[1]
            pcs = _pieces(val, [B])
            items = []
            for c, (m,) in [(c, mm) for c, mm in pcs]:
                modes = (m,)
                if m[0] == 'zero':
                    if h == 'D':
                        Y = ss / Hh if nd == 'D' else ss
                    else:
                        if nd == 'D':
                            Y = sp.Integer(1)
                        else:
                            raise PdeError("pdsolve: Neumann-probleem zonder oplossing of niet eenduidig (alle randen Neumann)")
                    items.append((modes, c * Y))
                    continue
                k = B.kk(_mode_index(B, m))
                if h == 'D':
                    Yf, Yd = sp.sinh(k * ss), sp.cosh(k * ss) * k
                    YH = sp.sinh(k * Hh)
                    YdH = sp.cosh(k * Hh) * k
                else:
                    Yf, Yd = sp.cosh(k * ss), sp.sinh(k * ss) * k
                    YH = sp.cosh(k * Hh)
                    YdH = sp.sinh(k * Hh) * k
                if nd == 'D':
                    fac = Yf / YH
                else:
                    fac = Yf / YdH * sgn
                items.append((modes, c * B.phi(_mode_index(B, m)) * fac))
            if items:
                total.append(_assemble(items, [B]))
    if not total:
        return sp.Eq(u, sp.Integer(0), evaluate=False)
    return sp.Eq(u, sp.Add(*total, evaluate=False), evaluate=False)


# ------------------------------------------------------------------ schijf / trommel
def _disk_laplace(u, co, bcs):
    r, th = u.args
    R_bcs = bcs.get(0, [])
    if len(R_bcs) != 1:
        raise PdeError("pdsolve: schijf: precies een randvoorwaarde u(R,theta)=f(theta) (of u_r=...) nodig")
    pos, terms, rhs = R_bcs[0]
    (o, c), = [(o, c) for o, c in terms.items() if c != 0]
    if o > 1:
        raise PdeError("pdsolve: schijf: alleen Dirichlet of Neumann op de rand")
    f = sp.simplify(rhs / c)
    R = pos
    cb, sb = PeriodicBasis(th, 'cos', 'n'), PeriodicBasis(th, 'sin', 'n')
    items = []
    for B in (cb, sb):
        for cf, m in _pieces(f, [B]):
            mm = m[0]
            if mm[0] == 'zero':
                if o == 1:
                    if sp.simplify(cf) != 0:
                        raise PdeError("pdsolve: Neumann-probleem op de schijf vereist gemiddelde 0 van de randdata")
                    continue
                items.append(((mm,), cf))
                continue
            n = _mode_index(B, mm)
            fac = (r / R) ** n * (R / n if o == 1 else 1)
            items.append(((mm,), cf * B.phi(n) * fac))
    # 'gen' en 'pt' termen van cos en sin gaan samen in een groep
    body = _assemble(items, [cb])
    if o == 1:
        body = sp.Add(body, sp.Symbol('_C1'), evaluate=False)
    return sp.Eq(u, body, evaluate=False)


def _drum(kind, u, co, rest, bcs, ics):
    r, t = u.args
    kt = (0, 1) if kind == 'heat' else (0, 2)
    T = co[kt]
    A = sp.simplify(-co[(2, 0)] / T)
    R_bcs = bcs.get(0, [])
    if len(R_bcs) != 1:
        raise PdeError("pdsolve: trommel: precies een randvoorwaarde bij r=R nodig")
    pos, terms, rhs = R_bcs[0]
    (o, c), = [(o, c) for o, c in terms.items() if c != 0]
    if rhs != 0 or o > 1:
        raise PdeError("pdsolve: trommel: alleen homogene Dirichlet (u(R,t)=0) of Neumann (u_r(R,t)=0)")
    if sp.simplify(rest) != 0 or co.get((0, 0), 0) != 0:
        raise PdeError("pdsolve: trommel: geen bron- of r*u-term ondersteund")
    B = BesselBasis(r, pos, 'D' if o == 0 else 'N', 'n')
    f = ics.get(0)
    if f is None:
        raise PdeError("pdsolve: beginvoorwaarde u(r,0)=f(r) ontbreekt")
    g = ics.get(1)
    bases = [B]
    items = []
    cc = _sqrt(A)
    if kind == 'heat':
        for cf, modes in _pieces(f, bases):
            k = B.kk(_mode_index(B, modes[0])) if modes[0][0] != 'zero' else 0
            items.append((modes, cf * _phi_for(B, modes[0]) * sp.exp(-A * k ** 2 * t)))
    else:
        for cf, modes in _pieces(f, bases):
            if modes[0][0] == 'zero':
                items.append((modes, cf))
            else:
                k = B.kk(_mode_index(B, modes[0]))
                items.append((modes, cf * _phi_for(B, modes[0]) * sp.cos(cc * k * t)))
        if g is not None:
            for cf, modes in _pieces(g, bases):
                if modes[0][0] == 'zero':
                    items.append((modes, cf * t))
                else:
                    k = B.kk(_mode_index(B, modes[0]))
                    items.append((modes, cf * _phi_for(B, modes[0]) * sp.sin(cc * k * t) / (cc * k)))
    return sp.Eq(u, _assemble(items, bases), evaluate=False)


# ------------------------------------------------------------------ hoofdingang
def solve(eq, u, conds):
    """eq: PDV als expressie (=0), u: u(x,t)/u(x,y,t)/u(x,y), conds: lijst Eq. -> Eq(u, reeks) of None (niet van toepassing)."""
    res = pde_coeffs(eq, u)
    if res is None:
        return None
    co, rest = res
    co = {k: v for k, v in co.items() if v != 0}
    n = len(u.args)
    bcs, ics = {}, {}
    last = n - 1
    parsed = [classify_cond(q, u) for q in conds]
    ztup = (0,) * n

    def has(k):
        return k in co

    def key(**kw):
        o = [0] * n
        for i, c in kw.items():
            o[int(i[1:])] = c
        return tuple(o)
    others = set(co) - {ztup}
    heat = wave = lap = False
    if n == 2 and has((0, 1)) and has((2, 0)) and not has((0, 2)) and not has((1, 1)):
        heat = True
    elif n == 2 and has((0, 2)) and has((2, 0)) and not has((0, 1)) and not has((1, 1)):
        ratio = sp.simplify(co[(2, 0)] / co[(0, 2)])
        if ratio.is_number and ratio.is_positive:
            lap = ratio == 1 and not has((1, 0))
        else:
            wave = True
    elif n == 3 and has((0, 0, 1)) and has((2, 0, 0)) and has((0, 2, 0)) and others <= {(0, 0, 1), (2, 0, 0), (0, 2, 0)}:
        heat = True
    elif n == 3 and has((0, 0, 2)) and has((2, 0, 0)) and has((0, 2, 0)) and others <= {(0, 0, 2), (2, 0, 0), (0, 2, 0)}:
        wave = True
    # radiale vorm: A*(u_rr + u_r/r)
    radial = False
    if n == 2 and has((1, 0)) and has((2, 0)) and (heat or wave or has((0, 2))):
        r_ = u.args[0]
        if sp.simplify(co[(1, 0)] * r_ / co[(2, 0)] - 1) == 0:
            radial = True
    if radial and n == 2 and has((0, 2)) and has((0, 1)):
        return None
    if n == 2 and has((1, 0)) and has((2, 0)) and has((0, 2)) and not has((0, 1)) and not has((1, 1)) \
            and sp.simplify(co[(1, 0)] * u.args[0] / co[(2, 0)] - 1) == 0 \
            and sp.simplify(co[(0, 2)] * u.args[0] ** 2 / co[(2, 0)] - 1) == 0 and rest == 0:
        for pin, pos, terms, rhs in parsed:
            bcs.setdefault(pin, []).append((pos, terms, rhs))
        return _disk_laplace(u, co, bcs)
    if radial:
        heat = has((0, 1)) and not has((0, 2))
        wave = has((0, 2)) and not has((0, 1))
        if not (heat or wave):
            return None
    else:
        if (heat or wave) and has((1, 0)):
            return None
    if not (heat or wave or lap):
        return None
    for pin, pos, terms, rhs in parsed:
        if (heat or wave) and pin == last:
            if sp.simplify(pos) != 0:
                raise PdeError("pdsolve: beginvoorwaarde moet bij t=0 gesteld zijn")
            nz = [o for o, c in terms.items() if c != 0]
            if len(nz) != 1:
                raise PdeError("pdsolve: beginvoorwaarde moet u(.,0) of u_t(.,0) zijn")
            o = nz[0]
            if o > 1:
                raise PdeError("pdsolve: beginvoorwaarde met afgeleide van orde >1 niet ondersteund")
            ics[o] = rhs / terms[o]
        else:
            bcs.setdefault(pin, []).append((pos, terms, rhs))
    if lap:
        return _laplace_rect(u, bcs)
    kind = 'heat' if heat else 'wave'
    if radial:
        return _drum(kind, u, co, rest, bcs, ics)
    return _evolution(kind, co, rest, u, bcs, ics)
