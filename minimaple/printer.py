"""Uitvoer: to_text (Maple-stijl, 1D) en to_latex."""
import re
import mpmath
import sympy as sp
from sympy.printing.str import StrPrinter
from .values import MList, MSet, Seq, Range, Str, Table, Plot
from .objs import MProc, Composition, Repeat, DOp, PyFn, TypeDecl

RENAME = {
    "log": "ln", "asin": "arcsin", "acos": "arccos", "atan": "arctan", "acot": "arccot", "asec": "arcsec",
    "acsc": "arccsc", "asinh": "arcsinh", "acosh": "arccosh", "atanh": "arctanh", "acoth": "arccoth",
    "asech": "arcsech", "acsch": "arccsch", "DiracDelta": "Dirac", "sign": "signum", "gamma": "GAMMA",
    "besselj": "BesselJ", "bessely": "BesselY", "besseli": "BesselI", "besselk": "BesselK",
    "legendre": "LegendreP", "hermite": "HermiteH", "laguerre": "LaguerreL", "chebyshevt": "ChebyshevT",
    "chebyshevu": "ChebyshevU", "zeta": "Zeta", "Max": "max", "Min": "min", "ceiling": "ceil", "re": "Re",
    "im": "Im", "arg": "argument", "airyai": "AiryAi", "airybi": "AiryBi", "lowergamma": "GAMMA",
    "polygamma": "Psi", "loggamma": "lnGAMMA", "Abs": "abs", "Ei": "Ei", "Si": "Si", "Ci": "Ci",
    "uppergamma": "GAMMA", "beta": "Beta", "Mod": "modp", "LaplaceTransform": "laplace",
    "InverseLaplaceTransform": "invlaplace", "FourierTransform": "fourier", "InverseFourierTransform": "invfourier",
    "SineTransform": "fouriersin", "CosineTransform": "fouriercos",
}


def fmt_float(e):
    prec = getattr(e, "_prec", 53)
    dps = mpmath.libmp.prec_to_dps(prec)
    if e == 0:
        return "0."
    s = mpmath.libmp.to_str(e._mpf_, dps, strip_zeros=True, min_fixed=-5, max_fixed=dps + 3)
    if "e" in s:
        m, ex = s.split("e")
        ex = int(ex)
        if m.endswith(".0"):
            m = m[:-2] + "."
        return f"{m}*10^{ex}" if ex >= 0 else f"{m}*10^({ex})"
    if "." in s:
        s = s.rstrip("0") if s.rstrip("0") != s else s
        if s.endswith("."):
            pass
    if s.endswith(".0"):
        s = s[:-1]
    if s.startswith("0.") is False and s.startswith("-0.") is False and s.startswith("."):
        s = "0" + s
    return s


