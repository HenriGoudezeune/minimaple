"""Gedeeld waardemodel + registry voor mini-Maple. Alle modules gebruiken dit."""
import sympy as sp

class MList(list):
    """Maple-lijst [a,b,c] (1-based indexering gebeurt in de interpreter)."""
class MSet(list):
    """Maple-verzameling {a,b}: lijst zonder dubbels, volgorde van invoer."""
class Seq(tuple):
    """Expressiereeks a,b,c (resultaat van bv. Eigenvectors, solve bij stelsels)."""
class Range:
    def __init__(s, lo, hi): s.lo, s.hi = lo, hi
    def __repr__(s): return f"{s.lo}..{s.hi}"
class Str(str):
    pass
class Table(dict):
    pass

class Plot:
    """Plot-object. spec = lijst van dicts (zie plots.py); .render(path) schrijft PNG."""
    def __init__(s, kind, layers, opts=None, dim=2):
        s.kind, s.layers, s.opts, s.dim = kind, layers, opts or {}, dim
    def render(s, path): 
        from . import plots; plots.render(s, path)

BUILTINS = {}      # naam -> functie(ctx, *args)   (kleine letters en Hoofdletters zoals in Maple)
PACKAGES = {}      # pakketnaam -> lijst namen (voor with(pkg) en pkg:-f)

def maple(*names, pkg=None):
    """Registreer een builtin: @maple('diff') def f(ctx, *args). Opties zoals color=red komen
    als sympy.Eq(Symbol('color'), Symbol('red')) in args. Retourneer een Maple-waarde."""
    def deco(fn):
        for n in names:
            BUILTINS[n] = fn
            if pkg: PACKAGES.setdefault(pkg, []).append(n)
        return fn
    return deco

def split_opts(args):
    """-> (positioneel, {naam: waarde}) voor argumenten van de vorm naam=waarde met Symbol links."""
    pos, opts = [], {}
    for a in args:
        if isinstance(a, sp.Equality) and isinstance(a.lhs, sp.Symbol) and a.lhs.name in OPTION_NAMES:
            opts[a.lhs.name] = a.rhs
        else: pos.append(a)
    return pos, opts

OPTION_NAMES = {'color','colour','title','thickness','linestyle','style','numpoints','view','labels','legend',
  'axes','scaling','discont','symbol','symbolsize','grid','resolution','axis','coords','method','output','shape',
  'digits','numeric','type','ics','source','range','arrows','scaling','gridlines','font','titlefont','axesfont',
  'orientation','projection','filled','contours','thickness','linestyle','smooth','adaptive','stepsize','maxfun'}

class Ctx:
    """Interpreter-context die builtins meekrijgen: ctx.env (dict naam->waarde), ctx.digits,
    ctx.call(f,*args) om Maple-callables aan te roepen, ctx.sym(name) voor Symbol met assume-info,
    ctx.coords (VectorCalculus-coördinaten), ctx.plots (lijst Plot-objecten die getoond moeten worden),
    ctx.out(text) om print-uitvoer te verzamelen."""
