"""mini-Maple interpreter: evalueert de AST van parser.py."""
import sys
import threading
import functools
import sympy as sp

from .values import (BUILTINS, PACKAGES, Ctx, MList, MSet, Seq, Range, Str, Table, Plot, MImage, split_opts)
from . import objs as _objs
from .objs import (MapleError, RangeB, Scope, MProc, MModule, Composition, Repeat, DOp, PyFn, TypeDecl, MISSING,
                   ReturnEx, BreakEx, NextEx)
from .objs import mkset as _mkset, same as _same_o
from .parser import parse, ParseError
from . import printer

sys.setrecursionlimit(300000)
MAX_DEPTH = 3000

CONSTS = {
    "Pi": sp.pi, "I": sp.I, "infinity": sp.oo, "gamma": sp.EulerGamma, "Catalan": sp.Catalan,
    "true": sp.true, "false": sp.false,
}
KNOWN_PACKAGES = {
    "linearalgebra", "plots", "plottools", "vectorcalculus", "student", "numtheory", "stringtools",
    "imagetools", "mtm", "codegeneration", "combinat", "geometry", "linalg", "inttrans", "orthopoly", "statistics", "polynomials",
    "difftool", "pdetools", "powerseries", "listtools", "arraytools", "type", "typesetting", "sets",
}


def _load_modules():
    for m in ("calc", "linalg", "vecalc", "plots", "imagetools"):
        try:
            __import__(f"minimaple.{m}")
        except ImportError:
            pass
    from . import core_fns
    core_fns.install()


def is_numlit(x):
    return isinstance(x, sp.Basic) and x.is_number and x.is_real


_OPCALL = (MProc, Composition, Repeat)
# builtins die algebraische expressies verwachten: een procedurenaam als argument blijft een naam
_ALGEBRAIC_BUILTINS = {"coeff", "coeffs", "degree", "ldegree", "lcoeff", "tcoeff", "collect", "series", "taylor", "subs",
                       "solve", "fsolve", "isolate", "eliminate", "expand", "simplify", "factor", "normal", "numer",
                       "denom", "indets", "has", "hastype", "algsubs", "combine", "convert", "rhs", "lhs"}
_LASTNAME_OPS = {"+", "-", "*", "/", "^", "=", "<>"}
_VALIDATE_NAMES = {'solve', 'fsolve', 'isolate', 'dsolve', 'pdsolve', 'diff', 'Diff', 'int', 'integrate', 'Int',
                   'limit', 'Limit', 'series', 'taylor'}


