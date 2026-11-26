"""Plot-commando's voor mini-Maple (matplotlib, backend Agg).

Elke builtin retourneert een values.Plot. Een Plot heeft:
  kind   : 'plot' | 'plot3d' | 'display' | 'multi'
  layers : lijst van dicts met sleutel 'type' (zie _draw_*), of (bij 'multi') lijst van Plot-objecten
  opts   : {'title','labels','view','scaling','axes','xscale','yscale','varnames','shape','orientation'}
  dim    : 2 of 3
Plot.render(path) -> render(plot, path) schrijft een PNG (6x4 inch, licht thema).
"""
import math
import warnings

import numpy as np
import sympy as sp
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.colors import is_color_like

from .values import (maple, split_opts as _split_opts_base, OPTION_NAMES, Plot, MList, MSet, Seq, Range, Str)

PKG = "plots"

# ----------------------------------------------------------------------------- stijl
CYCLE = ["#d62728", "#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b", "#e377c2", "#17becf"]
COLORS = {
    "red": "#d62728", "blue": "#1f77b4", "green": "#2ca02c", "black": "#000000", "white": "#ffffff",
    "yellow": "#e6c200", "orange": "#ff7f0e", "magenta": "#e000e0", "cyan": "#17becf", "gold": "#d4a017",
    "brown": "#8c564b", "pink": "#ff8fb1", "violet": "#8a2be2", "navy": "#000080", "grey": "#7f7f7f",
    "gray": "#7f7f7f", "coral": "#ff7f50", "aquamarine": "#40c9a0", "khaki": "#c3b091", "maroon": "#800000",
    "turquoise": "#30d5c8", "plum": "#8e4585", "tan": "#d2b48c", "wheat": "#e5c88a", "sienna": "#a0522d",
    "salmon": "#fa8072", "orchid": "#da70d6", "lime": "#32cd32", "purple": "#800080", "darkgreen": "#006400",
}
MARKERS = {"circle": "o", "solidcircle": "o", "cross": "+", "diagonalcross": "x", "box": "s",
           "solidbox": "s", "diamond": "D", "soliddiamond": "D", "point": ".", "asterisk": "*"}
HOLLOW = {"circle", "box", "diamond"}
LINESTYLES = {"solid": "-", "dot": ":", "dash": "--", "longdash": (0, (8, 3)), "dashdot": "-.",
              "dashdotdot": (0, (3, 2, 1, 2, 1, 2)), "dotted": ":", "dashed": "--",
              1: "-", 2: ":", 3: "--", 4: "-.", 5: (0, (8, 3)), 6: (0, (3, 2, 1, 2, 1, 2))}
FIGSIZE = (6.0, 4.0)
BG, FG, GRID = "#ffffff", "#333333", "#e3e3e3"


# ----------------------------------------------------------------------------- waarde-helpers
def split_opts(args):
    """als values.split_opts, maar accepteert ook naam=waarde-objecten die geen sympy-Eq zijn (lhs/rhs)."""
    pos, opts = [], {}
    for a in args:
        if (not isinstance(a, sp.Basic) and hasattr(a, "lhs") and hasattr(a, "rhs")
                and isinstance(a.lhs, sp.Symbol) and a.lhs.name in OPTION_NAMES):
            opts[a.lhs.name] = a.rhs
        elif isinstance(a, sp.Equality) and isinstance(a.lhs, sp.Symbol) and a.lhs.name in OPTION_NAMES:
            opts[a.lhs.name] = a.rhs
        else:
            pos.append(a)
    return pos, opts


def _seq(v):
    return isinstance(v, (MList, MSet, Seq, list, tuple, sp.MatrixBase, sp.NDimArray))


def _items(v):
    if isinstance(v, sp.MatrixBase):
        return list(v) if (v.rows == 1 or v.cols == 1) else [MList(v.row(i).tolist()[0]) for i in range(v.rows)]
    if isinstance(v, sp.NDimArray):
        return list(v.tolist())
    return list(v)


def _num(v):
    if isinstance(v, (int, float, np.floating, np.integer)):
        return float(v)
    if isinstance(v, complex):
        return float(v.real) if abs(v.imag) < 1e-12 else float("nan")
    try:
        c = complex(sp.N(v))
    except Exception:
        raise ValueError(f"plot: kan {v} niet numeriek maken")
    if abs(c.imag) > 1e-9 * (1 + abs(c.real)):
        return float("nan")
    return float(c.real)


def _name(v):
    if isinstance(v, sp.Symbol):
        return v.name
    return str(v)


def _color(v):
    if v is None:
        return None
    if isinstance(v, sp.Basic) and getattr(v, "func", None) is not None and getattr(v.func, "__name__", "") == "COLOR":
        nums = [_num(a) for a in v.args[1:4]]
        return tuple(min(max(a, 0), 1) for a in nums)
    if _seq(v):
        it = _items(v)
        if len(it) == 3 and all(not isinstance(a, str) for a in it):
            try:
                return tuple(min(max(_num(a), 0), 1) for a in it)
            except Exception:
                return None
    n = _name(v).strip().lower()
    if n in COLORS:
        return COLORS[n]
    if is_color_like(n):
        return n
    if n.startswith("#") and is_color_like(n.upper()):
        return n
    return None


def _per_curve(val, n, conv=lambda a: a):
    """option die een lijst kan zijn (per curve) -> lijst van lengte n"""
    if val is None:
        return [None] * n
    if _seq(val) and not isinstance(val, (str, Str)):
        it = _items(val)
        # een RGB-triplet is geen lijst van kleuren
        out = [conv(a) for a in it]
        return [out[i % len(out)] for i in range(n)] if out else [None] * n
    c = conv(val)
    return [c] * n


def _linestyle(v):
    if v is None:
        return None
    if isinstance(v, (sp.Integer, int)):
        return LINESTYLES.get(int(v))
    return LINESTYLES.get(_name(v).strip('"').lower())


def _lw(thickness):
    if thickness is None:
        return 1.6
    t = _num(thickness)
    return 0.8 + 0.7 * max(t, 0) if t == t else 1.6


# ----------------------------------------------------------------------------- bereiken & evalueren
def _lr(a):
    """(lhs, rhs) van x=a..b in elke vorm (sympy-Eq, object met lhs/rhs, tuple (x, Range)), anders None."""
    if isinstance(a, sp.Equality):
        return a.lhs, a.rhs
    if hasattr(a, "lhs") and hasattr(a, "rhs") and not isinstance(a, sp.Basic):
        return a.lhs, a.rhs
    if isinstance(a, tuple) and not isinstance(a, Seq) and len(a) == 2 and isinstance(a[1], Range):
        return a
    return None


def _is_range_arg(a):
    if isinstance(a, Range):
        return True
    lr = _lr(a)
    return lr is not None and isinstance(lr[0], sp.Symbol) and (isinstance(lr[1], Range) or _seq(lr[1]))


def _parse_range(a):
    """-> (Symbol|None, lo, hi, vals|None)"""
    var, r = None, a
    lr = _lr(a)
    if lr is not None:
        var, r = lr
    if isinstance(r, Range):
        lo, hi = _num(r.lo), _num(r.hi)
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise ValueError("plot: bereik moet eindig zijn")
        return var, lo, hi, None
    vals = _arr(r)
    return var, float(np.nanmin(vals)), float(np.nanmax(vals)), vals.ravel()