class MapleStr(StrPrinter):
    def __init__(self, settings=None):
        super().__init__(settings or {"order": None})

    def emptyPrinter(self, e):
        if isinstance(e, (MList, MSet, Seq, Str, Range, Table, MProc, Composition, Repeat, DOp, PyFn, TypeDecl, Plot)):
            return obj_text(e, self)
        if isinstance(e, bool):
            return "true" if e else "false"
        return super().emptyPrinter(e)

    # containers
    def _print_MList(self, e): return "[" + ", ".join(self._print(x) for x in e) + "]"
    def _print_MSet(self, e): return "{" + ", ".join(self._print(x) for x in e) + "}"
    def _print_Seq(self, e): return ", ".join(self._print(x) for x in e)
    def _print_Str(self, e): return '"' + str(e).replace("\\", "\\\\").replace('"', '\\"') + '"'
    def _print_str(self, e): return str(e)
    def _print_Range(self, e): return obj_text(e, self)
    def _print_RangeB(self, e): return obj_text(e, self)
    def _print_Table(self, e): return obj_text(e, self)
    def _print_list(self, e): return "[" + ", ".join(self._print(x) for x in e) + "]"
    def _print_tuple(self, e): return ", ".join(self._print(x) for x in e)
    def _print_dict(self, e): return "table([" + ", ".join(f"{self._print(k)} = {self._print(v)}" for k, v in e.items()) + "])"

    # getallen en constanten
    def _print_Float(self, e, *a): return fmt_float(e)
    def _print_Order(self, e): return "O(" + self._print(e.args[0]) + ")"

    def _print_Add(self, expr, order=None):
        # een O(...)-term (na subs in een reeks) achteraan, zoals Maple
        isO = lambda a: isinstance(a, sp.Function) and getattr(a.func, "__name__", "") == "O"
        if any(isO(a) for a in expr.args):
            rest = [a for a in expr.args if not isO(a)]
            os_ = [a for a in expr.args if isO(a)]
            txt = self._print(sp.Add(*rest)) if rest else ""
            return " + ".join(([txt] if txt else []) + [self._print(o) for o in os_])
        return super()._print_Add(expr, order)
    def _print_Pi(self, e): return "Pi"
    def _print_Exp1(self, e): return "exp(1)"
    def _print_EulerGamma(self, e): return "gamma"
    def _print_Catalan(self, e): return "Catalan"
    def _print_Infinity(self, e): return "infinity"
    def _print_NegativeInfinity(self, e): return "-infinity"
    def _print_ComplexInfinity(self, e): return "infinity"
    def _print_ImaginaryUnit(self, e): return "I"
    def _print_NaN(self, e): return "undefined"
    def _print_BooleanTrue(self, e): return "true"
    def _print_BooleanFalse(self, e): return "false"
    def _print_GoldenRatio(self, e): return "(1+sqrt(5))/2"

    def _print_Pow(self, e, rational=False):
        b, ex = e.as_base_exp()
        if ex == sp.S.Half:
            return f"sqrt({self._print(b)})"
        if ex == -sp.S.Half:
            return f"1/sqrt({self._print(b)})"
        if ex.is_number and ex.is_negative and not ex.is_Float:
            inner = self._print(sp.Pow(b, -ex))
            if re.fullmatch(r"(\w+|\([^()]*\))(\^(\w+|\([^()]*\)))?", inner):
                return "1/" + inner
            return "1/(" + inner + ")"
        return super()._print_Pow(e, rational).replace("**", "^")

    def _print_Function(self, e):
        name = type(e).__name__ if not hasattr(e.func, "__name__") else e.func.__name__
        name = RENAME.get(name, name)
        if name == "Dirac" and len(e.args) == 2:
            return f"Dirac({self._print(e.args[1])}, {self._print(e.args[0])})"
        if name.startswith("&") and len(name) > 1 and len(e.args) == 2:      # neutrale operator a &+ b
            return f"{self.parenthesize(e.args[0], 60)} {name} {self.parenthesize(e.args[1], 60)}"
        if not re.fullmatch(r"[A-Za-z_~][A-Za-z0-9_~]*", name):
            name = "`" + name + "`"
        return name + "(" + ", ".join(self._print(a) for a in e.args) + ")"

    def _print_Abs(self, e): return "abs(" + self._print(e.args[0]) + ")"
    def _print_atan2(self, e): return f"arctan({self._print(e.args[0])}, {self._print(e.args[1])})"
    def _print_exp(self, e): return "exp(" + self._print(e.args[0]) + ")"
    def _print_factorial(self, e):
        a = e.args[0]
        s = self._print(a)
        return s + "!" if (a.is_Atom and not s.startswith("-")) else "(" + s + ")!"
    def _print_Equality(self, e): return f"{self._print(e.lhs)} = {self._print(e.rhs)}"
    def _print_Unequality(self, e): return f"{self._print(e.lhs)} <> {self._print(e.rhs)}"
    def _print_And(self, e): return " and ".join(self._pb(a) for a in e.args)
    def _print_Or(self, e): return " or ".join(self._pb(a) for a in e.args)
    def _print_Not(self, e): return "not " + self._pb(e.args[0])
    def _pb(self, a):
        s = self._print(a)
        return f"({s})" if isinstance(a, (sp.And, sp.Or)) else s

    def _print_Piecewise(self, e):
        parts = []
        for v, c in e.args:
            if c == True:
                parts.append(self._print(v))
            else:
                parts.append(self._print(c))
                parts.append(self._print(v))
        return "piecewise(" + ", ".join(parts) + ")"

    def _print_Derivative(self, e):
        f = self._print(e.expr)
        vs = []
        for v, n in e.variable_count:
            vs.append(self._print(v) if n == 1 else f"{self._print(v)}${n}")
        return f"diff({f}, {', '.join(vs)})"

    def _print_Subs(self, e):
        ex = e.expr
        if isinstance(ex, sp.Derivative) and len(e.variables) == 1 and len(ex.variable_count) == 1:
            f = ex.expr
            v, n = ex.variable_count[0]
            if isinstance(f, sp.core.function.AppliedUndef) and len(f.args) == 1 and f.args[0] == v == e.variables[0]:
                pt = self._print(e.point[0])
                return f"D({f.func.__name__})({pt})" if n == 1 else f"(D@@{n})({f.func.__name__})({pt})"
        pts = ", ".join(f"{self._print(v)} = {self._print(p)}" for v, p in zip(e.variables, e.point))
        return f"eval({self._print(ex)}, {pts})"

    def _print_Integral(self, e):
        f = self._print(e.function)
        ls = []
        for l in e.limits:
            if len(l) == 3:
                ls.append(f"{self._print(l[0])} = {self._print(l[1])}..{self._print(l[2])}")
            else:
                ls.append(self._print(l[0]))
        return f"Int({f}, {', '.join(ls)})"

    def _print_Sum(self, e):
        out = self._print(e.function)
        for l in reversed(e.limits):
            out = f"Sum({out}, {self._print(l[0])} = {self._print(l[1])}..{self._print(l[2])})"
        return out

    def _print_Product(self, e):
        l = e.limits[0]
        return f"Product({self._print(e.function)}, {self._print(l[0])} = {self._print(l[1])}..{self._print(l[2])})"

    def _print_Limit(self, e):
        z, z0, d = e.args[1:]
        s = f"Limit({self._print(e.args[0])}, {self._print(z)} = {self._print(z0)}"
        if str(d) == "-":
            s += ", left"
        elif str(d) == "+" and False:
            s += ", right"
        return s + ")"

    def _print_Indexed(self, e):
        return f"{self._print(e.base)}[{', '.join(self._print(i) for i in e.indices)}]"

    def _print_IndexedBase(self, e): return str(e.label)

    def _print_MatrixBase(self, M):
        r, c = M.shape
        if c == 1:
            return "Vector[column]([" + ", ".join(self._print(x) for x in M) + "])"
        rows = ["[" + ", ".join(self._print(M[i, j]) for j in range(c)) + "]" for i in range(r)]
        return f"Matrix({r}, {c}, [{', '.join(rows)}])"
    _print_ImmutableDenseMatrix = _print_MatrixBase
    _print_MutableDenseMatrix = _print_MatrixBase
    _print_DenseMatrix = _print_MatrixBase
    _print_SparseMatrix = _print_MatrixBase
    _print_ImmutableMatrix = _print_MatrixBase
    _print_MutableSparseMatrix = _print_MatrixBase
    _print_ImmutableSparseMatrix = _print_MatrixBase