class Interpreter(Ctx):
    def __init__(self):
        _load_modules()
        self.reset()
        self._dispatch = {k[3:]: getattr(self, k) for k in dir(self) if k.startswith("ev_")}
        self.special = {
            "seq": self.sf_seq, "add": self.sf_add, "mul": self.sf_mul, "assigned": self.sf_assigned,
            "unassign": self.sf_unassign, "restart": self.sf_restart, "with": self.sf_with,
            "error": self.sf_error, "RETURN": self.sf_return, "Digits": None, "if": self.sf_if,
            "evaln": self.sf_evaln,
        }
        del self.special["Digits"]

    # ------------------------------------------------------------ toestand
    def reset(self):
        self.env = {}
        self.gscope = Scope(vars=self.env)
        self.scope = self.gscope
        self.digits = 10
        self.assumptions = {}
        self.coords = None
        self.plots = []
        self._out = []
        self.history = []
        self.depth = 0
        self._scan_cache = {}
        self._symcache = {}

    # ------------------------------------------------------------ Ctx-API
    def out(self, text):
        self._out.append(str(text))

    def sym(self, name):
        kw = self.assumptions.get(name)
        if not kw:
            return sp.Symbol(name)
        return sp.Symbol(name, **kw)

    def call(self, f, *args):
        return self.apply(f, list(args))

    def assign(self, name, val):
        self.set_var(name, val)

    def get(self, name, default=None):
        v = self.getvar(name)
        return default if v is MISSING else self.full(v)

    # ------------------------------------------------------------ variabelen
    def getvar(self, name):
        s = self.scope
        g = self.gscope
        while s is not None:
            if name in s.vars:
                return s.vars[name]
            if s is not g and name in s.locals:
                return MISSING
            if name in s.globals:
                s = g
                continue
            s = s.parent
        return MISSING

    def set_var(self, name, val):
        s = self.scope
        g = self.gscope
        while s is not None and s is not g:
            if name in s.vars or name in s.locals:
                s.vars[name] = val
                return
            if name in s.globals:
                break
            s = s.parent
        if name == "Digits":
            self.digits = int(val)
            return
        self.env[name] = val

    def del_var(self, name):
        s = self.scope
        g = self.gscope
        while s is not None:
            if name in s.vars:
                del s.vars[name]
                return
            if s is not g and name in s.locals:
                return
            if name in s.globals:
                s = g
                continue
            s = s.parent

    def is_assigned(self, name):
        return self.getvar(name) is not MISSING

    def add_assumptions(self, specs):
        for sp_ in specs:
            name, kw = self._assume_kw(sp_)
            if name:
                cur = dict(self.assumptions.get(name, {}))
                cur.update(kw)
                self.assumptions[name] = cur

    def _assume_kw(self, s):
        if isinstance(s, TypeDecl):
            x = s.val
            t = s.typ.name if isinstance(s.typ, sp.Symbol) else str(s.typ)
            kw = {"real": {"real": True}, "integer": {"integer": True}, "posint": {"integer": True, "positive": True},
                  "natural": {"integer": True, "positive": True}, "nonnegint": {"integer": True, "nonnegative": True},
                  "negint": {"integer": True, "negative": True}, "nonposint": {"integer": True, "nonpositive": True},
                  "rational": {"rational": True}, "positive": {"positive": True}, "negative": {"negative": True},
                  "nonneg": {"nonnegative": True}, "complex": {"complex": True}, "realcons": {"real": True},
                  "numeric": {"complex": True}, "even": {"even": True}, "odd": {"odd": True}, "prime": {"prime": True},
                  "nonzero": {"nonzero": True}}.get(t, {})
            return (x.name if isinstance(x, sp.Symbol) else None), kw
        if isinstance(s, sp.core.relational.Relational):
            l, r = s.lhs, s.rhs
            op = type(s).__name__
            flip = {"StrictGreaterThan": "StrictLessThan", "StrictLessThan": "StrictGreaterThan",
                    "GreaterThan": "LessThan", "LessThan": "GreaterThan"}
            if not isinstance(l, sp.Symbol) and isinstance(r, sp.Symbol):
                l, r, op = r, l, flip.get(op, op)
            if not isinstance(l, sp.Symbol):
                return None, {}
            nonneg = r.is_number and r.is_real and r >= 0
            nonpos = r.is_number and r.is_real and r <= 0
            if op == "StrictGreaterThan":
                return l.name, {"positive": True} if nonneg else {"real": True}
            if op == "GreaterThan":
                return l.name, {"nonnegative": True} if nonneg else {"real": True}
            if op == "StrictLessThan":
                return l.name, {"negative": True} if nonpos else {"real": True}
            if op == "LessThan":
                return l.name, {"nonpositive": True} if nonpos else {"real": True}
            if op == "Unequality":
                return l.name, {"nonzero": True} if r == 0 else {}
            return None, {}
        return None, {}

    # ------------------------------------------------------------ volledige evaluatie
    def _assume_map(self, syms):
        sub = {}
        for s in syms:
            kw = self.assumptions.get(s.name)
            if kw:
                new = sp.Symbol(s.name, **kw)
                if new != s and s == sp.Symbol(s.name):
                    sub[s] = new
        return sub

    def full(self, v, depth=0):
        if depth > 400:
            raise MapleError("too many levels of recursion")
        if isinstance(v, sp.Symbol):
            val = self.getvar(v.name)
            if val is MISSING or (isinstance(val, sp.Symbol) and val.name == v.name):
                if self.assumptions and v.name in self.assumptions and v == sp.Symbol(v.name):
                    return self.sym(v.name)
                return v
            return self.full(val, depth + 1)
        if isinstance(v, (sp.Basic, sp.MatrixBase)):
            if isinstance(v, sp.Basic) and v.is_Atom:
                return v
            syms = v.atoms(sp.Symbol)
            if not syms:
                return v
            sub = {}
            for s in syms:
                val = self.getvar(s.name)
                if val is MISSING or (isinstance(val, sp.Symbol) and val.name == s.name):
                    continue
                sub[s] = self.full(val, depth + 1)
            if self.assumptions:
                for s, n in self._assume_map([s for s in syms if s not in sub]).items():
                    sub[s] = n
            if not sub:
                return v
            try:
                return v.xreplace(sub)
            except Exception:
                return v
        if isinstance(v, (MList, MSet, Seq)):
            new = [self._full_elem(x, depth + 1) for x in v]
            if all(a is b for a, b in zip(new, v)):
                return v
            return type(v)(new)
        return v

    def _full_elem(self, x, depth):
        """Element van een lijst/reeks: namen van procedures/modules/tabellen blijven namen (last-name evaluation)."""
        if isinstance(x, sp.Symbol):
            val = self.getvar(x.name)
            if isinstance(val, (MProc, MModule, Table, Composition, Repeat)):
                return x
        return self.full(x, depth)

    # ------------------------------------------------------------ run
    def run(self, code):
        if threading.current_thread().name == "mm-worker":
            return self._run(code)
        holder = {}

        def target():
            try:
                holder["r"] = self._run(code)
            except BaseException as e:  # noqa
                holder["e"] = e

        old = threading.stack_size()
        try:
            threading.stack_size(512 * 1024 * 1024)
        except Exception:
            pass
        t = threading.Thread(target=target, name="mm-worker", daemon=True)
        t.start()
        try:
            threading.stack_size(old)
        except Exception:
            pass
        t.join()
        if "e" in holder:
            raise holder["e"]
        return holder["r"]

    def _result(self, src, show=True, text="", latex=None, plots=None, error=None):
        return {"stmt": src, "show": show, "text": text, "latex": latex, "plots": plots or [], "error": error}

    def _run(self, code):
        _objs.CURRENT[0] = self
        results = []
        try:
            items = parse(code)
        except ParseError as e:
            return [self._result(code.strip(), True, error=f"Error, {e}")]
        for node, show, src, perr in items:
            if perr is not None:
                results.append(self._result(src, True, error=f"Error, {perr}"))
                continue
            self._out = []
            self.plots = []
            self.scope = self.gscope
            self.depth = 0
            val = None
            err = None
            try:
                val = self.ev(node)
            except MapleError as e:
                err = f"Error, {e}"
            except ReturnEx as e:
                val = e.val
            except (BreakEx, NextEx):
                err = "Error, break or next outside of a loop"
            except RecursionError:
                err = "Error, too many levels of recursion"
            except ZeroDivisionError:
                err = "Error, numeric exception: division by zero"
            except Exception as e:  # noqa
                err = "Error, " + self._pyerr(e)
            self.scope = self.gscope
            outs = "".join(self._out)
            if outs:
                results.append(self._result(src, True, text=outs.rstrip("\n")))
            if err:
                results.append(self._result(src, True, error=err))
                continue
            val = self.norm(val)
            if isinstance(val, Plot) and not any(val is p for p in self.plots):
                self.plots.append(val)
            elif isinstance(val, MImage) and show:
                from .imagetools import image_plot
                self.plots.append(image_plot(val))
            if not (isinstance(val, Seq) and len(val) == 0):
                self.history = [val] + self.history[:2]
            is_null = isinstance(val, Seq) and len(val) == 0
            if is_null and outs:
                continue
            text, latex = "", None
            if show:
                try:
                    text = printer.to_text(val)
                    latex = printer.to_latex(val) if not isinstance(val, Plot) else None
                except Exception as e:  # noqa
                    text = str(val)
            results.append(self._result(src, show, text, latex, list(self.plots)))
        return results

    @staticmethod
    def _pyerr(e):
        msg = str(e)
        if isinstance(e, KeyError):
            return f"unable to find {msg}"
        if isinstance(e, (sp.SympifyError,)):
            return f"invalid input: {msg}"
        return msg or type(e).__name__

    def eval_str(self, code):
        _objs.CURRENT[0] = self
        items = parse(code)
        val = Seq()
        for node, show, src, perr in items:
            if perr is not None:
                raise MapleError(str(perr))
            val = self.norm(self.ev(node))
        return val

    @staticmethod
    def norm(v):
        if v is None:
            return Seq()
        if v is True:
            return sp.true
        if v is False:
            return sp.false
        if isinstance(v, int) and not isinstance(v, bool):
            return sp.Integer(v)
        if isinstance(v, float):
            return sp.Float(v)
        if isinstance(v, Seq) and len(v) == 1:
            return v[0]
        return v

    # ------------------------------------------------------------ evaluatie
    def ev(self, node):
        return self._dispatch[node[0]](node)

    def evs(self, nodes):
        """lijst knopen -> lijst waarden (Seq's afgevlakt, NULL weg)."""
        out = []
        for n in nodes:
            v = self.ev(n)
            if isinstance(v, Seq):
                out.extend(v)
            elif v is not None:
                out.append(v)
        return out

    def block(self, stmts):
        last = Seq()
        for s in stmts:
            last = self.ev(s)
        return last

    def ev_int(self, n):
        return sp.Integer(n[1])

    def ev_float(self, n):
        return sp.Float(n[1], self.digits)

    def ev_str(self, n):
        return Str(n[1])

    def ev_paren(self, n):
        return self.ev(n[1])

    def ev_name(self, n):
        name = n[1]
        v = self.getvar(name)
        if v is MISSING:
            if name == "Digits":
                return sp.Integer(self.digits)
            c = CONSTS.get(name)
            if c is not None:
                return c
            if name == "NULL":
                return Seq()
            if name == "restart":
                return self.sf_restart(())
            return self.sym(name)
        s = self.scope
        while s is not None:
            if name in s.vars:
                if s.pvals.get(name) is v:      # parameterwaarde is al geevalueerd bij de aanroep
                    return v
                break
            s = s.parent
        return self.full(v)

    def ev_ditto(self, n):
        k = n[1]
        if k <= len(self.history):
            return self.history[k - 1]
        return Seq()

    def ev_seq(self, n):
        items = self.evs(n[1])
        if len(items) == 1:
            return items[0]
        return Seq(items)

    def ev_list(self, n):
        return MList(self.evs(n[1]))

    def ev_set(self, n):
        return self.mkset(self.evs(n[1]))

    mkset = staticmethod(_mkset)

    def ev_range(self, n):
        lo = None if n[1] is None else self.ev(n[1])
        hi = None if n[2] is None else self.ev(n[2])
        return RangeB(lo, hi)

    def ev_uneval(self, n):
        e = n[1]
        if e[0] == "name":
            return self.sym(e[1])
        if e[0] == "seq" and not e[1]:
            return Seq()
        return self.ev(e)

    def ev_fact(self, n):
        x = self.ev(n[1])
        if isinstance(x, sp.Integer) and x < 0:
            raise MapleError("numeric exception: division by zero")
        return sp.factorial(x)

    def ev_ditto_(self, n):
        return Seq()

    def ev_mat(self, n):
        items = self.evs(n[2])
        fn = BUILTINS.get("_" + n[1])
        if fn is None:
            raise MapleError("matrix constructors are not available (LinearAlgebra module missing)")
        return fn(self, *items)

    def ev_typeop(self, n):
        return TypeDecl(self.ev(n[1]), self.ev(n[2]), self)

    def ev_concat(self, n):
        l = n[1]
        r = self.ev(n[2])
        if isinstance(r, sp.Basic) and not isinstance(r, sp.Symbol):
            rs = printer.to_text(r)
        else:
            rs = r.name if isinstance(r, sp.Symbol) else str(r)
        if l[0] == "name":
            lv = self.getvar(l[1])
            if lv is MISSING or isinstance(lv, sp.Symbol):
                name = l[1] + rs
                return self.ev(("name", name))
        lv = self.ev(l)
        if isinstance(lv, Str):
            return Str(str(lv) + (str(r) if isinstance(r, Str) else rs))
        if isinstance(lv, sp.Symbol):
            return self.ev(("name", lv.name + rs))
        return Str(printer.to_text(lv) + rs)

    def concat_name(self, node):
        l = node[1]
        r = self.ev(node[2])
        rs = r.name if isinstance(r, sp.Symbol) else printer.to_text(r)
        return l[1] + rs

    def _module_of(self, node):
        """Waarde van de linkerkant van A:-f als die een module is, anders None."""
        try:
            if node[0] == "name":
                v = self.getvar(node[1])
                if v is MISSING:
                    return None
                v = self.full(v) if not isinstance(v, MModule) else v
            else:
                v = self.ev(node)
        except MapleError:
            return None
        return v if isinstance(v, MModule) else None

    def ev_module(self, n):
        info = n[1]
        scope = Scope(parent=self.scope)
        scope.locals = set(info["locals"]) | set(info["exports"])
        scope.globals = set(info["globals"])
        m = MModule(scope, info["exports"], info["locals"], info["options"], info["src"], info["name"])
        saved = self.scope
        self.scope = scope
        try:
            self.block(info["body"])
        except ReturnEx:
            pass
        finally:
            self.scope = saved
        for e in m.exports:
            v = scope.vars.get(e)
            if isinstance(v, MProc) and v.name is None:
                v.name = e
        return m

    def _use_bindings(self, binds):
        out = {}
        for b in binds:
            if b[0] == "bin" and b[1] == "=" and b[2][0] == "name":
                out[b[2][1]] = self.ev(b[3])
                continue
            m = self._module_of(b)
            if m is not None:
                for e in m.exports:
                    if e in m.scope.vars:
                        out[e] = m.scope.vars[e]
                continue
            nm = self._nm(b)
            if nm is not None and (nm in PACKAGES or nm.lower() in KNOWN_PACKAGES):
                continue            # pakketfuncties zijn globaal beschikbaar
            raise MapleError(f"invalid use binding: {printer.to_text(self.ev(b))}")
        return out

    def ev_use(self, n):
        binds = self._use_bindings(n[1])
        if not binds:
            return self.block(n[2])
        scope = Scope(parent=self.scope, vars=dict(binds))
        scope.locals = set()
        saved = self.scope
        self.scope = scope
        try:
            return self.block(n[2])
        finally:
            self.scope = saved

    def ev_elembin(self, n):
        op = n[1]
        a, b = self.ev(n[2]), self.ev(n[3])
        return self.elem_binop(op, a, b)

    def elem_binop(self, op, a, b):
        def f(x, y):
            if op == "and":
                return self.ev(("bin", "and", ("_v", x), ("_v", y)))
            if op == "or":
                return self.ev(("bin", "or", ("_v", x), ("_v", y)))
            if op in ("||",):
                return self.ev(("concat", ("_v", x), ("_v", y)))
            r = self.binop(op, x, y)
            return r
        ca = isinstance(a, (MList, MSet, sp.MatrixBase, Table))
        cb = isinstance(b, (MList, MSet, sp.MatrixBase, Table))
        if ca and cb:
            if isinstance(a, sp.MatrixBase) and isinstance(b, sp.MatrixBase):
                if a.shape != b.shape:
                    raise MapleError("elementwise operation: dimensions of the operands do not match")
                return sp.Matrix(a.rows, a.cols, [f(x, y) for x, y in zip(a, b)])
            la, lb = list(a), list(b)
            if len(la) != len(lb):
                raise MapleError("elementwise operation: containers must have the same number of elements")
            res = [f(x, y) for x, y in zip(la, lb)]
            if isinstance(a, sp.MatrixBase):
                return sp.Matrix(a.rows, a.cols, res)
            return self.mkset(res) if isinstance(a, MSet) else MList(res)
        if ca or cb:
            c = a if ca else b
            g = (lambda x: f(x, b)) if ca else (lambda y: f(a, y))
            if isinstance(c, sp.MatrixBase):
                return sp.Matrix(c.rows, c.cols, [g(x) for x in c])
            res = [g(x) for x in c]
            return self.mkset(res) if isinstance(c, MSet) else MList(res)
        return f(a, b)

    def ev__v(self, n):
        return n[1]

    def ev_modget(self, n):
        f = n[2][1]
        m = self._module_of(n[1])
        if m is not None:
            if f not in m.exports:
                raise MapleError(f"module does not export `{f}`")
            v = m.scope.vars.get(f, MISSING)
            return self.sym(f) if v is MISSING else v
        if f in BUILTINS:
            return self.sym(f)
        v = self.getvar(f)
        if v is not MISSING:
            return self.full(v)
        raise MapleError(f"module member `{f}` not found")

    def ev_elemwise(self, n):
        raise MapleError("invalid use of elementwise operator ~")

    def ev_return(self, n):
        vals = self.evs(n[1])
        raise ReturnEx(vals[0] if len(vals) == 1 else Seq(vals))

    def ev_break(self, n):
        raise BreakEx()

    def ev_next(self, n):
        raise NextEx()

    # ------------------------------------------------------------ operatoren
    def ev_un(self, n):
        op = n[1]
        x = self._ev_operand(n[2]) if op == "-" else self.ev(n[2])
        if op == "-":
            if isinstance(x, (sp.Basic, sp.MatrixBase)):
                return -x
            if isinstance(x, MList):
                raise MapleError("invalid unary minus on a list")
            raise MapleError("invalid operand for unary minus")
        if op == "not":
            t = self.truth(x)
            if t is None:
                return sp.Not(x) if isinstance(x, sp.Basic) else x
            return sp.false if t else sp.true
        raise MapleError(f"unknown unary operator {op}")

    def truth(self, v):
        if v is True or v is sp.true:
            return True
        if v is False or v is sp.false:
            return False
        if isinstance(v, TypeDecl):
            return bool(v)
        if isinstance(v, sp.Equality):
            return self._eq_truth(v.lhs, v.rhs)
        if isinstance(v, sp.Unequality):
            return not self._eq_truth(v.lhs, v.rhs)
        if isinstance(v, sp.core.relational.Relational):
            try:
                r = type(v)(v.lhs, v.rhs)
            except Exception:
                return None
            if r is sp.true:
                return True
            if r is sp.false:
                return False
            try:
                a, b = sp.N(v.lhs), sp.N(v.rhs)
                if a.is_real and b.is_real:
                    return bool(type(v)(a, b))
            except Exception:
                pass
            return None
        if isinstance(v, sp.And):
            ts = [self.truth(a) for a in v.args]
            if any(t is False for t in ts):
                return False
            return True if all(t is True for t in ts) else None
        if isinstance(v, sp.Or):
            ts = [self.truth(a) for a in v.args]
            if any(t is True for t in ts):
                return True
            return False if all(t is False for t in ts) else None
        if isinstance(v, sp.Not):
            t = self.truth(v.args[0])
            return None if t is None else not t
        return None

    def _eq_truth(self, l, r):
        if _same(l, r):
            return True
        if isinstance(l, sp.Basic) and isinstance(r, sp.Basic):
            if l.is_number and r.is_number:
                try:
                    d = l - r
                    z = d.is_zero
                    if z is None:
                        z = abs(sp.N(d, 30)) < sp.Float("1e-25")
                    return bool(z)
                except Exception:
                    return False
            return False
        if isinstance(l, (list, tuple)) and isinstance(r, (list, tuple)):
            return len(l) == len(r) and all(self._eq_truth(a, b) for a, b in zip(l, r))
        return l == r

    def cond(self, v):
        t = self.truth(v)
        if t is None:
            raise MapleError(f"cannot determine if this expression is true or false: {printer.to_text(v)}")
        return t

    def ev_bin(self, n):
        op = n[1]
        if op == "and":
            a = self.ev(n[2])
            ta = self.truth(a)
            if ta is False:
                return sp.false
            b = self.ev(n[3])
            tb = self.truth(b)
            if tb is False:
                return sp.false
            if ta is True and tb is True:
                return sp.true
            if ta is True:
                return b
            if tb is True:
                return a
            return sp.And(a, b)
        if op == "or":
            a = self.ev(n[2])
            ta = self.truth(a)
            if ta is True:
                return sp.true
            b = self.ev(n[3])
            tb = self.truth(b)
            if tb is True:
                return sp.true
            if ta is False and tb is False:
                return sp.false
            if ta is False:
                return b
            if tb is False:
                return a
            return sp.Or(a, b)
        if op in _LASTNAME_OPS:
            a = self._ev_operand(n[2])
            b = self._ev_operand(n[3])
        else:
            a = self.ev(n[2])
            b = self.ev(n[3])
        return self.binop(op, a, b)

    def _evs_lastname(self, nodes):
        out = []
        for n in nodes:
            v = self._ev_operand(n)
            if isinstance(v, Seq):
                out.extend(v)
            elif v is not None:
                out.append(v)
        return out

    def _ev_operand(self, node):
        """Last-name evaluation: een naam die naar een procedure/module/tabel wijst blijft in rekenkundige
        uitdrukkingen een naam (f + g, AA/p, 2*f), zoals in Maple."""
        if node[0] == "name":
            v = self.getvar(node[1])
            if isinstance(v, (MProc, MModule, Table, Composition, Repeat)):
                return sp.Symbol(node[1])
        return self.ev(node)

    def binop(self, op, a, b):
        if op == "=" and (isinstance(a, Seq) or isinstance(b, Seq)):
            return sp.Basic.__new__(sp.Equality, a, b)
        if isinstance(a, Seq) or isinstance(b, Seq):
            if op in "+-*/^" and isinstance(a, Seq) and len(a) == 0 or isinstance(b, Seq) and len(b) == 0:
                raise MapleError("invalid operands: NULL")
            raise MapleError("invalid operands: expression sequence")
        f = getattr(self, "op_" + _OPNAMES.get(op, op), None)
        if f is None:
            raise MapleError(f"unknown operator {op}")
        return f(a, b)

    # rekenkunde -------------------------------------------------
    def _mat(self, x):
        return isinstance(x, sp.MatrixBase)

    def _num(self, x):
        return isinstance(x, sp.Basic)

    def _bad(self, op, a, b):
        if op in ("+", "-", "*", "/") and isinstance(a, _OPCALL) + isinstance(b, _OPCALL) >= 1 and \
                all(isinstance(z, _OPCALL) or self._num(z) for z in (a, b)):
            from .core_fns import arrow_from_expr, _op_names
            fa = a if isinstance(a, _OPCALL) else b
            names = _op_names(fa)
            syms = [sp.Symbol(n) for n in names]
            ea = self.apply(a, list(syms)) if isinstance(a, _OPCALL) else a
            eb = self.apply(b, list(syms)) if isinstance(b, _OPCALL) else b
            return arrow_from_expr(names, {"+": ea + eb, "-": ea - eb, "*": ea * eb, "/": ea / eb}[op])
        raise MapleError(f"invalid operands for {op}: {printer.to_text(a)} and {printer.to_text(b)}")

    def op_add(self, a, b):
        if self._mat(a) or self._mat(b):
            if self._mat(a) and self._mat(b):
                if a.shape != b.shape:
                    raise MapleError("Matrix dimensions mismatch in addition")
                return a + b
            M, s = (a, b) if self._mat(a) else (b, a)
            if self._num(s) and M.is_square:
                return M + s * sp.eye(M.rows)
            return self._bad("+", a, b)
        if self._num(a) and self._num(b):
            return a + b
        if isinstance(a, (MList, MSet)) and isinstance(b, (MList, MSet)):
            raise MapleError("unable to add lists or sets (use zip or map)")
        return self._bad("+", a, b)

    def op_sub(self, a, b):
        if self._mat(a) or self._mat(b):
            if self._mat(a) and self._mat(b):
                if a.shape != b.shape:
                    raise MapleError("Matrix dimensions mismatch in subtraction")
                return a - b
            if self._mat(a) and self._num(b) and a.is_square:
                return a - b * sp.eye(a.rows)
            if self._mat(b) and self._num(a) and b.is_square:
                return a * sp.eye(b.rows) - b
            return self._bad("-", a, b)
        if self._num(a) and self._num(b):
            return a - b
        return self._bad("-", a, b)

    def op_mul(self, a, b):
        if self._mat(a) or self._mat(b):
            if self._mat(a) and self._mat(b):
                if a.cols != b.rows:
                    raise MapleError("Matrix dimension mismatch in multiplication (use . for the matrix product of different shapes)")
                return a * b
            M, s = (a, b) if self._mat(a) else (b, a)
            if self._num(s):
                return M * s
            return self._bad("*", a, b)
        if self._num(a) and self._num(b):
            r = a * b
            if r.is_Mul and r.is_number and r.has(sp.I) and not r.has(sp.Float):
                r = sp.expand(r)
            return r
        return self._bad("*", a, b)

    def op_div(self, a, b):
        if self._mat(a) and self._num(b):
            return a / b
        if self._mat(b) and self._num(a) and b.is_square:
            return a * b.inv()
        if self._num(a) and self._num(b):
            if b == 0:
                raise MapleError("numeric exception: division by zero")
            r = a / b
            if r.is_number and r.has(sp.I) and not r.has(sp.Float) and r.is_algebraic:
                r = sp.expand(sp.radsimp(r))
            return r
        return self._bad("/", a, b)

    def op_pow(self, a, b):
        if self._mat(a) and (isinstance(b, sp.Basic)):
            if not a.is_square:
                raise MapleError("Matrix power requires a square Matrix")
            return a ** b
        if self._num(a) and self._num(b):
            if a == 0 and b.is_number and b.is_real and b < 0:
                raise MapleError("numeric exception: division by zero")
            if a == 0 and b == 0:
                return sp.Integer(1)
            r = a ** b
            if r.is_Pow and r.is_number and a.has(sp.I) and isinstance(b, sp.Integer):
                r = sp.expand(r)
            return r
        return self._bad("^", a, b)

    def op_dot(self, a, b):
        if self._mat(a) and self._mat(b):
            if a.shape[1] == 1 and b.shape[1] == 1 and a.shape[0] == b.shape[0]:
                return sp.expand(sum((sp.conjugate(x) * y for x, y in zip(a, b)), sp.Integer(0)))
            if a.cols != b.rows:
                raise MapleError("Matrix dimension mismatch in multiplication")
            if a.rows == 1 and b.cols == 1:      # rijvector . kolomvector = scalair (zoals in Maple)
                return sp.expand((a * b)[0, 0])
            return a * b
        if self._num(a) and self._num(b):
            return a * b
        if (self._mat(a) and self._num(b)) or (self._mat(b) and self._num(a)):
            return a * b
        return self._bad(".", a, b)

    def op_compose(self, a, b):
        return Composition([a, b])

    def op_repeat(self, a, b):
        return Repeat(a, b)

    def op_mod(self, a, b):
        if isinstance(a, sp.Integer) and isinstance(b, sp.Integer):
            if b == 0:
                raise MapleError("numeric exception: division by zero")
            return sp.Integer(int(a) % int(b))
        if self._num(a) and self._num(b):
            return sp.Mod(a, b)
        return self._bad("mod", a, b)

    def _rel(self, cls, a, b):
        if isinstance(a, Str) and isinstance(b, Str):
            ops = {sp.StrictLessThan: a < b, sp.LessThan: a <= b, sp.StrictGreaterThan: a > b, sp.GreaterThan: a >= b}
            return sp.true if ops[cls] else sp.false
        if not (self._num(a) and self._num(b)):
            return self._bad("<", a, b)
        if a.is_number and b.is_number and a.is_real and b.is_real:
            r = cls(a, b)
            if r is sp.true or r is sp.false:
                return r
        return cls(a, b, evaluate=False)

    def op_lt(self, a, b): return self._rel(sp.StrictLessThan, a, b)
    def op_le(self, a, b): return self._rel(sp.LessThan, a, b)
    def op_gt(self, a, b): return self._rel(sp.StrictGreaterThan, a, b)
    def op_ge(self, a, b): return self._rel(sp.GreaterThan, a, b)

    def op_eq(self, a, b):
        if isinstance(a, sp.Basic) and isinstance(b, sp.Basic):
            return sp.Eq(a, b, evaluate=False)
        e = sp.Basic.__new__(sp.Equality, a, b)
        return e

    def op_ne(self, a, b):
        if isinstance(a, sp.Basic) and isinstance(b, sp.Basic):
            return sp.Ne(a, b, evaluate=False)
        return sp.Basic.__new__(sp.Unequality, a, b)

    def op_in(self, a, b):
        if isinstance(b, (list, tuple)):
            return sp.true if any(self._eq_truth(a, x) for x in b) else sp.false
        if isinstance(b, Range):
            return sp.true if self.truth(sp.And(a >= b.lo, a <= b.hi)) else sp.false
        if isinstance(b, sp.Set):
            return sp.true if a in b else sp.false
        raise MapleError("invalid right-hand side of `in`")

    def op_subset(self, a, b):
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            return sp.true if all(any(_same(x, y) for y in b) for x in a) else sp.false
        return self._bad("subset", a, b)

    def op_union(self, a, b):
        if isinstance(a, (MSet, MList)) and isinstance(b, (MSet, MList)):
            return self.mkset(list(a) + list(b))
        if isinstance(a, sp.Set) and isinstance(b, sp.Set):
            return a | b
        return self._bad("union", a, b)

    def op_minus(self, a, b):
        if isinstance(a, (MSet, MList)) and isinstance(b, (MSet, MList)):
            return self.mkset([x for x in a if not any(_same(x, y) for y in b)])
        if isinstance(a, sp.Set) and isinstance(b, sp.Set):
            return a - b
        return self._bad("minus", a, b)

    def op_intersect(self, a, b):
        if isinstance(a, (MSet, MList)) and isinstance(b, (MSet, MList)):
            return self.mkset([x for x in a if any(_same(x, y) for y in b)])
        if isinstance(a, sp.Set) and isinstance(b, sp.Set):
            return a & b
        return self._bad("intersect", a, b)

    def op_xor(self, a, b):
        ta, tb = self.truth(a), self.truth(b)
        if ta is None or tb is None:
            return sp.Xor(a, b)
        return sp.true if ta != tb else sp.false

    def op_implies(self, a, b):
        ta, tb = self.truth(a), self.truth(b)
        if ta is None or tb is None:
            return sp.Implies(a, b)
        return sp.true if (not ta) or tb else sp.false

    # ------------------------------------------------------------ toewijzing
    def ev_assign(self, n):
        lhs, rhs = n[1], n[2]
        self._nout = len(lhs[1]) if lhs[0] == "seq" else 1
        try:
            val = self.ev(rhs)
        finally:
            self._nout = 1
        self.assign_to(lhs, val)
        return val

    def assign_to(self, lhs, val):
        k = lhs[0]
        if k == "name":
            name = lhs[1]
            self._assign_name(name, val)
        elif k == "paren":
            self.assign_to(lhs[1], val)
        elif k == "concat":
            self._assign_name(self.concat_name(lhs), val)
        elif k == "index":
            self.assign_index(lhs, val)
        elif k == "seq":
            vals = list(val) if isinstance(val, Seq) else [val]
            if len(vals) != len(lhs[1]):
                raise MapleError("number of lvalues and rvalues must match in multiple assignment")
            for t, v in zip(lhs[1], vals):
                self.assign_to(t, v)
        elif k == "call" and lhs[1][0] == "name":
            self.assign_fn(lhs, val)
        elif k == "uneval":
            self.assign_to(lhs[1], val)
        else:
            raise MapleError("invalid left-hand side of assignment")

    def _assign_name(self, name, val):
        if name in CONSTS and name not in ("gamma",):
            raise MapleError(f"attempting to assign to `{name}` which is protected")
        if isinstance(val, sp.Symbol) and val.name == name:
            self.del_var(name)
            return
        if isinstance(val, MProc) and val.name is None:
            val.name = name
        if name == "Digits":
            self.digits = int(val)
            return
        self.set_var(name, val)

    def assign_fn(self, lhs, val):
        # f(x) := expr   ->  f := x -> expr   (alleen met losse namen)
        args = lhs[2]
        if all(a[0] == "name" for a in args):
            names = [a[1] for a in args]
            syms = [self.sym(nm) for nm in names]

            def py(ctx, *a, _v=val, _s=syms):
                if len(a) != len(_s):
                    raise MapleError("wrong number of arguments")
                return _v.subs(dict(zip(_s, a))) if isinstance(_v, sp.Basic) else _v
            self._assign_name(lhs[1][1], MProc(params=[(nm, None, None) for nm in names], py=py, arrow=True,
                                               src=f"({', '.join(names)}) -> {printer.to_text(val)}", name=lhs[1][1]))
            return
        raise MapleError("invalid left-hand side of assignment")

    def assign_index(self, lhs, val):
        base = lhs[1]
        idxs = self.index_args(lhs[2])
        cont = self.raw_value(base)
        new = self.set_item(cont, idxs, val, base)
        if new is not cont or cont is MISSING:
            self.assign_to(base, new)

    def raw_value(self, base):
        if base[0] == "name":
            v = self.getvar(base[1])
            if v is MISSING:
                return MISSING
            return v
        if base[0] == "concat":
            v = self.getvar(self.concat_name(base))
            return v
        if base[0] == "index":
            c = self.raw_value(base[1])
            if c is MISSING:
                raise MapleError("invalid subscript")
            return self.get_item(c, self.index_args(base[2]))
        return self.ev(base)

    def index_args(self, nodes):
        out = []
        for a in nodes:
            v = self.ev(a)
            if isinstance(v, Seq):
                out.extend(v)
            else:
                out.append(v)
        return out

    # ------------------------------------------------------------ indexeren
    @staticmethod
    def _int(x, what="index"):
        if isinstance(x, sp.Integer):
            return int(x)
        if isinstance(x, sp.Basic) and x.is_Integer:
            return int(x)
        raise MapleError(f"invalid subscript selector")

    def _pos(self, i, n):
        i = self._int(i)
        if i < 0:
            i += n + 1
        if i < 1 or i > n:
            raise MapleError("invalid subscript selector")
        return i - 1

    def _rng(self, r, n):
        lo = 1 if r.lo is None else self._int(r.lo)
        hi = n if r.hi is None else self._int(r.hi)
        if lo < 0:
            lo += n + 1
        if hi < 0:
            hi += n + 1
        return lo, hi

    def get_item(self, c, idxs):
        if isinstance(c, Table):
            key = idxs[0] if len(idxs) == 1 else Seq(idxs)
            if key in c:
                return c[key]
            return sp.Indexed(sp.IndexedBase("table"), *idxs) if False else self._unevald_index(c, idxs)
        if isinstance(c, (MList, MSet, Seq, tuple)):
            if len(idxs) != 1:
                raise MapleError("invalid subscript selector")
            i = idxs[0]
            if isinstance(i, Range):
                lo, hi = self._rng(i, len(c))
                if lo < 1 or hi > len(c):
                    if hi < lo:
                        return type(c)([])
                    raise MapleError("invalid subscript selector")
                return type(c)(list(c)[lo - 1:hi])
            return c[self._pos(i, len(c))]
        if isinstance(c, Str):
            i = idxs[0]
            if isinstance(i, Range):
                lo, hi = self._rng(i, len(c))
                return Str(str(c)[lo - 1:hi])
            return Str(str(c)[self._pos(i, len(c))])
        if isinstance(c, sp.MatrixBase):
            r, cc = c.shape
            if len(idxs) == 1:
                if cc == 1 or r == 1:
                    i = idxs[0]
                    n = r * cc
                    if isinstance(i, Range):
                        lo, hi = self._rng(i, n)
                        vals = list(c)[lo - 1:hi]
                        return sp.Matrix(vals) if cc == 1 else sp.Matrix([vals])
                    return c[self._pos(i, n)]
                raise MapleError("invalid subscript selector: Matrix needs two indices")
            if len(idxs) == 2:
                i, j = idxs
                if not isinstance(i, Range) and not isinstance(j, Range):
                    return c[self._pos(i, r), self._pos(j, cc)]
                rows = self._sel(i, r)
                cols = self._sel(j, cc)
                return c.extract(rows, cols)
            raise MapleError("invalid subscript selector")
        if isinstance(c, sp.Basic):
            return sp.Indexed(sp.IndexedBase(printer.to_text(c)), *idxs)
        raise MapleError("invalid subscript selector")

    def _sel(self, i, n):
        if isinstance(i, Range):
            lo, hi = self._rng(i, n)
            if lo < 1 or hi > n or hi < lo:
                raise MapleError("invalid subscript selector")
            return list(range(lo - 1, hi))
        return [self._pos(i, n)]

    def _unevald_index(self, c, idxs):
        return sp.Symbol("table[...]")

    def set_item(self, c, idxs, val, base=None):
        if c is MISSING or (isinstance(c, sp.Symbol) and base is not None and base[0] == "name" and c.name == base[1]):
            c = Table()
            key = idxs[0] if len(idxs) == 1 else Seq(idxs)
            c[key] = val
            return c
        if isinstance(c, Table):
            key = idxs[0] if len(idxs) == 1 else Seq(idxs)
            c[key] = val
            return c
        if isinstance(c, MList):
            i = self._pos(idxs[0], len(c))
            new = MList(c)
            new[i] = val
            return new
        if isinstance(c, sp.MatrixBase):
            r, cc = c.shape
            if len(idxs) == 1:
                c[self._pos(idxs[0], r * cc)] = val
                return c
            if len(idxs) == 2:
                i, j = idxs
                if isinstance(i, Range) or isinstance(j, Range):
                    rows, cols = self._sel(i, r), self._sel(j, cc)
                    for a_, ri in enumerate(rows):
                        for b_, ci in enumerate(cols):
                            c[ri, ci] = val[a_, b_] if isinstance(val, sp.MatrixBase) else val
                    return c
                c[self._pos(i, r), self._pos(j, cc)] = val
                return c
        raise MapleError("invalid assignment target (cannot assign to this indexed object)")

    def ev_index(self, n):
        head = n[1]
        idxs = self.index_args(n[2])
        if head[0] == "name":
            v = self.getvar(head[1])
            if v is MISSING:
                return sp.Indexed(sp.IndexedBase(head[1]), *idxs) if all(isinstance(i, sp.Basic) for i in idxs) \
                    else self._bad_idx()
            c = v
        else:
            c = self.ev(head)
        if isinstance(c, sp.Symbol):
            cc = self.getvar(c.name)
            if cc is MISSING or cc is c:
                return sp.Indexed(sp.IndexedBase(c.name), *idxs)
            c = cc
        if isinstance(c, Table):
            key = idxs[0] if len(idxs) == 1 else Seq(idxs)
            if key not in c:
                nm = head[1] if head[0] == "name" else "table"
                return sp.Indexed(sp.IndexedBase(nm), *idxs)
        return self.get_item(self.full(c) if not isinstance(c, (Table, sp.MatrixBase)) else c, idxs)

    def _bad_idx(self):
        raise MapleError("invalid subscript selector")

    # ------------------------------------------------------------ control flow
    def ev_if(self, n):
        for c, body in n[1]:
            if self.cond(self.ev(c)):
                return self.block(body)
        if n[2] is not None:
            return self.block(n[2])
        return Seq()

    def ev_for(self, n):
        info = n[1]
        var = info["var"]
        body = info["body"]
        wcond = info["cond"]
        if info["inn"] is not None:
            L = self.ev(info["inn"])
            if isinstance(L, sp.MatrixBase):
                L = list(L)
            elif isinstance(L, sp.Basic) and not isinstance(L, Range):
                L = list(L.args) if L.args else [L]
            for x in list(L):
                if var:
                    self.set_var(var, x)
                if wcond is not None and not self.cond(self.ev(wcond)):
                    break
                try:
                    self.block(body)
                except BreakEx:
                    break
                except NextEx:
                    continue
            return Seq()
        frm = self.ev(info["frm"]) if info["frm"] is not None else sp.Integer(1)
        by = self.ev(info["by"]) if info["by"] is not None else sp.Integer(1)
        to = self.ev(info["to"]) if info["to"] is not None else None
        allint = isinstance(frm, sp.Integer) and isinstance(by, sp.Integer) and (to is None or isinstance(to, sp.Integer))
        if by == 0:
            raise MapleError("invalid loop increment")
        if allint:
            i, b = int(frm), int(by)
            t = None if to is None else int(to)
            while True:
                if t is not None and ((b > 0 and i > t) or (b < 0 and i < t)):
                    break
                if var:
                    self.set_var(var, sp.Integer(i))
                if wcond is not None and not self.cond(self.ev(wcond)):
                    break
                try:
                    self.block(body)
                except BreakEx:
                    break
                except NextEx:
                    pass
                i += b
            return Seq()
        i = frm
        pos = self.cond(sp.StrictGreaterThan(by, 0)) if by.is_number else True
        while True:
            if to is not None:
                c = sp.Le(i, to) if pos else sp.Ge(i, to)
                if not self.cond(c):
                    break
            if var:
                self.set_var(var, i)
            if wcond is not None and not self.cond(self.ev(wcond)):
                break
            try:
                self.block(body)
            except BreakEx:
                break
            except NextEx:
                pass
            i = i + by
        return Seq()

    def ev_try(self, n):
        body, catches, fin = n[1], n[2], n[3]
        try:
            try:
                return self.block(body)
            except (MapleError, ZeroDivisionError, TypeError, ValueError, KeyError, ArithmeticError) as e:
                msg = str(e) if isinstance(e, MapleError) else (
                    "numeric exception: division by zero" if isinstance(e, ZeroDivisionError) else self._pyerr(e))
                import re as _re
                bare = _re.sub(r"^(\(in [^)]*\) )+", "", msg)
                where = _re.match(r"^\(in ([^)]*)\)", msg)
                for pats, cb in catches:
                    if not pats or any(bare.startswith(p) or p in msg for p in pats):
                        self._lasterror = msg
                        fmt = getattr(e, "mfmt", None)
                        eargs = getattr(e, "margs", None)
                        if fmt is None:
                            fmt, eargs = bare, []
                        le = Seq([sp.Symbol(where.group(1)) if where else sp.Integer(0), Str(fmt)] + list(eargs))
                        self.env["lastexception"] = le
                        self.env["lasterror"] = Str(bare)
                        self._last_exc = e
                        return self.block(cb)
                raise
        finally:
            if fin is not None:
                self.block(fin)

    def ev_dollar(self, n):
        l, r = n[1], n[2]
        if l is None:
            if r[0] == "range":
                lo, hi = self.ev(r[1]), self.ev(r[2])
                return Seq(self._range_vals(lo, hi))
            raise MapleError("invalid $ operand")
        if r[0] == "bin" and r[1] == "=" and r[2][0] == "name":
            return self._iterate(l, r, lambda xs: Seq(xs))
        k = self.ev(r)
        if not isinstance(k, sp.Integer) or k < 0:
            raise MapleError("invalid arguments to $")
        v = self.ev(l)
        return Seq([v] * int(k))

    def ev_assuming(self, n):
        c = self.ev(n[2])
        specs = []
        for x in (c if isinstance(c, (list, tuple)) else [c]):
            if isinstance(x, (list, tuple)):
                specs.extend(x)
            else:
                specs.append(x)
        saved = {k: dict(v) for k, v in self.assumptions.items()}
        try:
            self.add_assumptions(specs)
            r = self.ev(n[1])
            if any(kw.get("integer") for kw in self.assumptions.values()):
                from .calc import integer_exp_fix
                r = integer_exp_fix(r)
            return r
        finally:
            self.assumptions = saved

    # ------------------------------------------------------------ procs
    def ev_arrow(self, n):
        params = n[1]
        return MProc(params=params, body=n[2], closure=self.scope, src=n[3], arrow=True)

    def _assigned_names(self, body, key):
        r = self._scan_cache.get(key)
        if r is not None:
            return r
        out = set()

        def walk(x):
            if isinstance(x, tuple):
                if x and x[0] in ("proc", "arrow", "module"):
                    return
                if x and x[0] == "assign":
                    t = x[1]
                    while t[0] == "paren":
                        t = t[1]
                    if t[0] == "name":
                        out.add(t[1])
                    elif t[0] == "seq":
                        for q in t[1]:
                            if q[0] == "name":
                                out.add(q[1])
                if x and x[0] == "for" and isinstance(x[1], dict) and x[1]["var"]:
                    out.add(x[1]["var"])
                for y in x:
                    walk(y)
            elif isinstance(x, list):
                for y in x:
                    walk(y)
            elif isinstance(x, dict):
                for y in x.values():
                    walk(y)
        walk(body)
        self._scan_cache[key] = out
        return out

    def ev_proc(self, n):
        info = n[1]
        p = MProc(params=info["params"], body=info["body"], closure=self.scope, locals_=info["locals"],
                  globals_=info["globals"], options=info["options"], src=info["src"], rettype=info["rettype"],
                  kwparams=info.get("kwparams", ()), dollar=info.get("dollar", False))
        declared = {q[0] for q in p.params} | {q[0] for q in p.kwparams} | p.locals | p.globals
        assigned = self._assigned_names(info["body"], id(info))
        enclosing = set()
        s = self.scope
        while s is not None and s is not self.gscope:
            enclosing |= set(s.vars) | s.locals
            s = s.parent
        p.locals |= {a for a in assigned if a not in declared and a not in enclosing}
        return p

    def call_proc(self, p, args):
        if p.py is not None:
            return p.py(self, *args)
        if p.memo is not None:
            try:
                key = tuple(args)
                hash(key)
            except TypeError:
                key = None
            if key is not None and key in p.memo:
                return p.memo[key]
        else:
            key = None
        if self.depth > MAX_DEPTH:
            raise MapleError(f"(in {p.name or 'anonymous procedure'}) too many levels of recursion")
        scope = Scope(parent=p.closure)
        scope.locals = set(p.locals)
        scope.globals = set(p.globals)
        saved = self.scope
        self.scope = scope
        self.depth += 1
        try:
            self._bind_params(p, scope, args)
            if p.arrow:
                res = self.ev(p.body)
            else:
                try:
                    res = self.block(p.body)
                except ReturnEx as r:
                    res = r.val
        except MapleError as e:
            msg = str(e)
            if p.name and not msg.startswith("(in "):
                ne = MapleError(f"(in {p.name}) {msg}")
                ne.mfmt, ne.margs = getattr(e, "mfmt", None), getattr(e, "margs", None)
                raise ne from None
            raise
        finally:
            self.scope = saved
            self.depth -= 1
        if key is not None and p.memo is not None:
            p.memo[key] = res
        return res

    def _bind_params(self, p, scope, args):
        from .core_fns import check_type
        scope.vars["args"] = Seq(args)
        scope.vars["nargs"] = sp.Integer(len(args))
        scope.vars["_passed"] = Seq(args)
        scope.vars["_npassed"] = sp.Integer(len(args))
        scope.vars["procname"] = sp.Symbol(p.name) if p.name else p
        pname_ = p.name or "procedure"
        # keyword-parameters {k := v} halen we eerst uit de argumenten (waar ze ook staan)
        kwnames = {k[0]: k for k in p.kwparams}
        if kwnames:
            rest = []
            for a in args:
                key = None
                if isinstance(a, sp.Equality) or type(a).__name__ == "Equality":
                    l = a.args[0]
                    if isinstance(l, sp.Symbol) and l.name in kwnames:
                        key, val = l.name, a.args[1]
                    elif isinstance(l, Str) and str(l) in kwnames:
                        key, val = str(l), a.args[1]
                elif isinstance(a, sp.Symbol) and a.name in kwnames:
                    key, val = a.name, sp.true        # `opt` als afkorting van opt = true
                if key is None:
                    rest.append(a)
                    continue
                typ = kwnames[key][1]
                if typ is not None and not check_type(self, val, self.ev(typ)):
                    raise MapleError(f"invalid input: {pname_} expects value for keyword parameter {key} to be of type "
                                     f"{printer.to_text(self.ev(typ))}, but received {printer.to_text(val)}")
                scope.vars[key] = val
            args = rest
            for k, typ, dflt in p.kwparams:
                if k not in scope.vars:
                    if dflt is not None:
                        scope.vars[k] = self.ev(dflt)
            scope.vars["_options"] = Seq([sp.Eq(sp.Symbol(k), scope.vars[k], evaluate=False)
                                         for k, _, _ in p.kwparams if k in scope.vars and
                                         isinstance(scope.vars[k], sp.Basic)])
        ai = 0
        for i, (pname, typ, dflt) in enumerate(p.params):
            if ai < len(args):
                val = args[ai]
                if typ is not None:
                    tv = self.ev(typ)
                    if not check_type(self, val, tv):
                        if dflt is not None:      # optioneel geordend parameter: default nemen, arg doorschuiven
                            scope.vars[pname] = self.ev(dflt)
                            continue
                        ordn = {1: "1st", 2: "2nd", 3: "3rd"}.get(i + 1, f"{i + 1}th")
                        raise MapleError(f"invalid input: {pname_} expects its {ordn} argument, "
                                         f"{pname}, to be of type {printer.to_text(tv)}, but received {printer.to_text(val)}")
                scope.vars[pname] = val
                scope.pvals[pname] = val
                ai += 1
            elif dflt is not None:
                scope.vars[pname] = self.ev(dflt)
        extra = list(args[ai:])
        if p.dollar and extra:
            raise MapleError(f"invalid input: too many and/or wrong type of arguments passed to {pname_}; "
                             f"first unused argument is {printer.to_text(extra[0])}")
        scope.vars["_rest"] = Seq(extra)
        scope.vars["_nrest"] = sp.Integer(len(extra))

    # ------------------------------------------------------------ aanroepen
    def eval_args(self, nodes):
        return self.evs(nodes)

    def ev_call(self, n):
        head, argn = n[1], n[2]
        k = head[0]
        if k == "paren":
            head = head[1]
            k = head[0]
        if k == "name":
            nm = head[1]
            raw = self.getvar(nm)
            if raw is MISSING:
                sf = self.special.get(nm)
                if sf is not None:
                    return sf(argn)
                if nm in _ALGEBRAIC_BUILTINS:
                    return self.call_name(nm, self._evs_lastname(argn))
                return self.call_name(nm, self.evs(argn))
            f = self.full(raw)
            return self.apply(f, self.evs(argn), nm)
        if k == "index":
            return self.call_indexed(head, argn)
        if k == "modget":
            f = head[2][1]
            m = self._module_of(head[1])
            if m is not None:
                if f not in m.exports:
                    raise MapleError(f"module does not export `{f}`")
                v = m.scope.vars.get(f, MISSING)
                args = self.evs(argn)
                if v is MISSING:
                    return self.undef_call(f, args)
                return self.apply(v, args, f)
            args = self.evs(argn)
            if f in BUILTINS:
                return self.call_name(f, args)
            v = self.getvar(f)
            if v is not MISSING:
                return self.apply(self.full(v), args, f)
            raise MapleError(f"module member `{f}` not found")
        if k == "elemwise":
            f = self.ev(head[1])
            return self.elemwise(f, self.evs(argn))
        if k == "uneval" and head[1][0] == "name":
            nm = head[1][1]                       # 'f'(x): aanroep uitgesteld -> onge-evalueerde f(x)
            if nm == "procname":
                pn = self.getvar("procname")
                nm = pn.name if isinstance(pn, sp.Symbol) else nm
            return self.undef_call(nm, self.evs(argn))
        f = self.ev(head)
        return self.apply(f, self.evs(argn))

    def call_indexed(self, head, argn):
        base = head[1]
        if base[0] == "name" and self.getvar(base[1]) is MISSING:
            nm = base[1]
            if nm == "evalf" and len(head[2]) == 1:
                d = self.ev(head[2][0])
                args = self.evs(argn)
                old = self.digits
                self.digits = int(d)
                try:
                    return self.call_name("evalf", args)
                finally:
                    self.digits = old
            idx = self.index_args(head[2])
            key = f"{nm}[{', '.join(printer.to_text(i) for i in idx)}]"
            if key in BUILTINS:
                return self.call_name(key, self.evs(argn))
            if len(idx) == 1 and isinstance(idx[0], sp.Symbol) and (nm.lower() in KNOWN_PACKAGES or nm in PACKAGES):
                f = idx[0].name
                if f in BUILTINS:
                    return self.call_name(f, self.evs(argn))
            if nm == "log" and len(idx) == 1:
                a = self.evs(argn)
                return sp.log(a[0], idx[0])
            if nm in BUILTINS and nm in ("D", "map", "diff"):
                return self.call_name(nm, self.evs(argn), extra=idx)
            if nm in BUILTINS:
                return self.call_name(nm, self.evs(argn), extra=idx)
        f = self.ev(head)
        return self.apply(f, self.evs(argn))

    def call_name(self, nm, args, extra=None):
        fn = BUILTINS.get(nm)
        if fn is None:
            return self.undef_call(nm, args)
        return self.call_builtin(nm, fn, args, extra)

    def call_builtin(self, nm, fn, args, extra=None):
        if nm in _VALIDATE_NAMES:
            from .calc import validate_args
            try:
                validate_args(nm, args)
            except ValueError as e:
                raise MapleError(str(e)) from None
        self._index_ctx = extra
        try:
            return fn(self, *args)
        except (MapleError, ReturnEx, BreakEx, NextEx):
            raise
        except ZeroDivisionError:
            raise MapleError("numeric exception: division by zero")
        except RecursionError:
            raise
        except TypeError as e:
            msg = str(e)
            if "positional argument" in msg or "required" in msg:
                raise MapleError(f"invalid input: {nm} called with arguments {', '.join(printer.to_text(a) for a in args)}") from None
            raise MapleError(f"(in {nm}) {msg}") from None
        except (ValueError, NotImplementedError, AttributeError, KeyError, IndexError, sp.SympifyError) as e:
            raise MapleError(f"(in {nm}) {self._pyerr(e)}") from None
        finally:
            self._index_ctx = None

    def undef_call(self, nm, args):
        try:
            return sp.Function(nm)(*[self._fnarg(a) for a in args])
        except Exception:
            raise MapleError(f"invalid arguments to {nm}") from None

    @staticmethod
    def _fnarg(a):
        if isinstance(a, (list, tuple)):
            return sp.Tuple(*a)
        if isinstance(a, sp.MatrixBase):
            return sp.ImmutableDenseMatrix(a)
        if isinstance(a, Str):
            return sp.Symbol(str(a))
        return a

    def apply(self, f, args, name=None):
        if isinstance(f, MProc):
            return self.call_proc(f, args)
        if isinstance(f, sp.Symbol):
            v = self.getvar(f.name)
            if v is not MISSING and not (isinstance(v, sp.Symbol) and v.name == f.name):
                v = self.full(v)
                if not (isinstance(v, sp.Symbol) and v.name == f.name):
                    return self.apply(v, args, f.name)
            return self.call_name(f.name, args)
        if isinstance(f, MModule):
            ma = f.scope.vars.get("ModuleApply")
            if ma is None:
                raise MapleError("attempting to call a module without a ModuleApply")
            return self.apply(ma, args)
        if isinstance(f, Composition):
            fs = f.fs
            res = self.apply(fs[-1], args)
            for g in reversed(fs[:-1]):
                res = self.apply(g, list(res) if isinstance(res, Seq) else [res])
            return res
        if isinstance(f, Repeat):
            k = int(f.n)
            res = args
            for _ in range(k):
                v = self.apply(f.f, list(res))
                res = list(v) if isinstance(v, Seq) else [v]
            return res[0] if len(res) == 1 else Seq(res)
        if isinstance(f, DOp):
            x = self.sym("x")
            fn = sp.Function(f.name)(x)
            return sp.Subs(sp.Derivative(fn, (x, f.order)), x, args[0])
        if isinstance(f, PyFn):
            return f.fn(self, *args)
        if isinstance(f, sp.Indexed):
            return sp.Function(printer.to_text(f))(*args)
        if isinstance(f, sp.core.function.UndefinedFunction) or (isinstance(f, type) and issubclass(f, sp.Function)):
            return f(*args)
        if isinstance(f, sp.Basic) and not isinstance(f, (sp.core.relational.Relational, sp.logic.boolalg.Boolean)):
            if f.is_number:
                return f                          # 2(x) = 2
            if isinstance(f, (sp.Add, sp.Mul, sp.Pow)):
                # operatoralgebra: (f+g)(x) = f(x)+g(x), (2*f)(x) = 2*f(x), (f^2)(x) = f(x)^2
                sub = {}
                for s_ in f.free_symbols:
                    r = self.apply(s_, list(args))
                    if not isinstance(r, sp.Basic):
                        raise MapleError(f"attempting to call a non-procedure: {printer.to_text(f)}")
                    sub[s_] = r
                return f.xreplace(sub)
            raise MapleError(f"attempting to call a non-procedure: {printer.to_text(f)}")
        if isinstance(f, sp.Basic):
            raise MapleError(f"attempting to call a non-procedure: {printer.to_text(f)}")
        raise MapleError("invalid function call")

    def elemwise(self, f, args):
        cont = None
        for a in args:
            if isinstance(a, (MList, MSet, sp.MatrixBase)):
                cont = a
                break
        if cont is None:
            return self.apply(f, args)

        def one(x):
            return self.apply(f, [x if a is cont else a for a in args] if False else
                              [x if a is cont else a for a in args])
        if isinstance(cont, sp.MatrixBase):
            return cont.applyfunc(one)
        res = [one(x) for x in cont]
        return self.mkset(res) if isinstance(cont, MSet) else MList(res)

    # ------------------------------------------------------------ special forms
    def _range_vals(self, lo, hi):
        if isinstance(lo, sp.Integer) and isinstance(hi, sp.Integer):
            return [sp.Integer(i) for i in range(int(lo), int(hi) + 1)]
        if not (isinstance(lo, sp.Basic) and isinstance(hi, sp.Basic) and lo.is_number and hi.is_number):
            raise MapleError("non-numeric range in sequence")
        out = []
        i = lo
        while self.truth(sp.Le(i, hi, evaluate=False)):
            out.append(i)
            i = i + 1
        return out

    def _iterate(self, body, spec, combine):
        """spec: ('bin','=',('name',v),range|lijst) of ('bin','in',('name',v),lijst)."""
        if spec[0] != "bin" or spec[1] not in ("=", "in") or spec[2][0] != "name":
            raise MapleError("invalid arguments: second argument must be of the form i=a..b or i in L")
        var = spec[2][1]
        src = spec[3]
        if src[0] == "range" and spec[1] == "=":
            vals = self._range_vals(self.ev(src[1]), self.ev(src[2]))
        else:
            L = self.ev(src)
            if isinstance(L, Range):
                vals = self._range_vals(L.lo, L.hi)
            elif isinstance(L, (list, tuple)):
                vals = list(L)
            elif isinstance(L, sp.MatrixBase):
                vals = list(L)
            elif isinstance(L, sp.Basic) and spec[1] == "in":
                vals = list(L.args) if L.args else [L]
            else:
                vals = [L]
        old = self.getvar(var)
        out = []
        try:
            for v in vals:
                self.set_var(var, v)
                r = self.ev(body)
                if isinstance(r, Seq):
                    out.extend(r)
                else:
                    out.append(r)
        finally:
            if old is MISSING:
                self.del_var(var)
            else:
                self.set_var(var, old)
        return combine(out)

    def _spec_args(self, argn, what):
        if len(argn) < 2:
            if what == "seq" and len(argn) == 1:
                return None
            raise MapleError(f"invalid arguments to {what}")
        return argn[0], argn[1]

    def sf_seq(self, argn):
        sa = self._spec_args(argn, "seq")
        if sa is None:
            return self.ev(argn[0])
        return self._iterate(sa[0], sa[1], lambda xs: Seq(xs))

    def sf_add(self, argn):
        sa = self._spec_args(argn, "add")
        return self._iterate(sa[0], sa[1], lambda xs: functools.reduce(self.op_add, xs) if xs else sp.Integer(0))

    def sf_mul(self, argn):
        sa = self._spec_args(argn, "mul")
        return self._iterate(sa[0], sa[1], lambda xs: functools.reduce(self.op_mul, xs) if xs else sp.Integer(1))

    @staticmethod
    def _nm(node):
        while node[0] in ("uneval", "paren"):
            node = node[1]
        return node[1] if node[0] == "name" else None

    def sf_assigned(self, argn):
        names = [self._nm(a) for a in argn]
        if not names or None in names:
            raise MapleError("invalid arguments to assigned")
        return sp.true if all(self.is_assigned(nm) for nm in names) else sp.false

    def sf_unassign(self, argn):
        for a in argn:
            nm = self._nm(a)
            if nm is None:
                v = self.ev(a)
                nm = v.name if isinstance(v, sp.Symbol) else None
            if nm is None:
                raise MapleError("invalid arguments to unassign")
            self.del_var(nm)
            self.assumptions.pop(nm, None)
        return Seq()

    def sf_restart(self, argn):
        self.reset()
        return Seq()

    def sf_with(self, argn):
        names = []
        for a in argn:
            nm = self._nm(a)
            if nm is None and a[0] == "index":
                nm = self._nm(a[1])
            if nm:
                names.append(nm)
        out = []
        for a in argn:
            m = self._module_of(a)
            if m is not None:
                for e in m.exports:
                    if e in m.scope.vars:
                        self.env[e] = m.scope.vars[e]
                    out.append(self.sym(e))
                names = [x for x in names if x != self._nm(a)]
        for nm in names:
            out.extend(self.sym(x) for x in PACKAGES.get(nm, []))
        return MList(out)

    def sf_if(self, argn):
        """`if`(c, a, b): lui in a en b."""
        if len(argn) != 3:
            raise MapleError("invalid input: `if` expects 3 arguments")
        return self.ev(argn[1]) if self.cond(self.ev(argn[0])) else self.ev(argn[2])

    def sf_evaln(self, argn):
        if len(argn) != 1:
            raise MapleError("invalid input: evaln expects 1 argument")
        a = argn[0]
        while a[0] in ("uneval", "paren"):
            a = a[1]
        if a[0] == "name":
            return sp.Symbol(a[1])
        if a[0] == "concat":
            return sp.Symbol(self.concat_name(a))
        if a[0] == "index" and a[1][0] == "name":
            return sp.Indexed(sp.IndexedBase(a[1][1]), *self.index_args(a[2]))
        raise MapleError("illegal use of an object as a name")

    def sf_error(self, argn):
        args = self.evs(argn)
        if not args:
            e = getattr(self, "_last_exc", None)
            if e is not None:
                raise e                                  # `error;` in een catch: opnieuw opwerpen
        err = MapleError(self.format_msg(args))
        if args and isinstance(args[0], Str):
            err.mfmt, err.margs = str(args[0]), list(args[1:])
        raise err

    def sf_return(self, argn):
        vals = self.evs(argn)
        raise ReturnEx(vals[0] if len(vals) == 1 else Seq(vals))

    def format_msg(self, args):
        if not args:
            return "error"
        fmt = args[0]
        if not isinstance(fmt, str):
            return printer.to_text(fmt)
        s = str(fmt)
        import re

        def rep(m):
            i = int(m.group(1))
            if i <= len(args) - 1:
                v = args[i]
                return str(v) if isinstance(v, str) and not isinstance(v, Str) else (str(v) if isinstance(v, Str) else printer.to_text(v))
            return m.group(0)
        s = re.sub(r"%(\d+)", rep, s)
        s = re.sub(r"_rest|%\*", " " + ", ".join(printer.to_text(a) for a in args[1:]), s) if "%*" in s else s
        if "%" not in fmt and len(args) > 1:
            s += ", " + ", ".join(printer.to_text(a) if not isinstance(a, Str) else str(a) for a in args[1:])
        return s


_same = _same_o


_OPNAMES = {"+": "add", "-": "sub", "*": "mul", "/": "div", "^": "pow", ".": "dot", "@": "compose",
            "@@": "repeat", "<": "lt", "<=": "le", ">": "gt", ">=": "ge", "=": "eq", "<>": "ne"}