def _arr(v):
    if isinstance(v, sp.MatrixBase):
        a = np.array([[_num(e) for e in row] for row in v.tolist()], dtype=float)
    elif isinstance(v, sp.NDimArray):
        a = np.array([[_num(e) for e in row] for row in v.tolist()], dtype=float) if v.rank() == 2 \
            else np.array([_num(e) for e in v.tolist()], dtype=float)
    elif _seq(v):
        it = _items(v)
        a = np.array([_arr(e) if _seq(e) else _num(e) for e in it], dtype=float)
    else:
        a = np.array(_num(v), dtype=float)
    if a.ndim == 2 and 1 in a.shape:
        a = a.ravel()
    return a


def _clean(res, shape):
    a = np.asarray(res)
    if a.dtype == object:
        out = np.empty(a.shape, dtype=complex)
        for i, e in np.ndenumerate(a):
            try:
                out[i] = complex(e)
            except Exception:
                out[i] = np.nan
        a = out
    if np.iscomplexobj(a):
        bad = np.abs(a.imag) > 1e-9 * (1 + np.abs(a.real))
        a = np.where(bad, np.nan, a.real)
    a = a.astype(float, copy=False)
    a = np.where(np.isfinite(a), a, np.nan)
    return np.broadcast_to(a, shape).copy()


def _dirac(x):
    return np.where(x == 0, np.inf, 0.0)


_LAMBDA_EXTRA = {"DiracDelta": _dirac}


def _eval(ctx, expr, names, arrays):
    """Evalueer expr op de (gebroadcaste) arrays; names = lijst Symbolen (of None voor callables)."""
    arrays = np.broadcast_arrays(*[np.asarray(a, dtype=float) for a in arrays])
    shape = arrays[0].shape
    if isinstance(expr, (int, float, sp.Number)) or (isinstance(expr, sp.Basic) and expr.is_number):
        return _clean(complex(sp.N(expr)) if isinstance(expr, sp.Basic) else expr, shape)
    if isinstance(expr, sp.Lambda):
        body, vs = expr.expr, list(expr.variables)
        if all(isinstance(n, sp.Symbol) for n in names):
            expr = body.subs(dict(zip(vs, names)), simultaneous=True)
        else:
            names = vs
    if not isinstance(expr, sp.Basic):
        return _pointwise(lambda *a: ctx.call(expr, *a), arrays, shape)
    free = expr.free_symbols - set(n for n in names if n is not None)
    if free:
        raise ValueError("plot: onbepaalde variabele(n): " + ", ".join(sorted(map(str, free))))
    sy = list(names)
    try:
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore")
            try:
                f = sp.lambdify(sy, expr, modules=[_LAMBDA_EXTRA, "scipy", "numpy"])
            except Exception:
                f = sp.lambdify(sy, expr, modules=[_LAMBDA_EXTRA, "numpy"])
            return _clean(f(*arrays), shape)
    except Exception:
        pass
    return _pointwise(lambda *a: expr.subs(dict(zip(sy, a))), arrays, shape)


def _pointwise(fn, arrays, shape):
    out = np.full(shape, np.nan, dtype=complex)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for idx in np.ndindex(*shape):
            args = [float(a[idx]) for a in arrays]
            if any(a != a for a in args):
                continue
            try:
                v = fn(*args)
                out[idx] = complex(sp.N(v)) if isinstance(v, sp.Basic) else complex(v)
            except Exception:
                out[idx] = np.nan
    return _clean(out, shape)


def _jump_xy(x, y, force=False):
    """zet NaN in over polen/sprongen zodat er geen verticale verbindingslijn getekend wordt"""
    y = np.array(y, float)
    x = np.array(x, float)
    y[np.abs(y) > 1e9] = np.nan
    dy = np.abs(np.diff(y))
    fin = dy[np.isfinite(dy)]
    if fin.size < 3:
        return x, y
    med = np.median(fin) + 1e-300
    scale = np.nanmax(np.abs(y)) if np.isfinite(y).any() else 0
    if force:
        big = dy > 8 * med
    else:
        big = (dy > 25 * med) & (np.sign(y[:-1]) * np.sign(y[1:]) < 0) & (dy > 0.25 * scale)
    idx = np.where(big)[0]
    if idx.size:
        x = np.insert(x, idx + 1, (x[idx] + x[idx + 1]) / 2)
        y = np.insert(y, idx + 1, np.nan)
    return x, y


# ----------------------------------------------------------------------------- opties normaliseren
def _view(v, dim):
    """-> dict met 'x','y','z' -> (lo,hi)"""
    out = {}
    if v is None:
        return out

    def rng(r):
        if isinstance(r, Range):
            try:
                lo, hi = _num(r.lo), _num(r.hi)
            except ValueError:
                return None
            return (lo, hi) if lo == lo and hi == hi else None
        return None
    if isinstance(v, Range):
        out["z" if dim == 3 else "y"] = rng(v)
    elif _seq(v):
        for k, r in zip("xyz", _items(v)):
            if rng(r):
                out[k] = rng(r)
    return {k: w for k, w in out.items() if w}


def _labels(v):
    if v is None:
        return None
    if _seq(v):
        return [_name(a).strip('"') for a in _items(v)]
    return [_name(v)]


def _common_opts(o, dim, varnames=None):
    op = {}
    if o.get("title") is not None:
        op["title"] = _name(o["title"])
    if "view" in o:
        op["view"] = _view(o["view"], dim)
    if o.get("labels") is not None or o.get("axis") is not None:
        pass
    lab = _labels(o.get("labels"))
    if lab:
        op["labels"] = lab
    elif varnames:
        op["labels"] = varnames
    if o.get("scaling") is not None:
        op["scaling"] = _name(o["scaling"]).lower()
    if o.get("axes") is not None:
        op["axes"] = _name(o["axes"]).lower()
    if o.get("orientation") is not None and _seq(o["orientation"]):
        op["orientation"] = [_num(a) for a in _items(o["orientation"])]
    return op


def _style(o):
    return _name(o["style"]).lower() if o.get("style") is not None else None


def _layer_opts(o, n):
    cols = _per_curve(o.get("color", o.get("colour")), n, _color)
    # kleur als RGB-lijst: één kleur
    if "color" in o or "colour" in o:
        c0 = o.get("color", o.get("colour"))
        if _seq(c0) and len(_items(c0)) == 3 and all(not isinstance(a, (str, Str)) for a in _items(c0)):
            cols = [_color(c0)] * n
    th = _per_curve(o.get("thickness"), n, lambda a: _lw(a))
    ls = _per_curve(o.get("linestyle"), n, _linestyle)
    leg = _per_curve(o.get("legend"), n, lambda a: _name(a).strip('"'))
    sym = _per_curve(o.get("symbol"), n, lambda a: _name(a).strip('"').lower())
    ssz = _per_curve(o.get("symbolsize"), n, _num)
    return cols, th, ls, leg, sym, ssz


def _marker(sym, default="o"):
    if sym is None:
        return default
    return MARKERS.get(sym, default)