_P = MapleStr()


def _arrow_src(src):
    s = re.sub(r"\s*->\s*", " -> ", src.strip())
    return s


def obj_text(v, pr=None):
    pr = pr or _P
    if isinstance(v, Range):
        lo = "" if v.lo is None else pr._print(v.lo)
        hi = "" if v.hi is None else pr._print(v.hi)
        return f"{lo}..{hi}"
    if isinstance(v, Table):
        return "table([" + ", ".join(f"{pr._print(k)} = {pr._print(x)}" for k, x in v.items()) + "])"
    if isinstance(v, MProc):
        if v.arrow:
            return _arrow_src(v.src)
        if v.src:
            return v.src.strip()
        return "proc() ... end proc"
    if isinstance(v, Composition):
        return "(" + "@".join(pr._print(f) for f in v.fs) + ")"
    if isinstance(v, Repeat):
        return f"({pr._print(v.f)}@@{pr._print(v.n)})"
    if isinstance(v, DOp):
        return f"D({v.name})" if v.order == 1 else f"(D@@{v.order})({v.name})"
    if isinstance(v, PyFn):
        return v.text
    if isinstance(v, TypeDecl):
        return f"{pr._print(v.val)}::{pr._print(v.typ)}"
    if isinstance(v, Plot):
        return ""
    if isinstance(v, Seq):
        return ", ".join(pr._print(x) for x in v)
    if isinstance(v, MSet):
        return "{" + ", ".join(pr._print(x) for x in v) + "}"
    if isinstance(v, MList):
        return "[" + ", ".join(pr._print(x) for x in v) + "]"
    return str(v)


