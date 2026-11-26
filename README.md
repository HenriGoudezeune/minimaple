# mini-Maple

Een kleine, aanpasbare rekenomgeving met Maple-achtige syntax, gebouwd op Python en SymPy.
Eigen implementatie: geen code of bestanden van Maple.

- **Syntax:** `:=`, `;`/`:`, `->`, `proc ... end proc`, `if`/`for`/`while`, `seq`/`add`/`map`, `x$n`, `D(y)(0)`, `<a,b>`/`<a|b>`, `pkg:-f`, `with(pkg)`, `assuming`.
- **Calculus:** `diff`, `int`, `limit`, `sum`, `series`/`taylor`, `solve`/`fsolve`, `dsolve` (ook met beginvoorwaarden en `numeric`), `pdsolve`, `simplify`, `convert`, `evalf`.
- **inttrans:** `laplace`, `invlaplace`, `fourier`, `invfourier`, `fouriercos`, `fouriersin`; DFT/FFT.
- **LinearAlgebra:** `Matrix`, `Vector`, `Determinant`, `MatrixInverse`, `Eigenvalues`, `Eigenvectors`, `LinearSolve`, `SingularValues`, `MatrixExponential`, `JordanForm`, `QRDecomposition`, ...
- **VectorCalculus:** `Gradient`, `Divergence`, `Curl`, `Laplacian`, `Jacobian`, `Hessian`, `LineInt`, `Flux` (cartesisch, cilinder, bol).
- **plots:** `plot`, `plot3d`, `implicitplot`, `fieldplot`, `contourplot`, `spacecurve`, `loglogplot`, `display`, `odeplot`, ...

## Gebruik
```
python -m venv .venv && .venv/bin/pip install sympy numpy scipy matplotlib mpmath mcp
.venv/bin/python -m minimaple                # REPL
.venv/bin/python -m minimaple -e "int(x^2, x=0..1);"
.venv/bin/python -m minimaple.web            # web-UI op 127.0.0.1:8750
.venv/bin/python -m minimaple.mcp_server     # MCP-server (stdio) voor Claude
```
Claude Code: `claude mcp add minimaple -- /pad/naar/.venv/bin/python -m minimaple.mcp_server`

Tests: `.venv/bin/python -m pytest -q tests`