def _line_layer(x, y, i, lo, style, default_marker="o", jumps=None, z=None):
    cols, th, ls, leg, sym, ssz = lo
    L = {"type": "line" if z is None else "curve3d", "x": x, "y": y, "color": cols[i],
         "lw": th[i] or 1.6, "ls": ls[i] or "-", "label": leg[i], "marker": None, "ms": ssz[i] or 5,
         "hollow": False}
    if z is not None:
        L["z"] = z
    if style == "point":
        L["ls"] = "none"
        L["marker"] = _marker(sym[i], default_marker)
        L["hollow"] = sym[i] in HOLLOW
    elif sym[i]:
        L["marker"] = _marker(sym[i])
        L["hollow"] = sym[i] in HOLLOW
    return L


# ----------------------------------------------------------------------------- plot (2D)
def _npts(o, default=1200):
    n = o.get("numpoints")
    if n is None:
        return default
    return max(int(_num(n)), 2)


def _split_data(args):
    """splits posities in (data, ranges, rest)"""
    pos, o = split_opts(args)
    rngs = [a for a in pos if _is_range_arg(a)]
    rest = [a for a in pos if not _is_range_arg(a)]
    return rest, rngs, o


def _is_param_list(d):
    if isinstance(d, (MList, list, tuple)) and len(d) >= 3 and not isinstance(d, (MSet,)):
        last = _items(d)[-1]
        return _is_range_arg(last)
    return False


def _expr_list(d):
    """[x(t),y(t)] / Matrix-vector -> lijst expressies"""
    return _items(d)


def _has_vars(e):
    if isinstance(e, sp.Lambda):
        return True
    if isinstance(e, sp.Basic):
        return bool(e.free_symbols)
    return not isinstance(e, (int, float))


def _is_data_seq(d):
    """lijst met enkel getallen of paren/rijen van getallen"""
    if isinstance(d, sp.MatrixBase):
        return all(not e.free_symbols for e in d)
    if not _seq(d):
        return False
    for e in _items(d):
        if _seq(e):
            if not _is_data_seq(e):
                return False
        elif isinstance(e, sp.Basic):
            if e.free_symbols:
                return False
        elif not isinstance(e, (int, float, np.number)):
            return False
    return True


def _data_xy(d):
    a = _arr(d)
    if a.ndim == 1:
        return np.arange(1, len(a) + 1, dtype=float), a
    if a.ndim == 2 and a.shape[1] == 2:
        return a[:, 0], a[:, 1]
    if a.ndim == 2 and a.shape[0] == 2:
        return a[0], a[1]
    raise ValueError("plot: data moet een lijst getallen of paren [x,y] zijn")


def _func_layers(ctx, exprs, rng, o, lo, style, polar=False):
    var, a, b, vals = _parse_range(rng) if rng is not None else (None, None, None, None)
    layers = []
    names = []
    for i, e in enumerate(exprs):
        v = var
        if v is None:
            if isinstance(e, sp.Lambda):
                v = e.variables[0]
            elif isinstance(e, sp.Basic) and len(e.free_symbols) == 1:
                v = next(iter(e.free_symbols))
            elif isinstance(e, sp.Basic) and e.free_symbols:
                raise ValueError("plot: geef een bereik, bv. x=0..1")
            else:
                v = sp.Symbol("x")
        if a is None:
            raise ValueError("plot: bereik ontbreekt (bv. x=-5..5)")
        t = np.asarray(vals, float) if vals is not None else np.linspace(a, b, _npts(o))
        y = _eval(ctx, e, [v], [t])
        if polar:
            x, y = y * np.cos(t), y * np.sin(t)
        else:
            x = t
            if _name(o.get("discont", "")).lower() != "false" and vals is None and style != "point":
                x, y = _jump_xy(x, y, _name(o.get("discont", "")).lower() == "true")
        L = _line_layer(x, y, i, lo, style, ".", )
        if style == "point" and L["marker"] == "o" and o.get("symbol") is None:
            L["marker"] = "."
        layers.append(L)
        names.append(v.name if isinstance(v, sp.Symbol) else "x")
    return layers, (names[0] if names else "x")


def _plot_impl(ctx, args, scale=None, polar=False, default_style=None):
    rest, rngs, o = _split_data(args)
    if not rest:
        raise ValueError("plot: geen te plotten gegevens")
    d = rest[0]
    if len(rest) >= 2 and not rngs and _is_data_seq(rest[0]) and _is_data_seq(rest[1]):
        # plot(X, Y)
        d = None
        x, y = _arr(rest[0]), _arr(rest[1])
    style = _style(o) or default_style
    if str(o.get("coords", "")).lower().strip('"') == "polar":
        polar = True
    layers, xn = [], "x"
    if d is None:
        lo = _layer_opts(o, 1)
        layers = [_line_layer(x.ravel(), y.ravel(), 0, lo, style, "o")]
    elif _is_param_list(d) or (isinstance(d, sp.MatrixBase) and d.cols == 1 and d.rows in (2, 3) and rngs):
        if _is_param_list(d):
            it = _items(d)
            exprs, rng = it[:-1], it[-1]
        else:
            exprs, rng = _items(d), rngs[0]
        if len(exprs) == 3:
            return _spacecurve_build(ctx, exprs, rng, o)
        if len(exprs) != 2:
            raise ValueError("plot: parametrisch plot verwacht [x(t), y(t), t=a..b]")
        var, a, b, vals = _parse_range(rng)
        t = np.asarray(vals, float) if vals is not None else np.linspace(a, b, _npts(o))
        lo = _layer_opts(o, 1)
        if var is None:
            var = sp.Symbol("t")
        x = _eval(ctx, exprs[0], [var], [t])
        y = _eval(ctx, exprs[1], [var], [t])
        if polar:
            x, y = x * np.cos(y), x * np.sin(y)
        layers = [_line_layer(x, y, 0, lo, style, "o")]
        xn = "x"
    elif isinstance(d, (MSet,)) or (_seq(d) and not _is_data_seq(d) and not isinstance(d, sp.MatrixBase)):
        exprs = _items(d)
        if not rngs:
            raise ValueError("plot: bereik ontbreekt (bv. x=-5..5)")
        lo = _layer_opts(o, len(exprs))
        layers, xn = _func_layers(ctx, exprs, rngs[0], o, lo, style, polar)
    elif _is_data_seq(d) or isinstance(d, (sp.MatrixBase, sp.NDimArray)):
        # lijst-van-lijsten van paren (meerdere datasets)?
        items = _items(d)
        multi = (not isinstance(d, sp.MatrixBase) and items and all(_seq(e) and _is_data_seq(e) and
                 len(_items(e)) > 2 and all(_seq(q) for q in _items(e)) for e in items))
        if multi:
            lo = _layer_opts(o, len(items))
            layers = [_line_layer(*_data_xy(e), i, lo, style, "o") for i, e in enumerate(items)]
        else:
            x, y = _data_xy(d)
            lo = _layer_opts(o, 1)
            layers = [_line_layer(x, y, 0, lo, style, "o")]
    else:
        exprs = [d] + [e for e in rest[1:] if not _is_data_seq(e)]
        if not rngs:
            if isinstance(d, sp.Basic) and not d.free_symbols:
                raise ValueError("plot: bereik ontbreekt")
            if not isinstance(d, sp.Basic) or d.free_symbols:
                # callable zonder bereik is onmogelijk; expressie met 1 symbool ook
                raise ValueError("plot: bereik ontbreekt (bv. x=-5..5)")
        lo = _layer_opts(o, len(exprs))
        layers, xn = _func_layers(ctx, exprs, rngs[0], o, lo, style, polar)
    op = _common_opts(o, 2, None if polar else [xn, ""])
    if polar and "scaling" not in op:
        op["scaling"] = "constrained"
    if scale:
        op.update(scale)
    return Plot("plot", layers, op, 2)