def matrix_block(M):
    r, c = M.shape
    if r == 0 or c == 0:
        return f"Matrix({r}, {c}, [])"
    cells = [[_P._print(M[i, j]) for j in range(c)] for i in range(r)]
    w = [max(len(cells[i][j]) for i in range(r)) for j in range(c)]
    lines = []
    for i in range(r):
        lines.append("[" + " ".join(cells[i][j].rjust(w[j]) for j in range(c)) + "]")
    return "\n".join(lines)


def to_text(val):
    if val is None:
        return ""
    if isinstance(val, Seq):
        return ", ".join(_one(x) for x in val)
    return _one(val)


def _one(v):
    if isinstance(v, sp.MatrixBase) and not isinstance(v, sp.Basic.__class__):
        return matrix_block(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Plot):
        return ""
    return _P._print(v) if not isinstance(v, str) or isinstance(v, Str) else str(v)


# ---------------------------------------------------------------- LaTeX
def to_latex(val):
    try:
        return _latex(val)
    except Exception:
        return to_text(val)


def _latex(v):
    if v is None:
        return ""
    if isinstance(v, Plot):
        return ""
    if isinstance(v, Seq):
        return ",\\, ".join(_latex(x) for x in v)
    if isinstance(v, MSet):
        return "\\left\\{" + ",\\, ".join(_latex(x) for x in v) + "\\right\\}"
    if isinstance(v, MList):
        return "\\left[" + ",\\, ".join(_latex(x) for x in v) + "\\right]"
    if isinstance(v, Str):
        return "\\text{" + str(v).replace("_", "\\_") + "}"
    if isinstance(v, Range):
        lo = "" if v.lo is None else _latex(v.lo)
        hi = "" if v.hi is None else _latex(v.hi)
        return f"{lo}\\ldots {hi}"
    if isinstance(v, Table):
        return "\\mathrm{table}\\left(\\left[" + ",\\, ".join(f"{_latex(k)} = {_latex(x)}" for k, x in v.items()) + "\\right]\\right)"
    if isinstance(v, bool):
        return "\\mathrm{true}" if v else "\\mathrm{false}"
    if isinstance(v, sp.Basic) or isinstance(v, sp.MatrixBase):
        if isinstance(v, sp.MatrixBase):
            return sp.latex(v, mat_delim="[", mat_str="matrix")
        s = sp.latex(v, ln_notation=True)
        return s
    if isinstance(v, (MProc, Composition, Repeat, DOp, PyFn, TypeDecl)):
        return "\\text{" + to_text(v).replace("_", "\\_").replace("^", "\\^{}") + "}"
    if isinstance(v, (int, float)):
        return str(v)
    return "\\text{" + str(v) + "}"
