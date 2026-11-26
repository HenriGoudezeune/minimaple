/* Autocompletion voor invoergroepen: commando's, pakketfuncties, eigen namen.
   Typen toont suggesties vanaf 2 letters; Ctrl+Space toont ze altijd.
   Pijltjes kiezen, Tab of Enter neemt over, Esc sluit. */
(function () {
  "use strict";
  var groups = document.getElementById("groups");
  if (!groups) return;
  var KW = ["proc", "end", "local", "global", "if", "then", "elif", "else", "for", "from", "to", "by", "while", "do", "return",
    "module", "export", "use", "in", "try", "catch", "finally", "error", "break", "next", "assuming", "and", "or", "not",
    "infinity", "Pi", "true", "false", "NULL", "Digits"];
  var cmds = null, sigs = {}, pkgOf = {};
  var SIG = {"diff": "diff(f, x) of diff(f, x$n)", "int": "int(f, x) of int(f, x=a..b)", "limit": "limit(f, x=a)", "sum": "sum(f, k=a..b)", "series": "series(f, x=a, n)", "taylor": "taylor(f, x=a, n)", "solve": "solve(vgl, x) of solve({vgln}, {x,y})", "fsolve": "fsolve(vgl, x=a..b)", "dsolve": "dsolve({DV, bvw}, y(x))", "pdsolve": "pdsolve(PDV, f(x,t))", "simplify": "simplify(e)", "expand": "expand(e)", "factor": "factor(e)", "subs": "subs(x=a, e)", "eval": "eval(e, x=a)", "evalf": "evalf(e) of evalf(e, n)", "plot": "plot(f, x=a..b, opties)", "plot3d": "plot3d(f, x=a..b, y=c..d)", "convert": "convert(e, parfrac, x)", "laplace": "laplace(f, t, s)", "invlaplace": "invlaplace(F, s, t)", "fourier": "fourier(f, t, w)", "invfourier": "invfourier(F, w, t)", "Matrix": "Matrix(m, n, init)", "Vector": "Vector(n, init) of <a, b, c>", "Determinant": "Determinant(A)", "MatrixInverse": "MatrixInverse(A)", "Eigenvalues": "Eigenvalues(A)", "Eigenvectors": "Eigenvectors(A) -> waarden, vectoren", "LinearSolve": "LinearSolve(A, b)", "Transpose": "Transpose(A)", "Rank": "Rank(A)", "NullSpace": "NullSpace(A)", "MatrixExponential": "MatrixExponential(A, t)", "SingularValues": "SingularValues(A, output=[...])", "Gradient": "Gradient(f, [x,y,z])", "Divergence": "Divergence(F)", "Curl": "Curl(F)", "Laplacian": "Laplacian(f, [x,y,z])", "Jacobian": "Jacobian([f,g], [x,y])", "SetCoordinates": "SetCoordinates(cartesian[x,y,z])", "VectorField": "VectorField(<P, Q, R>)", "LineInt": "LineInt(F, Path(<x(t),y(t)>, t=a..b))", "Flux": "Flux(F, Surface(...))", "seq": "seq(f(i), i=a..b)", "add": "add(f(i), i=a..b)", "map": "map(f, L)", "unapply": "unapply(e, x)", "piecewise": "piecewise(c1, f1, ..., f)", "with": "with(pakket)", "display": "display([p1, p2])", "pointplot": "pointplot([[x,y], ...])", "fieldplot": "fieldplot(<P,Q>, x=a..b, y=c..d)", "implicitplot": "implicitplot(vgl, x=a..b, y=c..d)", "collect": "collect(e, x)", "coeff": "coeff(p, x, n)", "rhs": "rhs(vgl)", "lhs": "lhs(vgl)", "assume": "assume(x > 0)", "printf": "printf(\"%a\\\\n\", e)"};
  fetch("/api/commands").then(function (r) { return r.json(); }).then(function (d) {
    cmds = (d.builtins || []).filter(function (n) { return /^[A-Za-z]/.test(n); });
    sigs = d.sigs || {};
    Object.keys(d.packages || {}).forEach(function (p) { (d.packages[p] || []).forEach(function (n) { pkgOf[n] = p; }); });
  }).catch(function () { cmds = []; });

  var box = document.createElement("div");
  box.className = "acbox"; box.setAttribute("role", "listbox"); box.hidden = true;
  document.body.appendChild(box);
  var items = [], sel = 0, ta = null, start = 0;

  function userNames() {
    var s = {};
    groups.querySelectorAll("textarea.code").forEach(function (t) {
      var re = /([A-Za-z_][A-Za-z0-9_]*)\s*(?:,\s*[A-Za-z_][A-Za-z0-9_]*\s*)*:=/g, m;
      while ((m = re.exec(t.value))) s[m[1]] = 1;
      var re2 = /with\(\s*([A-Za-z]+)/g;
      while ((m = re2.exec(t.value))) s["#pkg:" + m[1]] = 1;
    });
    return s;
  }
  function wordAt(t) {
    var p = t.selectionStart, v = t.value.slice(0, p), m = /[A-Za-z_][A-Za-z0-9_]*$/.exec(v);
    return m ? { w: m[0], s: p - m[0].length } : { w: "", s: p };
  }
  function candidates(w, force) {
    if (!cmds || (!force && w.length < 2)) return [];
    var u = userNames(), lw = w.toLowerCase(), out = [], seen = {};
    function add(n, kind) {
      if (seen[n] || n === w) return;
      if (n.toLowerCase().indexOf(lw) !== 0) return;
      seen[n] = 1; out.push({ n: n, k: kind });
    }
    Object.keys(u).forEach(function (n) { if (n.indexOf("#pkg:") !== 0) add(n, "var"); });
    var loaded = Object.keys(u).filter(function (k) { return k.indexOf("#pkg:") === 0; }).map(function (k) { return k.slice(5); });
    var a = cmds.slice().sort(function (x, y) {   // functies uit geladen pakketten eerst, dan kort voor lang
      var px = loaded.indexOf(pkgOf[x]) >= 0 ? 0 : 1, py = loaded.indexOf(pkgOf[y]) >= 0 ? 0 : 1;
      return px - py || x.length - y.length || (x < y ? -1 : 1);
    });
    a.forEach(function (n) { add(n, "fn"); });
    KW.forEach(function (n) { add(n, "kw"); });
    return out.slice(0, 12);
  }
  function caretXY(t, pos) {
    var cs = getComputedStyle(t), m = document.createElement("div");
    ["font", "lineHeight", "letterSpacing", "whiteSpace", "overflowWrap", "tabSize", "padding", "border", "boxSizing"].forEach(function (p) { m.style[p] = cs[p]; });
    m.style.position = "absolute"; m.style.visibility = "hidden"; m.style.width = t.clientWidth + "px";
    m.textContent = t.value.slice(0, pos);
    var sp = document.createElement("span"); sp.textContent = "​"; m.appendChild(sp);
    document.body.appendChild(m);
    var r = t.getBoundingClientRect(), x = r.left + sp.offsetLeft, y = r.top + sp.offsetTop + sp.offsetHeight;
    m.remove();
    return { x: x, y: y };
  }
  function render() {
    box.innerHTML = "";
    items.forEach(function (it, i) {
      var d = document.createElement("div");
      d.className = "acitem" + (i === sel ? " on" : ""); d.setAttribute("role", "option");
      var n = document.createElement("span"); n.className = "acn"; n.textContent = it.n; d.appendChild(n);
      var h = document.createElement("span"); h.className = "ach";
      h.textContent = it.k === "var" ? "eigen naam" : it.k === "kw" ? "sleutelwoord" : (SIG[it.n] || sigs[it.n] || pkgOf[it.n] || "");
      d.appendChild(h);
      d.addEventListener("mousedown", function (e) { e.preventDefault(); sel = i; accept(); });
      box.appendChild(d);
    });
    var on = box.children[sel]; if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest" });
  }
  function open(t, force) {
    var wa = wordAt(t), c = candidates(wa.w, force);
    if (!c.length) return close();
    ta = t; start = wa.s; items = c; sel = 0; render();
    var xy = caretXY(t, wa.s), vw = document.documentElement.clientWidth;
    box.hidden = false;
    var w = box.offsetWidth;
    box.style.left = Math.max(8, Math.min(xy.x, vw - w - 8)) + "px";
    var below = xy.y + 4, h = box.offsetHeight;
    box.style.top = (below + h > window.innerHeight - 8 ? Math.max(8, xy.y - 28 - h) : below) + "px";
  }
  function close() { box.hidden = true; items = []; ta = null; }
  function accept() {
    var it = items[sel]; if (!it || !ta) return close();
    var t = ta, p = t.selectionStart, v = t.value, ins = it.n, after = v.slice(p);
    var call = it.k === "fn" && after.charAt(0) !== "(";
    t.value = v.slice(0, start) + ins + (call ? "()" : "") + after;
    var c = start + ins.length + (call ? 1 : 0);
    t.setSelectionRange(c, c);
    t.dispatchEvent(new Event("input", { bubbles: true }));
    close();
  }
  groups.addEventListener("keydown", function (e) {
    var t = e.target;
    if (!t.classList || !t.classList.contains("code")) return;
    if (e.ctrlKey && (e.key === " " || e.code === "Space")) { e.preventDefault(); e.stopImmediatePropagation(); open(t, true); return; }
    if (box.hidden || t !== ta) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); e.stopImmediatePropagation();
      sel = (sel + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length; render();
    } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
      e.preventDefault(); e.stopImmediatePropagation(); accept();
    } else if (e.key === "Escape") {
      e.preventDefault(); e.stopImmediatePropagation(); close();
    }
  }, true);
  groups.addEventListener("input", function (e) {
    var t = e.target;
    if (!t.classList || !t.classList.contains("code")) return;
    if (e.inputType && e.inputType.indexOf("delete") === 0 && box.hidden) return;
    open(t, false);
  });
  groups.addEventListener("focusout", function () { setTimeout(function () { if (!box.contains(document.activeElement)) close(); }, 120); });
  window.addEventListener("resize", close);
  document.addEventListener("scroll", close, true);
})();