@maple("plot")
def _plot(ctx, *args):
    return _plot_impl(ctx, args)


@maple("polarplot", pkg=PKG)
def _polarplot(ctx, *args):
    rest, rngs, o = _split_data(args)
    if not rngs and not any(_is_param_list(r) for r in rest):
        rngs = [sp.Eq(sp.Symbol("theta"), Range(-sp.pi, sp.pi))]
        args = list(args) + rngs
    return _plot_impl(ctx, args, polar=True)


@maple("loglogplot", pkg=PKG)
def _loglogplot(ctx, *args):
    return _plot_impl(ctx, args, {"xscale": "log", "yscale": "log"})


@maple("semilogplot", pkg=PKG)
def _semilogplot(ctx, *args):
    return _plot_impl(ctx, args, {"yscale": "log"})


@maple("logplot", pkg=PKG)
def _logplot(ctx, *args):
    return _plot_impl(ctx, args, {"xscale": "log"})


@maple("listplot", pkg=PKG)
def _listplot(ctx, *args):
    pos, o = split_opts(args)
    return _plot_impl(ctx, list(args))


@maple("pointplot", pkg=PKG)
def _pointplot(ctx, *args):
    pos, o = split_opts(args)
    if pos and _seq(pos[0]) and _data_dim(pos) == 3:
        return _pointplot3d(ctx, *args)
    o.setdefault("style", sp.Symbol("point"))
    pos2, _ = split_opts(args)
    return _plot_impl(ctx, pos2 + [_OptEq(k, v) for k, v in o.items()])


class _OptEq:
    def __init__(self, k, v):
        self.lhs, self.rhs = sp.Symbol(k), v


def _data_dim(pos):
    try:
        a = _arr(pos[0])
    except Exception:
        return 2
    if a.ndim == 2 and a.shape[1] == 3 and a.shape[0] != 3 or len(pos) == 3:
        return 3
    return 2


# ----------------------------------------------------------------------------- 3D krommen en punten
def _spacecurve_build(ctx, exprs, rng, o, multi=None):
    var, a, b, vals = _parse_range(rng)
    t = np.asarray(vals, float) if vals is not None else np.linspace(a, b, _npts(o, 800))
    var = var or sp.Symbol("t")
    sets = multi or [exprs]
    lo = _layer_opts(o, len(sets))
    layers = []
    for i, ex in enumerate(sets):
        xyz = [_eval(ctx, e, [var], [t]) for e in ex]
        layers.append(_line_layer(xyz[0], xyz[1], i, lo, _style(o), "o", z=xyz[2]))
    return Plot("plot3d", layers, _common_opts(o, 3, ["x", "y", "z"]), 3)


@maple("spacecurve", pkg=PKG)
def _spacecurve(ctx, *args):
    rest, rngs, o = _split_data(args)
    d = rest[0]
    if _is_param_list(d):
        it = _items(d)
        return _spacecurve_build(ctx, it[:-1], it[-1], o)
    if not rngs:
        raise ValueError("spacecurve: bereik ontbreekt")
    if isinstance(d, MSet):
        return _spacecurve_build(ctx, None, rngs[0], o, [_items(e) for e in d])
    return _spacecurve_build(ctx, _items(d), rngs[0], o)


@maple("pointplot3d", pkg=PKG)
def _pointplot3d(ctx, *args):
    pos, o = split_opts(args)
    if len(pos) == 3:
        x, y, z = (_arr(p).ravel() for p in pos)
    else:
        a = _arr(pos[0])
        if a.ndim != 2 or 3 not in a.shape:
            raise ValueError("pointplot3d: verwacht lijst van [x,y,z]")
        x, y, z = (a[:, 0], a[:, 1], a[:, 2]) if a.shape[1] == 3 else (a[0], a[1], a[2])
    style = _style(o) or "point"
    lo = _layer_opts(o, 1)
    L = _line_layer(x, y, 0, lo, style, "o", z=z)
    return Plot("plot3d", [L], _common_opts(o, 3, ["x", "y", "z"]), 3)


# ----------------------------------------------------------------------------- plot3d
def _coords_conv(o, X, Y, Z):
    c = _name(o.get("coords", "")).strip('"').lower()
    if c == "spherical":        # (r, theta=azimut, phi=polair)
        return X * np.cos(Y) * np.sin(Z), X * np.sin(Y) * np.sin(Z), X * np.cos(Z)
    if c == "cylindrical":
        return X * np.cos(Y), X * np.sin(Y), Z
    return X, Y, Z


def _grid_n(o, default=60):
    g = o.get("grid", o.get("gridlines"))
    if g is not None and _seq(g):
        m = [int(_num(a)) for a in _items(g)]
        return max(m[0], 2), max(m[-1] if len(m) > 1 else m[0], 2)
    n = o.get("numpoints")
    if n is not None:
        k = max(int(math.sqrt(_num(n))), 2)
        return k, k
    return default, default


@maple("plot3d")
def _plot3d(ctx, *args):
    rest, rngs, o = _split_data(args)
    if not rest:
        raise ValueError("plot3d: geen gegevens")
    d = rest[0]
    style = _style(o) or "surface"
    m, n = _grid_n(o)
    # kolomvector / [X,Y,Z] = parametrisch
    param = (isinstance(d, sp.MatrixBase) and d.cols == 1) or (isinstance(d, (MList, list)) and len(d) == 3
                                                                  and not _is_param_list(d))
    if param and len(rngs) == 1:
        return _spacecurve_build(ctx, _items(d), rngs[0], o)
    if len(rngs) < 2 and not (isinstance(d, sp.Basic) or callable(d) or _seq(d)):
        raise ValueError("plot3d: twee bereiken nodig, bv. x=-1..1, y=-1..1")
    if len(rngs) < 2:
        raise ValueError("plot3d: twee bereiken nodig, bv. x=-1..1, y=-1..1")
    (v1, a1, b1, w1), (v2, a2, b2, w2) = _parse_range(rngs[0]), _parse_range(rngs[1])
    u = np.asarray(w1, float) if w1 is not None else np.linspace(a1, b1, m)
    v = np.asarray(w2, float) if w2 is not None else np.linspace(a2, b2, n)
    U, V = np.meshgrid(u, v)
    if param:
        surfs = [_items(d)]
    elif isinstance(d, MSet) or (isinstance(d, (MList, list)) and not param):
        surfs = [e if not _seq(e) else _items(e) for e in _items(d)]
    else:
        surfs = [d]
    cols, th, ls, leg, sym, ssz = _layer_opts(o, len(surfs))
    layers = []
    names = [v1, v2]
    for i, s in enumerate(surfs):
        if isinstance(s, list):
            if len(s) != 3:
                raise ValueError("plot3d: parametrisch oppervlak verwacht [x,y,z]")
            X, Y, Z = (_eval(ctx, e, names, [U, V]) for e in s)
        else:
            Z = _eval(ctx, s, names, [U, V])
            X, Y = U, V
        X, Y, Z = _coords_conv(o, X, Y, Z)
        layers.append({"type": "surface", "X": X, "Y": Y, "Z": Z, "color": cols[i], "style": style,
                       "label": leg[i], "lw": th[i]})
    vn = [x.name if isinstance(x, sp.Symbol) else s for x, s in zip(names, "xy")] + ["z"]
    op = _common_opts(o, 3, vn if not param else ["x", "y", "z"])
    return Plot("plot3d", layers, op, 3)


