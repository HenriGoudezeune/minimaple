(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var codeEl = $("code"), outEl = $("out"), histEl = $("hist"), runBtn = $("run");
  var HKEY = "minimaple.history", MAXH = 30;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function lsGet() { try { return JSON.parse(localStorage.getItem(HKEY) || "[]"); } catch (e) { return []; } }
  function lsSet(v) { try { localStorage.setItem(HKEY, JSON.stringify(v)); } catch (e) {} }

  function renderResult(r) {
    var box = el("div", "res");
    if (r.error) {
      box.classList.add("err");
      if (r.stmt) box.appendChild(el("div", "stmt", r.stmt));
      box.appendChild(el("pre", null, "Fout: " + r.error));
    } else if (r.show === false) {
      box.classList.add("quiet");
      box.textContent = (r.stmt || "") + "  (onderdrukt)";
    } else {
      if (r.latex && window.katex) {
        var t = el("div", "tex");
        try { window.katex.render(r.latex, t, { throwOnError: true, displayMode: false }); box.appendChild(t); }
        catch (e) { box.appendChild(el("pre", null, r.text || "")); r.text = null; }
      }
      if (r.text != null && (r.text !== "" || !r.latex)) box.appendChild(el("pre", null, r.text));
    }
    (r.plots || []).forEach(function (src) {
      var img = el("img"); img.src = src; img.alt = "plot"; box.appendChild(img);
    });
    return box;
  }

  function addCell(code, results) {
    var empty = outEl.querySelector(".empty"); if (empty) empty.remove();
    var cell = el("article", "card cell");
    var head = el("div", "in");
    head.appendChild(el("span", null, code));
    var re = el("button", "btn ghost small", "Opnieuw"); re.type = "button";
    re.onclick = function () { codeEl.value = code; codeEl.focus(); };
    head.appendChild(re);
    cell.appendChild(head);
    results.forEach(function (r) { cell.appendChild(renderResult(r)); });
    outEl.insertBefore(cell, outEl.firstChild);
  }

  function renderHist() {
    var h = lsGet(); histEl.textContent = "";
    if (!h.length) { histEl.appendChild(el("p", "empty", "Leeg.")); return; }
    h.forEach(function (c) {
      var b = el("button", "hist", c.replace(/\s+/g, " ")); b.type = "button"; b.title = c;
      b.onclick = function () { codeEl.value = c; codeEl.focus(); window.scrollTo({ top: 0, behavior: "smooth" }); };
      histEl.appendChild(b);
    });
  }
  function pushHist(c) {
    var h = lsGet().filter(function (x) { return x !== c; });
    h.unshift(c); lsSet(h.slice(0, MAXH)); renderHist();
  }

  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json(); });
  }

  function run() {
    var code = codeEl.value.trim();
    if (!code || runBtn.disabled) return;
    runBtn.disabled = true;
    post("/api/eval", { code: code }).then(function (d) {
      addCell(code, d.results || [{ stmt: code, error: d.error || "onbekende fout" }]);
      pushHist(code);
    }).catch(function (e) {
      addCell(code, [{ stmt: code, error: String(e) }]);
    }).then(function () { runBtn.disabled = false; });
  }

  runBtn.onclick = run;
  codeEl.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); }
  });
  $("reset").onclick = function () {
    post("/api/reset", {}).then(function () {
      addCell("(sessie gereset)", [{ stmt: "", show: true, text: "Alle definities gewist.", latex: null }]);
    });
  };
  $("clear").onclick = function () { outEl.textContent = ""; outEl.appendChild(el("p", "empty", "Nog niets uitgevoerd.")); };
  $("clearhist").onclick = function () { lsSet([]); renderHist(); };

  fetch("/api/examples").then(function (r) { return r.json(); }).then(function (ex) {
    var box = $("examples");
    ex.forEach(function (x, i) {
      var t = el("button", "tile"); t.type = "button";
      t.style.setProperty("--chip", "var(--c" + (i % 10) + ")");
      t.appendChild(el("span", "mono", "Voorbeeld " + (i + 1)));
      t.appendChild(el("b", null, x.title));
      t.onclick = function () { codeEl.value = x.code; codeEl.focus(); };
      box.appendChild(t);
    });
  });
  renderHist();
})();
