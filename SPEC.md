# mini-Maple — ontwerp (bindend voor alle modules)
Eigen implementatie (GEEN Maple-code/-bestanden kopiëren of decompileren), Python 3.14 + SymPy 1.14, venv: `.venv/bin/python`.
Doel: Maple-achtige syntax; de commando's voor wiskundige modellering (calculus, lineaire algebra, vectoranalyse, DV's, transformaties). Pakket `minimaple/`.
Waardemodel + registry: `minimaple/values.py` (lees dit eerst!). Builtins: `@maple('naam', pkg='LinearAlgebra') def f(ctx, *args)`.
Waarden zijn sympy-objecten (Expr, Matrix (kolomvector = nx1, rijvector = 1xn), Eq, Function-toepassingen, Piecewise), MList, MSet, Seq, Range, Str, Plot.
Opties `color=red` komen als `sp.Eq(Symbol('color'), ...)` (zie split_opts). Onbekende namen zijn `sp.Symbol(naam)` (via ctx.sym). Onbepaalde functies `y(x)` = `sp.Function('y')(x)`.
Constanten: Pi->sp.pi, I->sp.I, infinity->sp.oo, E bestaat niet (exp(1)), Euler gamma -> `gamma`.
Interpreter-API (module interp.py): `Interpreter().run(code:str) -> list[dict]` met per statement
`{"stmt":str,"show":bool,"text":str,"latex":str|None,"plots":[Plot],"error":str|None}`; `show`=False bij `:`-afsluiting;
printf/print-uitvoer komt als eigen resultaat. `Interpreter.eval_str(code)->waarde`. Sessie-staat blijft in het object.
Printer (printer.py): `to_text(val)` Maple-stijl (x^2, Pi, ln, sqrt(2), arcsin, Dirac, Heaviside, `_C1`, Matrix als blok `[1 2]`), `to_latex(val)`.
Core-special forms (parser/interp): `:=`, ;/: , `->`, proc...end proc, if/elif/else, for/while/do, seq/add/mul (lui, met `i=a..b` of `i in L`), `x$n`, `@`, `@@`, `assuming`, `D`, `eval(e, x=a)`, `%`, `with(pkg)`, `pkg:-f`, `Pkg[f](..)`, indexering 1-based a[i], M[i,j], M[i,..], `evalf[n]`, `.` (matrixproduct/dotproduct), `<a,b>` kolom -> BUILTINS['_vstack'], `<a|b>` -> BUILTINS['_hstack'].
Modules: calc.py (calculus/solve/dsolve/transforms), linalg.py (LinearAlgebra), vecalc.py (VectorCalculus), plots.py (plot-commando's + render), interp.py/parser.py/printer.py/core_fns.py, cli.py, mcp_server.py, web/ (UI).
Elke module heeft eigen tests in tests/test_<module>.py (pytest, `.venv/bin/python -m pytest`). Test altijd tegen bekende/analytische oplossingen. Wijzig alleen je eigen bestanden; zit je iets in de weg in een ander bestand, meld het in je eindrapport.