# ----------------------------------------------------------------------------- contour / implicit
def _two_ranges(rngs, fname):
    if len(rngs) < 2:
        raise ValueError(f"{fname}: twee bereiken nodig, bv. x=-2..2, y=-2..2")
    return _parse_range(rngs[0]), _parse_range(rngs[1])


@maple("contourplot", pkg=PKG)
def _contourplot(ctx, *args):
    rest, rngs, o = _split_data(args)
    (v1, a1, b1, w1), (v2, a2, b2, w2) = _two_ranges(rngs, "contourplot")
    m, n = _grid_n(o, 150)
    X, Y = np.meshgrid(np.linspace(a1, b1, m) if w1 is None else w1, np.linspace(a2, b2, n) if w2 is None else w2)
    names = [v1 or sp.Symbol("x"), v2 or sp.Symbol("y")]
    Z = _eval(ctx, rest[0], names, [X, Y])
    c = o.get("contours")
    levels = None
    if c is not None:
        levels = [_num(a) for a in _items(c)] if _seq(c) else int(_num(c))
    else:
        levels = 8
    fl = _name(o.get("filled", "false")).lower() == "true"
    cols, th, ls, leg, sym, ssz = _layer_opts(o, 1)
    L = {"type": "contour", "X": X, "Y": Y, "Z": Z, "levels": levels, "filled": fl, "color": cols[0],
         "label": None, "lw": th[0] or 1.2, "labels": True}
    return Plot("plot", [L], _common_opts(o, 2, [names[0].name, names[1].name]), 2)


def _eqs(d):
    items = _items(d) if _seq(d) else [d]
    out = []
    for e in items:
        out.append(e.lhs - e.rhs if isinstance(e, sp.Equality) else e)
    return out


@maple("implicitplot", pkg=PKG)
def _implicitplot(ctx, *args):
    rest, rngs, o = _split_data(args)
    (v1, a1, b1, w1), (v2, a2, b2, w2) = _two_ranges(rngs, "implicitplot")
    m, n = _grid_n(o, 500)
    X, Y = np.meshgrid(np.linspace(a1, b1, m), np.linspace(a2, b2, n))
    names = [v1 or sp.Symbol("x"), v2 or sp.Symbol("y")]
    fs = _eqs(rest[0])
    cols, th, ls, leg, sym, ssz = _layer_opts(o, len(fs))
    layers = []
    for i, f in enumerate(fs):
        Z = _eval(ctx, f, names, [X, Y])
        layers.append({"type": "contour", "X": X, "Y": Y, "Z": Z, "levels": [0.0], "filled": False,
                       "color": cols[i], "label": leg[i], "lw": th[i] or 1.6, "labels": False, "auto": True})
    return Plot("plot", layers, _common_opts(o, 2, [names[0].name, names[1].name]), 2)


@maple("implicitplot3d", pkg=PKG)
def _implicitplot3d(ctx, *args):
    rest, rngs, o = _split_data(args)
    if len(rngs) < 3:
        raise ValueError("implicitplot3d: drie bereiken nodig")
    ps = [_parse_range(r) for r in rngs[:3]]
    k = _grid_n(o, 36)[0]
    ax = [np.linspace(p[1], p[2], k) for p in ps]
    X, Y, Z = np.meshgrid(*ax, indexing="ij")
    names = [p[0] or sp.Symbol(s) for p, s in zip(ps, "xyz")]
    fs = _eqs(rest[0])
    cols, th, ls, leg, sym, ssz = _layer_opts(o, len(fs))
    layers = [{"type": "implicit3d", "X": X, "Y": Y, "Z": Z, "F": _eval(ctx, f, names, [X, Y, Z]),
               "color": cols[i], "label": leg[i]} for i, f in enumerate(fs)]
    return Plot("plot3d", layers, _common_opts(o, 3, [n.name for n in names]), 3)


# ----------------------------------------------------------------------------- vectorvelden
def _vec_exprs(d, k):
    ex = _items(d)
    if len(ex) != k:
        raise ValueError(f"vectorveld moet {k} componenten hebben")
    return ex


def _field2(ctx, ex, rngs, o, fname):
    (v1, a1, b1, w1), (v2, a2, b2, w2) = _two_ranges(rngs, fname)
    m, n = _grid_n(o, 18)
    if o.get("grid") is None and o.get("gridlines") is None and o.get("numpoints") is None:
        m = n = 18
    X, Y = np.meshgrid(np.linspace(a1, b1, m), np.linspace(a2, b2, n))
    names = [v1 or sp.Symbol("x"), v2 or sp.Symbol("y")]
    U, V = (_eval(ctx, e, names, [X, Y]) for e in ex)
    cols = _layer_opts(o, 1)[0]
    L = {"type": "field", "X": X, "Y": Y, "U": U, "V": V, "color": cols[0]}
    return Plot("plot", [L], _common_opts(o, 2, [names[0].name, names[1].name]), 2)


@maple("fieldplot", pkg=PKG)
def _fieldplot(ctx, *args):
    rest, rngs, o = _split_data(args)
    return _field2(ctx, _vec_exprs(rest[0], 2), rngs, o, "fieldplot")


def _field3(ctx, ex, rngs, o, fname):
    if len(rngs) < 3:
        raise ValueError(f"{fname}: drie bereiken nodig")
    ps = [_parse_range(r) for r in rngs[:3]]
    k = 6
    g = o.get("grid", o.get("gridlines"))
    if g is not None and _seq(g):
        k = max(int(_num(_items(g)[0])), 2)
    ax = [np.linspace(p[1], p[2], k) for p in ps]
    X, Y, Z = np.meshgrid(*ax, indexing="ij")
    names = [p[0] or sp.Symbol(s) for p, s in zip(ps, "xyz")]
    U, V, W = (_eval(ctx, e, names, [X, Y, Z]) for e in ex)
    cols = _layer_opts(o, 1)[0]
    L = {"type": "field3d", "X": X, "Y": Y, "Z": Z, "U": U, "V": V, "W": W, "color": cols[0]}
    return Plot("plot3d", [L], _common_opts(o, 3, [n.name for n in names]), 3)


@maple("fieldplot3d", pkg=PKG)
def _fieldplot3d(ctx, *args):
    rest, rngs, o = _split_data(args)
    return _field3(ctx, _vec_exprs(rest[0], 3), rngs, o, "fieldplot3d")


@maple("gradplot", pkg=PKG)
def _gradplot(ctx, *args):
    rest, rngs, o = _split_data(args)
    vs = [_parse_range(r)[0] or sp.Symbol(s) for r, s in zip(rngs, "xy")]
    f = rest[0]
    return _field2(ctx, [sp.diff(f, v) for v in vs[:2]], rngs, o, "gradplot")


@maple("gradplot3d", pkg=PKG)
def _gradplot3d(ctx, *args):
    rest, rngs, o = _split_data(args)
    vs = [_parse_range(r)[0] or sp.Symbol(s) for r, s in zip(rngs, "xyz")]
    return _field3(ctx, [sp.diff(rest[0], v) for v in vs[:3]], rngs, o, "gradplot3d")


