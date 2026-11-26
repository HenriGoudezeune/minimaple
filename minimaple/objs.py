"""Hulpobjecten van de interpreter (procs, composities, D-operator, ranges)."""
import sympy as sp
from .values import Range, Table


class MapleError(Exception):
    """Fout met Maple-achtige melding (zonder 'Error, ' prefix)."""


class RangeB(Range, sp.Basic):
    """Range die ook een sympy-Basic is, zodat sp.Eq(x, a..b) werkt."""
    def __new__(cls, lo, hi):
        obj = sp.Basic.__new__(cls, lo if isinstance(lo, sp.Basic) else sp.Integer(0) if lo is None else sp.sympify(lo),
                               hi if isinstance(hi, sp.Basic) else sp.Integer(0) if hi is None else sp.sympify(hi))
        obj.lo, obj.hi = lo, hi
        return obj

    def __init__(self, lo, hi):
        pass

    def _hashable_content(self):
        return (self.lo, self.hi)

    def __repr__(self):
        return f"{self.lo}..{self.hi}"

    def __eq__(self, other):
        return isinstance(other, Range) and self.lo == other.lo and self.hi == other.hi

    def __hash__(self):
        return hash((self.lo, self.hi))

    @property
    def free_symbols(self):
        s = set()
        for x in (self.lo, self.hi):
            if isinstance(x, sp.Basic):
                s |= x.free_symbols
        return s

    def xreplace(self, rule):
        f = lambda x: x.xreplace(rule) if isinstance(x, sp.Basic) else x
        return RangeB(f(self.lo), f(self.hi))

    def subs(self, *a, **k):
        f = lambda x: x.subs(*a, **k) if isinstance(x, sp.Basic) else x
        return RangeB(f(self.lo), f(self.hi))

    def has(self, *pats):
        return any(isinstance(x, sp.Basic) and x.has(*pats) for x in (self.lo, self.hi))


def _range_sympy(self):
    return RangeB(self.lo, self.hi)


if not hasattr(Range, "_sympy_"):
    Range._sympy_ = _range_sympy


CURRENT = [None]   # laatst actieve interpreter (voor __call__ van procs door andere modules)


class _Callable:
    _interp = None

    def __call__(self, *a):
        it = self._interp or CURRENT[0]
        if it is None:
            raise TypeError("no interpreter")
        import numbers
        a = [sp.sympify(x) if isinstance(x, numbers.Number) and not isinstance(x, sp.Basic) else x for x in a]
        return it.apply(self, a)


class Scope:
    __slots__ = ("vars", "parent", "locals", "globals", "pvals")

    def __init__(self, parent=None, vars=None):
        self.vars = {} if vars is None else vars
        self.parent = parent
        self.locals = set()
        self.globals = set()
        self.pvals = {}


class MProc(_Callable):
    """Maple-procedure of pijlfunctie."""
    def __init__(self, params=(), body=None, closure=None, locals_=(), globals_=(), options=(),
                 name=None, src="", arrow=False, py=None, rettype=None):
        self.params = list(params)      # (naam, type_ast|None, default_ast|None)
        self.body = body                # lijst statements (proc) of expressie (arrow)
        self.closure = closure
        self.locals = set(locals_)
        self.globals = set(globals_)
        self.options = set(options)
        self.name = name
        self.src = src
        self.arrow = arrow
        self.py = py                    # python-callable (ctx, *args) alternatief
        self.memo = {} if "remember" in self.options else None
        self.rettype = rettype

    def __repr__(self):
        return self.src or "proc"


class Composition(_Callable):
    def __init__(self, fs):
        self.fs = list(fs)

    def __repr__(self):
        return "@".join(map(str, self.fs))


class Repeat(_Callable):
    """f@@n"""
    def __init__(self, f, n):
        self.f, self.n = f, n


class DOp(_Callable):
    """D(y) voor een onbekende naam y: D(y)(0) -> Subs(Derivative(y(x),x), x, 0)."""
    def __init__(self, name, order=1):
        self.name, self.order = name, order


class PyFn(_Callable):
    def __init__(self, fn, text="proc() ... end proc"):
        self.fn, self.text = fn, text


class TypeDecl:
    """Resultaat van `a::type` in een uitdrukking."""
    def __init__(self, val, typ, ctx=None):
        self.val, self.typ, self.ctx = val, typ, ctx

    def __bool__(self):
        from .core_fns import check_type
        return bool(check_type(self.ctx, self.val, self.typ))


class Unassigned:
    def __repr__(self):
        return "<unassigned>"


MISSING = Unassigned()


class ReturnEx(BaseException):
    def __init__(self, val):
        self.val = val


class BreakEx(BaseException):
    pass


class NextEx(BaseException):
    pass


def same(a, b):
    try:
        return bool(a == b)
    except Exception:
        return a is b


def mkset(items):
    from .values import MSet
    out = []
    for x in items:
        if not any(same(x, y) for y in out):
            out.append(x)
    if out and all(isinstance(x, sp.Basic) and x.is_number and x.is_real for x in out):
        try:
            out.sort(key=lambda x: float(sp.N(x)))
        except Exception:
            pass
    return MSet(out)