# ----------------------------------------------------------------------------- tekst, odeplot
@maple("textplot", pkg=PKG)
def _textplot(ctx, *args):
    pos, o = split_opts(args)
    d = pos[0]
    items = _items(d)
    if items and not _seq(items[0]):
        items = [d]
    layers = []
    col = _color(o.get("color"))
    for it in items:
        x, y, s = _items(it)[:3]
        layers.append({"type": "text", "x": _num(x), "y": _num(y), "s": _name(s).strip('"'), "color": col})
    return Plot("plot", layers, _common_opts(o, 2), 2)


@maple("complexplot", pkg=PKG)
def _complexplot(ctx, *args):
    """complexplot(f(t), t=a..b): kromme (Re f, Im f) in het complexe vlak."""
    rest, rngs, o = _split_data(args)
    if not rngs:
        raise ValueError("complexplot: bereik ontbreekt")
    var = _parse_range(rngs[0])[0] or sp.Symbol("t")
    tr = sp.Symbol(var.name, real=True)
    f = sp.sympify(rest[0]).subs(var, tr)
    parts = [sp.re(f).subs(tr, var), sp.im(f).subs(tr, var)]
    others = [a for a in args if a is not rest[0] and all(a is not r for r in rngs)]
    op = _plot_impl(ctx, [MList(parts + [rngs[0]])] + others)
    op.opts.setdefault("scaling", "constrained")
    return op


@maple("densityplot", pkg=PKG)
def _densityplot(ctx, *args):
    extra = [sp.Eq(sp.Symbol("filled"), sp.Symbol("true"))]
    if not any(isinstance(a, sp.Equality) and str(a.lhs) == "contours" for a in args):
        extra.append(sp.Eq(sp.Symbol("contours"), sp.Integer(30)))
    return _contourplot(ctx, *args, *extra)


def _subs_deep(a, var, val):
    if isinstance(a, (MList, MSet, Seq)):
        return type(a)(_subs_deep(x, var, val) for x in a)
    if isinstance(a, sp.Equality) and not isinstance(a.rhs, sp.Basic):
        return a
    if isinstance(a, sp.Basic):
        return a.subs(var, val)
    return a


@maple("animate", pkg=PKG)
def _animate(ctx, *args):
    """animate(plotcmd, [args], t=a..b, frames=n): vaste weergave = alle frames over elkaar (kleur per frame)."""
    from .values import BUILTINS
    pos, o = split_opts(args)
    if len(pos) < 3:
        raise ValueError("animate: animate(plot, [argumenten], t=a..b)")
    cmd, fargs, rng = pos[0], _items(pos[1]) if _seq(pos[1]) else [pos[1]], pos[2]
    var, a, b, _ = _parse_range(rng)
    nfr = int(_num(o["frames"])) if "frames" in o else 6
    nfr = max(2, min(nfr, 12))
    fn = BUILTINS.get(cmd.name if isinstance(cmd, sp.Symbol) else str(cmd))
    if fn is None:
        raise ValueError("animate: onbekend plotcommando")
    layers, base = [], None
    grad = matplotlib.colormaps["viridis"]
    for k, tv in enumerate(np.linspace(a, b, nfr)):
        pl = fn(ctx, *[_subs_deep(x, var, sp.Float(float(tv))) for x in fargs])
        col = matplotlib.colors.to_hex(grad(k / (nfr - 1)))
        for L in pl.layers:
            if isinstance(L, dict):
                L = dict(L)
                if L.get("type") in ("line", "curve3d"):
                    L["color"] = col
                L["label"] = None
                layers.append(L)
        base = base or pl
    op = dict(base.opts)
    op["title"] = f"{var.name} = {a:g} .. {b:g} ({nfr} frames)"
    return Plot(base.kind, layers, op, base.dim)


def _ode_state(res):
    m = {}
    it = res
    if isinstance(res, dict):
        it = [sp.Eq(k, v) for k, v in res.items()]
    elif isinstance(res, sp.Equality):
        it = [res]
    elif _seq(res):
        it = _items(res)
    for e in it:
        if isinstance(e, sp.Equality):
            try:
                m[str(e.lhs)] = _num(e.rhs)
            except ValueError:
                pass
    return m


def _ode_value(expr, state):
    if isinstance(expr, sp.Basic):
        key = str(expr)
        if key in state:
            return state[key]
        from sympy.core.function import AppliedUndef
        rep = {}
        for a in expr.atoms(AppliedUndef, sp.Derivative, sp.Symbol):
            if str(a) in state:
                rep[a] = state[str(a)]
        try:
            return _num(expr.xreplace(rep))
        except Exception:
            return float("nan")
    return _num(expr)


@maple("odeplot", pkg=PKG)
def _odeplot(ctx, *args):
    pos, o = split_opts(args)
    rngs = [a for a in pos if _is_range_arg(a)]
    rest = [a for a in pos if not _is_range_arg(a)]
    sol = rest[0]
    spec = rest[1] if len(rest) > 1 else None
    rng = rngs[0] if rngs else o.get("range")
    if rng is None:
        for attr in ("range", "tspan"):
            if getattr(sol, attr, None) is not None:
                rng = getattr(sol, attr)
        if rng is None:
            raise ValueError("odeplot: geef een bereik, bv. t=0..5")
    var, a, b, _ = _parse_range(rng)
    tn = var.name if var is not None else "t"
    N = min(_npts(o, 300), 1000)
    ts = np.linspace(a, b, N)
    states = []
    for t in ts:
        try:
            states.append(_ode_state(ctx.call(sol, float(t))))
        except Exception:
            states.append({})
        states[-1].setdefault(tn, float(t))
    if spec is None:
        keys = [k for k in (states[0] if states else {}) if k != tn]
        if not keys:
            raise ValueError("odeplot: oplossing gaf geen waarden terug")
        spec = [sp.Symbol(tn), sp.Symbol(keys[0])]
    elif _seq(spec):
        spec = _items(spec)
    else:
        spec = [sp.Symbol(tn), spec]
    comps = [np.array([_ode_value(s_, st) for st in states]) for s_ in spec]
    lo = _layer_opts(o, 1)
    if len(comps) == 3:
        L = _line_layer(comps[0], comps[1], 0, lo, _style(o), "o", z=comps[2])
        return Plot("plot3d", [L], _common_opts(o, 3, [str(s) for s in spec]), 3)
    L = _line_layer(comps[0], comps[1], 0, lo, _style(o), "o")
    return Plot("plot", [L], _common_opts(o, 2, [str(s) for s in spec[:2]]), 2)


# ----------------------------------------------------------------------------- display
def _flatten_plots(v, out):
    if isinstance(v, Plot):
        out.append(v)
    elif _seq(v) or hasattr(v, "tolist"):
        for e in (_items(v) if _seq(v) else v.tolist()):
            _flatten_plots(e, out)
    return out


def _is_grid(v):
    """array / lijst-van-lijsten van plots -> subplots; een gewone MList/MSet wordt gecombineerd (Maple)"""
    if isinstance(v, (MList, MSet, Seq, list, tuple)):
        its = list(v)
        return bool(its) and all(isinstance(e, (MList, list, tuple)) for e in its)
    return isinstance(v, (sp.NDimArray,)) or (hasattr(v, "tolist") and not isinstance(v, sp.Basic))


def _grid_shape(v):
    rows = v.tolist() if (hasattr(v, "tolist") and not isinstance(v, (list, tuple))) else [list(r) for r in v]
    if rows and not isinstance(rows[0], (list, tuple)):
        rows = [rows]
    return rows


@maple("display", pkg=PKG)
def _display(ctx, *args):
    pos, o = split_opts(args)
    plots, grids = [], []
    for a in pos:
        if _is_grid(a):
            rows = _grid_shape(a)
            grids.append(rows)
        else:
            _flatten_plots(a, plots)
    if grids:
        rows = grids[0]
        r, c = len(rows), max(len(x) if isinstance(x, (list, tuple)) else 1 for x in rows)
        cells = [e for row in rows for e in (row if isinstance(row, (list, tuple)) else [row])]
        cells = [e for e in cells if isinstance(e, Plot)]
        op = _common_opts(o, 2)
        op["shape"] = (r, c)
        return Plot("multi", cells, op, 2)
    if not plots:
        raise ValueError("display: geen plots opgegeven")
    layers, op = [], {}
    dim = max(p.dim for p in plots)
    for p in plots:
        layers += p.layers
        for k, v in p.opts.items():
            if k == "labels" and "labels" in op and all(not s for s in v):
                continue
            op.setdefault(k, v)
    op.update(_common_opts(o, dim))
    if o.get("legend") is not None:
        lg = _per_curve(o["legend"], len([L for L in layers if L.get("type") in ("line", "curve3d", "surface", "contour")]),
                        lambda a: _name(a).strip('"'))
        i = 0
        for L in layers:
            if L.get("type") in ("line", "curve3d", "surface", "contour"):
                L = L
                L["label"] = lg[i]
                i += 1
    return Plot("display", layers, op, dim)


# ----------------------------------------------------------------------------- tekenen
def _style_ax(ax, dim=2):
    ax.set_facecolor(BG)
    for s in ax.spines.values() if dim == 2 else []:
        s.set_color("#888888")
    ax.tick_params(colors=FG, labelsize=8)
    if dim == 2:
        ax.grid(True, color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)


class _Colors:
    def __init__(self):
        self.i = 0

    def next(self):
        c = CYCLE[self.i % len(CYCLE)]
        self.i += 1
        return c


def _lim_clip(ys):
    f = np.concatenate([y[np.isfinite(y)] for y in ys]) if ys else np.array([])
    if f.size < 5:
        return None
    c = 8 * np.percentile(np.abs(f), 90) + 1e-12
    if np.abs(f).max() <= c:
        return None
    lo, hi = max(f.min(), -c), min(f.max(), c)
    pad = 0.05 * (hi - lo or 1)
    return lo - pad, hi + pad


def _draw2d(ax, plot):
    cyc = _Colors()
    o = plot.opts
    ys = []
    handles = False
    for L in plot.layers:
        t = L["type"]
        if t == "line":
            x, y = np.asarray(L["x"], float), np.asarray(L["y"], float)
            if o.get("xscale") == "log":
                x = np.where(x > 0, x, np.nan)
            if o.get("yscale") == "log":
                y = np.where(y > 0, y, np.nan)
            c = L["color"] or cyc.next()
            kw = dict(color=c, linewidth=L["lw"], linestyle=L["ls"], label=L["label"] or "_nolegend_")
            if L["marker"]:
                kw.update(marker=L["marker"], markersize=L["ms"])
                if L["hollow"]:
                    kw.update(markerfacecolor="none")
            ax.plot(x, y, **kw)
            if L["label"]:
                handles = True
            ys.append(y)
        elif t == "text":
            ax.text(L["x"], L["y"], L["s"], color=L["color"] or FG, fontsize=9, ha="center", va="center")
        elif t == "field":
            X, Y, U, V = L["X"], L["Y"], L["U"], L["V"]
            mag = np.hypot(U, V)
            ax.quiver(X, Y, U, V, color=L["color"] or CYCLE[1], angles="xy", width=0.004, pivot="mid",
                      scale=None)
        elif t == "contour":
            X, Y, Z = L["X"], L["Y"], L["Z"]
            Zm = np.ma.masked_invalid(Z)
            if Zm.count() == 0:
                continue
            lev = L["levels"]
            try:
                if L["filled"]:
                    cs = ax.contourf(X, Y, Zm, levels=lev, cmap="viridis")
                    ax.figure.colorbar(cs, ax=ax, shrink=0.85, pad=0.02).ax.tick_params(labelsize=7)
                elif L["color"] or L.get("auto"):
                    c = L["color"] or cyc.next()
                    cs = ax.contour(X, Y, Zm, levels=lev, colors=[c], linewidths=L["lw"])
                    if L["label"]:
                        cs.collections[0].set_label(L["label"]) if hasattr(cs, "collections") else None
                        ax.plot([], [], color=c, label=L["label"], linewidth=L["lw"])
                        handles = True
                else:
                    cs = ax.contour(X, Y, Zm, levels=lev, cmap="viridis", linewidths=L["lw"])
                    if L["labels"]:
                        ax.clabel(cs, fontsize=7)
            except Exception:
                pass
    if o.get("axes") == "none":
        ax.axis("off")
    elif o.get("axes") == "normal":
        ax.spines["left"].set_position("zero")
        ax.spines["bottom"].set_position("zero")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    if o.get("xscale") == "log":
        ax.set_xscale("log")
    if o.get("yscale") == "log":
        ax.set_yscale("log")
    view = o.get("view") or {}
    if "x" in view:
        ax.set_xlim(*view["x"])
    if "y" in view:
        ax.set_ylim(*view["y"])
    else:
        lim = _lim_clip(ys)
        if lim:
            ax.set_ylim(*lim)
    if o.get("scaling") == "constrained":
        ax.set_aspect("equal", adjustable="datalim" if not view else "box")
    lab = o.get("labels") or []
    if len(lab) > 0 and lab[0]:
        ax.set_xlabel(lab[0], fontsize=9, color=FG)
    if len(lab) > 1 and lab[1]:
        ax.set_ylabel(lab[1], fontsize=9, color=FG)
    if o.get("title"):
        ax.set_title(o["title"], fontsize=10, color=FG)
    if handles:
        ax.legend(fontsize=8, framealpha=0.9, loc="best")


def _draw3d(ax, plot):
    cyc = _Colors()
    o = plot.opts
    view = o.get("view") or {}
    handles = False
    allx, ally, allz = [], [], []
    for L in plot.layers:
        t = L["type"]
        if t == "surface":
            X, Y, Z = (np.asarray(L[k], float) for k in "XYZ")
            if "z" in view:
                Z = np.where((Z >= view["z"][0]) & (Z <= view["z"][1]), Z, np.nan)
            allx.append(X); ally.append(Y); allz.append(Z)
            st = L["style"]
            c = L["color"]
            kw = {}
            if st in ("wireframe", "wireframe_nogrid"):
                ax.plot_wireframe(X, Y, Z, color=c or CYCLE[1], linewidth=0.5, rstride=max(1, X.shape[0] // 25),
                                  cstride=max(1, X.shape[1] // 25))
            elif st == "contour":
                ax.contour(X, Y, np.ma.masked_invalid(Z), levels=12, cmap="viridis")
            elif st == "point":
                ax.scatter(X.ravel(), Y.ravel(), Z.ravel(), s=3, color=c or CYCLE[1])
            else:
                if c:
                    ax.plot_surface(X, Y, Z, color=c, linewidth=0.15, edgecolor="#ffffff55", alpha=0.95,
                                    antialiased=True)
                else:
                    ax.plot_surface(X, Y, Z, cmap="viridis", linewidth=0.1, edgecolor="#00000022",
                                    alpha=0.97, antialiased=True)
                if st == "surfacecontour":
                    zmin = np.nanmin(Z)
                    ax.contour(X, Y, np.ma.masked_invalid(Z), levels=10, zdir="z", offset=zmin, cmap="viridis")
            if L["label"]:
                handles = True
                ax.plot([], [], color=c or CYCLE[1], label=L["label"])
        elif t == "curve3d":
            x, y, z = (np.asarray(L[k], float) for k in "xyz")
            allx.append(x); ally.append(y); allz.append(z)
            c = L["color"] or cyc.next()
            kw = dict(color=c, linewidth=L["lw"], linestyle=L["ls"], label=L["label"] or "_nolegend_")
            if L["marker"]:
                kw.update(marker=L["marker"], markersize=L["ms"])
                if L["hollow"]:
                    kw.update(markerfacecolor="none")
            ax.plot(x, y, z, **kw)
            handles = handles or bool(L["label"])
        elif t == "field3d":
            X, Y, Z, U, V, W = (np.asarray(L[k], float) for k in ("X", "Y", "Z", "U", "V", "W"))
            allx.append(X); ally.append(Y); allz.append(Z)
            mag = np.sqrt(U ** 2 + V ** 2 + W ** 2)
            span = min(np.ptp(X), np.ptp(Y), np.ptp(Z)) / max(X.shape[0], 2)
            mx = np.nanmax(mag) or 1.0
            ax.quiver(X, Y, Z, U, V, W, length=0.9 * span / mx, normalize=False,
                      color=L["color"] or CYCLE[1], linewidth=0.8)
        elif t == "implicit3d":
            X, Y, Z, F = (np.asarray(L[k], float) for k in ("X", "Y", "Z", "F"))
            allx.append(X); ally.append(Y); allz.append(Z)
            c = L["color"] or cyc.next()
            _implicit_slices(ax, X, Y, Z, F, c)
    # grenzen
    def lims(vs, key):
        if key in view:
            return view[key]
        v = np.concatenate([np.ravel(a)[np.isfinite(np.ravel(a))] for a in vs]) if vs else np.array([])
        if v.size == 0:
            return None
        return float(v.min()), float(v.max())
    lx, ly, lz = lims(allx, "x"), lims(ally, "y"), lims(allz, "z")
    if lx:
        ax.set_xlim(*lx)
    if ly:
        ax.set_ylim(*ly)
    if lz and lz[0] != lz[1]:
        ax.set_zlim(*lz)
    if o.get("scaling") == "constrained" and lx and ly and lz:
        ax.set_box_aspect((max(np.ptp(lx), 1e-9), max(np.ptp(ly), 1e-9), max(np.ptp(lz), 1e-9)))
    lab = (o.get("labels") or []) + ["", "", ""]
    ax.set_xlabel(lab[0] or "x", fontsize=9, color=FG)
    ax.set_ylabel(lab[1] or "y", fontsize=9, color=FG)
    ax.set_zlabel(lab[2] or "z", fontsize=9, color=FG)
    ax.tick_params(labelsize=7, colors=FG)
    if o.get("axes") == "none":
        ax.set_axis_off()
    ori = o.get("orientation")
    if ori and len(ori) >= 2:
        ax.view_init(elev=ori[1], azim=ori[0])
    if o.get("title"):
        ax.set_title(o["title"], fontsize=10, color=FG)
    if handles:
        ax.legend(fontsize=8, loc="upper left")
    for a in (ax.xaxis, ax.yaxis, ax.zaxis):
        try:
            a.pane.set_facecolor((0.96, 0.96, 0.96, 1))
            a.pane.set_edgecolor("#cccccc")
            a._axinfo["grid"]["color"] = GRID
        except Exception:
            pass


def _implicit_slices(ax, X, Y, Z, F, color, count=9):
    """Geen marching cubes beschikbaar: teken nul-niveaulijnen van F op doorsneden in drie richtingen."""
    import contourpy
    n = F.shape
    for axis in range(3):
        for k in np.linspace(0, n[axis] - 1, count).round().astype(int):
            sl = [slice(None)] * 3
            sl[axis] = k
            sl = tuple(sl)
            S = F[sl]
            if not np.isfinite(S).any() or not (np.nanmin(S) < 0 < np.nanmax(S)):
                continue
            idx = [i for i in range(3) if i != axis]
            P = [X[sl], Y[sl], Z[sl]]
            A, B = P[idx[0]], P[idx[1]]
            const = float(np.nanmean(P[axis]))
            # contourpy verwacht x,y 1D of 2D met shape (ny,nx); onze arrays zijn (n0,n1): gebruik indexen
            gen = contourpy.contour_generator(z=np.ma.masked_invalid(S).T)
            for line in gen.lines(0.0):
                ii, jj = line[:, 0], line[:, 1]   # fractionele indexen (x=kolom=eerste as van S)
                def interp(M):
                    return _bilin(M, ii, jj)
                pa, pb = interp(A), interp(B)
                pts = [None, None, None]
                pts[idx[0]], pts[idx[1]], pts[axis] = pa, pb, np.full_like(pa, const)
                ax.plot(*pts, color=color, linewidth=0.9)


def _bilin(M, ii, jj):
    i0 = np.clip(np.floor(ii).astype(int), 0, M.shape[0] - 2)
    j0 = np.clip(np.floor(jj).astype(int), 0, M.shape[1] - 2)
    fi, fj = ii - i0, jj - j0
    return (M[i0, j0] * (1 - fi) * (1 - fj) + M[i0 + 1, j0] * fi * (1 - fj)
            + M[i0, j0 + 1] * (1 - fi) * fj + M[i0 + 1, j0 + 1] * fi * fj)


def render(plot, path, dpi=110):
    """Schrijf plot als PNG naar path."""
    if plot.kind == "multi":
        r, c = plot.opts.get("shape", (1, len(plot.layers)))
        fig = Figure(figsize=(6.0 if c == 1 else 7.5, 3.4 * r + (0.3 if plot.opts.get("title") else 0)), dpi=dpi,
                     facecolor=BG)
        for i, p in enumerate(plot.layers):
            ax = fig.add_subplot(r, c, i + 1, projection="3d" if p.dim == 3 else None)
            _style_ax(ax, p.dim)
            (_draw3d if p.dim == 3 else _draw2d)(ax, p)
        if plot.opts.get("title"):
            fig.suptitle(plot.opts["title"], fontsize=11, color=FG)
    else:
        fig = Figure(figsize=FIGSIZE, dpi=dpi, facecolor=BG)
        ax = fig.add_subplot(111, projection="3d" if plot.dim == 3 else None)
        _style_ax(ax, plot.dim)
        (_draw3d if plot.dim == 3 else _draw2d)(ax, plot)
    fig.tight_layout()
    fig.savefig(str(path), format="png", facecolor=BG)
    return str(path)
