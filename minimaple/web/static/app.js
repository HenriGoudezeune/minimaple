/* mini-Maple worksheet-UI. Eigen implementatie; geen externe code behalve KaTeX. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var groupsEl = $("groups"), noticeEl = $("notice"), sheetEl = $("sheet"), dlg = $("dlg");
  var LS = "minimaple.ws", LSPAL = "minimaple.pal";
  var mobile = window.matchMedia("(max-width:760px)");
  var S = { name: "naamloos", dirty: false, label: 0, queue: [], busy: false, stopping: false,
            ctrl: null, cur: null, lastInput: null, cmds: null };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function lsGet(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json(); });
  }

  // ------------------------------------------------------------------ status
  function setStatus(txt, kind) {
    $("st-state").textContent = txt;
    var s = $("status"); s.classList.toggle("busy", kind === "busy"); s.classList.toggle("bad", kind === "bad");
    document.querySelector('.tb[data-cmd="stop"]').disabled = !(S.busy || S.queue.length);
  }
  function info() {
    var all = groupsEl.children.length, inp = groupsEl.querySelectorAll(".grp-in").length;
    $("st-info").textContent = inp + " invoergroepen, " + (all - inp) + " tekstblokken";
  }
  function setName(n) {
    S.name = n || "naamloos";
    $("docname").textContent = S.name;
    document.title = S.name + " - mini-Maple";
  }

  // ------------------------------------------------------------------ groepen
  function autosize(ta) { ta.style.height = "0px"; ta.style.height = ta.scrollHeight + "px"; }

  function makeGroup(type, code) {
    var g = el("section", "grp " + (type === "text" ? "grp-text" : "grp-in"));
    g.dataset.type = type;
    var ta;
    if (type === "text") {
      var view = el("div", "md"); view.tabIndex = 0; view.setAttribute("role", "button");
      view.setAttribute("aria-label", "Tekstblok, klik om te bewerken");
      ta = el("textarea", "txt"); ta.hidden = true; ta.rows = 1;
      ta.placeholder = "Tekst: # kop, **vet**, *cursief*, `code`, $x^2$";
      ta.value = code || "";
      g.appendChild(view); g.appendChild(ta);
      renderText(g);
    } else {
      var row = el("div", "in-row"), p = el("span", "prompt", ">");
      p.setAttribute("aria-hidden", "true");
      ta = el("textarea", "code"); ta.rows = 1; ta.spellcheck = false;
      ["autocapitalize", "autocomplete", "autocorrect"].forEach(function (a) { ta.setAttribute(a, "off"); });
      ta.setAttribute("aria-label", "Maple-invoer");
      ta.value = code || "";
      row.appendChild(p); row.appendChild(ta); g.appendChild(row);
      g.appendChild(el("div", "out"));
    }
    return g;
  }
  function ta(g) { return g.querySelector("textarea"); }
  function codeOf(g) { return ta(g).value; }
  function groups() { return Array.prototype.slice.call(groupsEl.children); }
  function inputs() { return groups().filter(function (g) { return g.dataset.type === "input"; }); }

  function insertGroup(type, ref, where, code) {
    var g = makeGroup(type, code);
    if (!ref) groupsEl.appendChild(g);
    else if (where === "before") groupsEl.insertBefore(g, ref);
    else groupsEl.insertBefore(g, ref.nextSibling);
    if (type === "input") autosize(ta(g));
    changed(); info();
    return g;
  }
  function focusGroup(g, atEnd) {
    if (!g) return;
    if (g.dataset.type === "text") { editText(g); return; }
    var t = ta(g); t.focus();
    var n = atEnd === false ? 0 : t.value.length;
    try { t.setSelectionRange(n, n); } catch (e) {}
    keepVisible(g);
  }
  function keepVisible(g) {
    var r = g.getBoundingClientRect(), s = sheetEl.getBoundingClientRect();
    if (r.top < s.top + 8 || r.bottom > s.bottom - 40) g.scrollIntoView({ block: "nearest" });
  }
  function setCurrent(g) {
    if (S.cur === g) return;
    if (S.cur) S.cur.classList.remove("cur");
    S.cur = g; if (g) g.classList.add("cur");
    if (g && g.dataset.type === "input") S.lastInput = g;
  }
  function loadGroups(list) {
    groupsEl.textContent = ""; S.cur = S.lastInput = null;
    (list || []).forEach(function (x) {
      var g = makeGroup(x.type === "text" ? "text" : "input", x.code || "");
      groupsEl.appendChild(g);
    });
    if (!inputs().length) groupsEl.appendChild(makeGroup("input", ""));
    inputs().forEach(function (g) { autosize(ta(g)); });
    info();
  }
  function serialize() {
    return groups().map(function (g) { return { type: g.dataset.type, code: codeOf(g) }; });
  }
  var saveT = null;
  function changed() {
    S.dirty = true;
    clearTimeout(saveT);
    saveT = setTimeout(function () { lsSet(LS, { name: S.name, groups: serialize() }); }, 400);
  }
  function hasContent() { return groups().some(function (g) { return codeOf(g).trim(); }); }

  // ------------------------------------------------------------------ markdown-light
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function tex(src, display) {
    if (!window.katex) return "<code>" + esc(src) + "</code>";
    try { return window.katex.renderToString(src, { throwOnError: true, displayMode: display }); }
    catch (e) { return "<code>" + esc(src) + "</code>"; }
  }
  function inline(s) {
    var keep = [];
    function hold(h) { keep.push(h); return "\u0000" + (keep.length - 1) + "\u0000"; }
    s = s.replace(/`([^`]+)`/g, function (_, c) { return hold("<code>" + esc(c) + "</code>"); });
    s = s.replace(/\$\$([^$]+)\$\$/g, function (_, m) { return hold(tex(m, true)); });
    s = s.replace(/\$([^$\n]+)\$/g, function (_, m) { return hold(tex(m, false)); });
    s = esc(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[\s(])\*([^\s*][^*]*)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
    return s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return keep[+i]; });
  }
  function markdown(src) {
    var out = [], list = null;
    function close() { if (list) { out.push("</" + list + ">"); list = null; } }
    src.replace(/\r/g, "").split(/\n\s*\n/).forEach(function (block) {
      var lines = block.split("\n"), para = [];
      function flushP() { if (para.length) { out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; } }
      lines.forEach(function (l) {
        var m;
        if ((m = /^(#{1,4})\s+(.*)$/.exec(l))) { flushP(); close(); out.push("<h" + m[1].length + ">" + inline(m[2]) + "</h" + m[1].length + ">"); }
        else if ((m = /^\s*[-*]\s+(.*)$/.exec(l))) { flushP(); if (list !== "ul") { close(); out.push("<ul>"); list = "ul"; } out.push("<li>" + inline(m[1]) + "</li>"); }
        else if ((m = /^\s*\d+[.)]\s+(.*)$/.exec(l))) { flushP(); if (list !== "ol") { close(); out.push("<ol>"); list = "ol"; } out.push("<li>" + inline(m[1]) + "</li>"); }
        else if (l.trim()) { close(); para.push(l); }
      });
      flushP(); close();
    });
    return out.join("");
  }
  function renderText(g) {
    var view = g.querySelector(".md"), t = ta(g);
    view.innerHTML = markdown(t.value);
    view.hidden = false; t.hidden = true;
  }
  function editText(g) {
    var view = g.querySelector(".md"), t = ta(g);
    view.hidden = true; t.hidden = false; autosize(t); t.focus();
    setCurrent(g); keepVisible(g);
  }

  // ------------------------------------------------------------------ uitvoer
  function renderResults(out, results) {
    out.textContent = "";
    var multi = results.length > 1;
    results.forEach(function (r) {
      if (r.error) {
        var e = el("div", "res err"), pre = el("pre");
        if (multi && r.stmt) pre.appendChild(el("span", "stmt", r.stmt));
        pre.appendChild(document.createTextNode(/^(Error|Warning)\b/.test(r.error) ? r.error : "Error, " + r.error));
        e.appendChild(pre); out.appendChild(e);
      } else if (r.show !== false) {
        var txt = r.text, hasMath = r.latex && window.katex && !(/^\\text\{/.test(r.latex) && txt);
        if (hasMath || txt) {
          var box = el("div", "res"), m = el("div", "math");
          if (hasMath) {
            try { window.katex.render(r.latex, m, { throwOnError: true, displayMode: true }); }
            catch (x) { m.textContent = ""; m.appendChild(el("pre", null, txt || r.latex)); }
            box.appendChild(m);
            S.label += 1; box.appendChild(el("span", "lbl", "(" + S.label + ")"));
          } else if (r.latex) {              // procedures e.d.: als tekst, gecentreerd
            m.appendChild(el("pre", null, txt)); box.appendChild(m);
            S.label += 1; box.appendChild(el("span", "lbl", "(" + S.label + ")"));
          } else {
            box.appendChild(el("pre", null, txt));   // print/printf-uitvoer
          }
          out.appendChild(box);
        }
      }
      if (r.show !== false) (r.plots || []).forEach(function (src) {
        var img = el("img", "plot"); img.src = src; img.alt = "plot"; img.loading = "lazy"; out.appendChild(img);
      });
    });
  }
  function helpBox(text) { return el("div", "helpbox", text); }
  function getHelp(name) {
    return fetch("/api/help?name=" + encodeURIComponent(name.trim())).then(function (r) { return r.json(); });
  }

  // ------------------------------------------------------------------ evalueren
  function enqueue(g) {
    if (!g || g.dataset.type !== "input" || S.queue.indexOf(g) >= 0) return;
    S.queue.push(g); g.classList.add("queued"); pump();
  }
  function pump() {
    if (S.busy) return;
    var g = S.queue.shift();
    if (!g) return setStatus(S.lastBad ? "Ready (fout)" : "Ready", S.lastBad ? "bad" : "");
    if (!g.isConnected) return pump();
    evalGroup(g).then(pump);
  }
  function evalGroup(g) {
    g.classList.remove("queued");
    var code = codeOf(g).trim(), out = g.querySelector(".out");
    if (!code) { out.textContent = ""; return Promise.resolve(); }
    if (code.charAt(0) === "?") {
      g.classList.add("busy");
      return getHelp(code.slice(1).replace(/[;:]\s*$/, "")).then(function (d) {
        out.textContent = ""; out.appendChild(helpBox(d.text)); S.lastBad = false;
      }).catch(function (e) { renderResults(out, [{ error: String(e) }]); })
        .then(function () { g.classList.remove("busy"); });
    }
    if (/^restart\s*[;:]/.test(code)) S.label = 0;
    S.lastBad = false;
    S.busy = true; g.classList.add("busy"); setStatus("Evaluating…", "busy");
    var t0 = performance.now();
    S.ctrl = window.AbortController ? new AbortController() : null;
    var tries = 0;
    function call() {   // bij 429 (rate limit) even wachten en opnieuw, zodat "Alles uitvoeren" op grote werkbladen lukt
      return fetch("/api/eval", { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ code: code }), signal: S.ctrl ? S.ctrl.signal : undefined })
        .then(function (r) {
          if (r.status === 429 && tries++ < 30 && !S.stopping) {
            setStatus("Wachten (te veel verzoeken)…", "busy");
            return new Promise(function (ok) { setTimeout(ok, 3000); }).then(function () {
              if (S.stopping) throw new Error("stopped");
              setStatus("Evaluating…", "busy"); return call();
            });
          }
          return r.json();
        });
    }
    return call()
      .then(function (d) { renderResults(out, d.results || [{ error: d.error || "unknown error" }]); return !d.results; })
      .catch(function (e) {
        renderResults(out, [{ error: S.stopping ? "computation interrupted (Stop); session reset, earlier definitions lost." : String(e) }]);
        return true;
      })
      .then(function (bad) {
        S.busy = false; S.ctrl = null; g.classList.remove("busy");
        var dt = (performance.now() - t0) / 1000;
        $("st-time").textContent = "laatste: " + (dt < 10 ? dt.toFixed(2) : dt.toFixed(1)) + " s";
        S.lastBad = !!(bad || out.querySelector(".err"));
      });
  }
  function runCurrent(advance) {
    var g = S.cur && S.cur.dataset.type === "input" ? S.cur : S.lastInput;
    if (!g || !g.isConnected) g = inputs()[0];
    if (!g) return;
    enqueue(g);
    if (!advance) return;
    var n = g.nextElementSibling;
    while (n && n.dataset.type !== "input") n = n.nextElementSibling;
    if (!n) n = insertGroup("input", g.nextElementSibling && groupsEl.lastElementChild || g, "after");
    focusGroup(n);
  }
  function runAll() {
    S.label = 0;
    inputs().forEach(function (g) { if (codeOf(g).trim()) enqueue(g); });
  }
  function stop() {
    S.queue.forEach(function (g) { g.classList.remove("queued"); }); S.queue = [];
    if (!S.busy) return setStatus("Ready");
    S.stopping = true;
    post("/api/stop").catch(function () {}).then(function () {
      if (S.ctrl) S.ctrl.abort();
      S.label = 0;
      setTimeout(function () { S.stopping = false; }, 500);
    });
  }
  function restart() {
    stop();
    post("/api/reset").then(function () {
      S.label = 0; setStatus("Ready (restarted)");
      flash("Restart: alle definities zijn gewist. De uitvoer blijft staan.");
    });
  }

  // ------------------------------------------------------------------ meldingen
  function notice(html, bad, actions) {
    noticeEl.innerHTML = ""; noticeEl.hidden = false; noticeEl.classList.toggle("bad", !!bad);
    var t = el("span"); t.innerHTML = html; noticeEl.appendChild(t);
    noticeEl.appendChild(el("span", "sp"));
    (actions || []).forEach(function (a) {
      var b = el("button", "nbtn" + (a.primary ? " primary" : ""), a.label); b.type = "button";
      b.onclick = function () { a.fn(); }; noticeEl.appendChild(b);
    });
    var x = el("button", "nbtn", "Sluiten"); x.type = "button";
    x.onclick = function () { noticeEl.hidden = true; }; noticeEl.appendChild(x);
  }
  var flashT;
  function flash(msg) { notice(esc(msg)); clearTimeout(flashT); flashT = setTimeout(function () { noticeEl.hidden = true; }, 4000); }

  // ------------------------------------------------------------------ bestanden
  function openFile(f) {
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) return notice("Bestand te groot (max 5 MB).", true);
    if (S.dirty && hasContent() && !window.confirm("Het huidige werkblad vervangen door " + f.name + "?")) return;
    parseAndShow(f.name, f);
  }
  function parseAndShow(fname, body) {
    var f = { name: fname };
    setStatus("Openen…", "busy");
    fetch("/api/open?name=" + encodeURIComponent(f.name), { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: body })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) { setStatus("Ready", "bad"); return notice("Kon " + esc(f.name) + " niet openen: " + esc(d.error), true); }
        stop(); post("/api/reset"); S.label = 0;
        loadGroups(d.groups); setName(f.name); S.dirty = false;
        lsSet(LS, { name: S.name, groups: serialize() });
        sheetEl.scrollTop = 0;
        var nIn = inputs().length, nTx = groups().length - nIn;
        var html = "<b>" + esc(f.name) + "</b> geopend: " + nIn + " invoergroepen, " + nTx + " tekstblokken. Nog niets uitgevoerd.";
        if (d.warnings && d.warnings.length) html += "<ul>" + d.warnings.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") + "</ul>";
        notice(html, false, [{ label: "Alles uitvoeren", primary: true, fn: function () { noticeEl.hidden = true; runAll(); } }]);
        setStatus("Ready");
      })
      .catch(function (e) { setStatus("Ready", "bad"); notice("Openen mislukt: " + esc(String(e)), true); });
  }
  function xmlEsc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function toMpl(list) {
    return list.filter(function (g) { return g.code.trim(); }).map(function (g) {
      var c = g.code.replace(/\s+$/, "");
      if (g.type === "text") return c.split("\n").map(function (l) { return l.trim() ? "# " + l : "#"; }).join("\n");
      c = c.split("\n").filter(function (l) { return l.trim(); }).join("\n");
      var last = c.split("\n").pop().trim();
      if (!/[;:]$/.test(c) && last.charAt(0) !== "#") c += ";";
      return c;
    }).join("\n\n") + "\n";
  }
  function toMw(list) {
    var rows = ['<?xml version="1.0" encoding="UTF-8"?>', "<Worksheet>", '<Version major="2025" minor="2"/>'];
    list.forEach(function (g) {
      var c = g.code.replace(/\s+$/, "");
      if (!c.trim()) return;
      if (g.type === "text") {
        c.split(/\n\s*\n/).forEach(function (p) {
          p = p.trim(); if (!p) return;
          var m = /^(#{1,4})\s+([\s\S]*)$/.exec(p), st = m ? "Heading " + m[1].length : "Text";
          rows.push('<Group view="presentation"><Input><Text-field style="' + st + '" layout="' + (m ? st : "Normal") + '">' + xmlEsc(m ? m[2] : p) + "</Text-field></Input></Group>");
        });
      } else {
        rows.push('<Group view="code"><Input><Text-field prompt="&gt; " style="Maple Input" layout="Normal">' + xmlEsc(c) + "</Text-field></Input></Group>");
      }
    });
    rows.push("</Worksheet>");
    return rows.join("\n") + "\n";
  }
  function baseName() { return (S.name || "naamloos").replace(/\.(mw|mpl|txt|mm|maple|html)$/i, "") || "naamloos"; }
  function download(text, name, type) {
    var a = el("a"); a.href = URL.createObjectURL(new Blob([text], { type: type }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    S.dirty = false;
  }
  function exportHtml() {
    var body = groups().map(function (g) {
      if (g.dataset.type === "text") return '<div class="t">' + markdown(codeOf(g)) + "</div>";
      var out = g.querySelector(".out").innerHTML;
      return '<div class="g"><pre class="i">&gt; ' + esc(codeOf(g)) + "</pre>" + out + "</div>";
    }).join("\n");
    var css = "body{font:16px/1.55 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d1d1f}" +
      ".i{color:#c8102e;font:14px/1.5 ui-monospace,monospace;white-space:pre-wrap;margin:10px 0 4px}" +
      ".res{display:flex;align-items:center;gap:10px}.math{flex:1;text-align:center;color:#0040dd;overflow-x:auto}" +
      ".lbl{color:#6e6e73;font:12px monospace}.res pre{white-space:pre-wrap}.err pre{color:#d70015}" +
      ".plot{display:block;margin:8px auto;max-width:100%}.helpbox{white-space:pre-wrap;font:13px monospace;background:#f5f5f7;padding:8px}";
    download('<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
      "<title>" + esc(baseName()) + '</title><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.11/katex.min.css">' +
      "<style>" + css + "</style></head><body>" + body + "</body></html>", baseName() + ".html", "text/html");
  }
  function newSheet() {
    if (S.dirty && hasContent() && !window.confirm("Nieuw werkblad? Niet-opgeslagen werk gaat verloren.")) return;
    stop(); post("/api/reset"); S.label = 0;
    loadGroups([]); setName("naamloos"); S.dirty = false; noticeEl.hidden = true;
    lsSet(LS, { name: S.name, groups: serialize() });
    focusGroup(inputs()[0]);
  }

  // ------------------------------------------------------------------ dialoog / help
  function openDialog(title, build) {
    $("dlg-title").textContent = title;
    var b = $("dlg-body"); b.textContent = ""; build(b);
    if (!dlg.open) { if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", ""); }
  }
  dlg.addEventListener("click", function (e) {
    if (e.target === dlg || e.target.hasAttribute("data-close")) dlg.close();
  });
  function loadCmds() {
    if (S.cmds) return Promise.resolve(S.cmds);
    return fetch("/api/commands").then(function (r) { return r.json(); }).then(function (d) { S.cmds = d; return d; });
  }
  function helpDialog(name) {
    openDialog("Help", function (b) {
      var inp = el("input"); inp.type = "search"; inp.placeholder = "commando, bv. diff"; inp.value = name || "";
      inp.setAttribute("aria-label", "Commando");
      var pre = el("pre", null, "Typ een commando en druk op Enter. In een invoergroep werkt ook ?diff");
      var chips = el("div", "chips");
      b.appendChild(inp); b.appendChild(pre); b.appendChild(chips);
      function show(n) {
        inp.value = n;
        getHelp(n).then(function (d) { pre.textContent = d.text; }).catch(function (e) { pre.textContent = String(e); });
      }
      inp.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); show(inp.value); } });
      inp.addEventListener("input", function () { filter(inp.value); });
      function filter(q) {
        q = q.trim().toLowerCase();
        Array.prototype.forEach.call(chips.querySelectorAll("button"), function (c) {
          c.hidden = q && c.textContent.toLowerCase().indexOf(q) < 0;
        });
      }
      loadCmds().then(function (d) {
        d.builtins.filter(function (n) { return n.charAt(0) !== "_"; }).forEach(function (n) {
          var c = el("button", null, n); c.type = "button"; c.onclick = function () { show(n); }; chips.appendChild(c);
        });
        filter(inp.value);
      });
      if (name) show(name);
      setTimeout(function () { inp.focus(); }, 30);
    });
  }
  function commandsDialog() {
    openDialog("Alle commando's", function (b) {
      var chips = el("div", "chips"); b.appendChild(chips);
      loadCmds().then(function (d) {
        Object.keys(d.packages).sort().forEach(function (p) {
          chips.appendChild(el("h4", null, p + "  (with(" + p + "))"));
          d.packages[p].forEach(function (n) {
            if (n.charAt(0) === "_") return;
            var c = el("button", null, n); c.type = "button"; c.onclick = function () { helpDialog(n); }; chips.appendChild(c);
          });
        });
        chips.appendChild(el("h4", null, "Ingebouwd (zonder pakket)"));
        var inPk = {}; Object.keys(d.packages).forEach(function (p) { d.packages[p].forEach(function (n) { inPk[n] = 1; }); });
        d.builtins.forEach(function (n) {
          if (inPk[n] || n.charAt(0) === "_") return;
          var c = el("button", null, n); c.type = "button"; c.onclick = function () { helpDialog(n); }; chips.appendChild(c);
        });
      });
    });
  }
  var KEYS = [
    ["Enter", "Groep uitvoeren en naar de volgende invoergroep"], ["Shift+Enter", "Nieuwe regel in dezelfde groep"],
    ["Ctrl+Shift+Enter", "Hele worksheet uitvoeren"], ["Ctrl+J / Ctrl+K", "Invoergroep erna / ervoor"],
    ["Alt+↑ / Alt+↓", "Groep verplaatsen"], ["↑ / ↓", "Naar de vorige/volgende groep (op de eerste/laatste regel)"],
    ["Ctrl+Del", "Groep verwijderen"], ["Ctrl+O / Ctrl+S", "Openen / opslaan als .mw"],
    ["F1", "Help bij het woord onder de cursor"], ["?naam", "Help in de worksheet, bv. ?dsolve"],
    ["Esc", "Tekstblok klaar / menu of dialoog sluiten"]];
  function keysDialog() {
    openDialog("Sneltoetsen", function (b) {
      var t = el("table", "keys");
      KEYS.forEach(function (k) { var tr = el("tr"); tr.appendChild(el("td", null, k[0])); tr.appendChild(el("td", null, k[1])); t.appendChild(tr); });
      b.appendChild(t);
    });
  }
  function examplesDialog() {
    openDialog("Voorbeelden", function (b) {
      var box = el("div", "exlist"); b.appendChild(box);
      b.insertBefore(el("p", null, "Wordt ingevoegd na de huidige groep, elke regel als eigen invoergroep."), box);
      fetch("/api/examples").then(function (r) { return r.json(); }).then(function (ex) {
        ex.forEach(function (x) {
          var btn = el("button"); btn.type = "button";
          btn.appendChild(el("b", null, x.title)); btn.appendChild(el("small", null, x.code.replace(/\n/g, "  ")));
          btn.onclick = function () {
            dlg.close();
            var ref = S.cur, first = null;
            ref = insertGroup("text", ref, "after", "## " + x.title);
            x.code.split("\n").forEach(function (l) { if (l.trim()) { ref = insertGroup("input", ref, "after", l); first = first || ref; } });
            focusGroup(first);
          };
          box.appendChild(btn);
        });
      });
    });
  }
  function aboutDialog() {
    openDialog("Over mini-Maple", function (b) {
      b.innerHTML = "<p>Een eigen computeralgebra-notebook met Maple-syntax, gebouwd op SymPy. Geen Maple-code of -onderdelen.</p>" +
        "<p>Opent .mw-werkbladen (enkel invoer en tekst; uitvoer wordt opnieuw uitgerekend) en .mpl/.txt. Bewaart als .mw of .mpl, op je eigen toestel.</p>" +
        "<p>Stop doodt het rekenproces: de sessie (alle definities) gaat dan verloren.</p>";
    });
  }
  function wordAtCursor() {
    var t = document.activeElement;
    if (!t || t.tagName !== "TEXTAREA") return "";
    var v = t.value, i = t.selectionStart, a = i, z = i;
    while (a > 0 && /[\w]/.test(v.charAt(a - 1))) a--;
    while (z < v.length && /[\w]/.test(v.charAt(z))) z++;
    return v.slice(a, z);
  }

  // ------------------------------------------------------------------ paletten
  var P = [
    ["Expressie", [["a/b", "(«a»)/(«b»)"], ["xⁿ", "«x»^«n»"], ["√x", "sqrt(«x»)"], ["|x|", "abs(«x»)"], ["eˣ", "exp(«x»)"], ["ln", "ln(«x»)"],
      ["sin", "sin(«x»)"], ["cos", "cos(«x»)"], ["tan", "tan(«x»)"], ["arctan", "arctan(«x»)"], ["f := x →", "«f» := «x» -> «x^2»;"], [":=", "«a» := «expr»;"],
      ["solve", "solve(«x^2 - 1 = 0», «x»)"], ["fsolve", "fsolve(«cos(x) = x», «x» = «0»..«1»)"], ["simplify", "simplify(«expr»)"], ["expand", "expand(«expr»)"],
      ["factor", "factor(«expr»)"], ["subs", "subs(«x» = «a», «expr»)"], ["eval", "eval(«expr», «x» = «a»)"], ["evalf", "evalf(«expr»)"],
      ["π", "Pi"], ["i", "I"], ["∞", "infinity"], ["e", "exp(1)"]]],
    ["Calculus", [["d/dx", "diff(«f», «x»)"], ["d²/dx²", "diff(«f», «x», «x»)"], ["∂²/∂x∂y", "diff(«f», «x», «y»)"], ["∫ dx", "int(«f», «x»)"],
      ["∫ₐᵇ dx", "int(«f», «x» = «a»..«b»)"], ["∫∫", "int(int(«f», «x» = «0»..«1»), «y» = «0»..«1»)"], ["lim", "limit(«f», «x» = «0»)"],
      ["Σ", "sum(«f», «k» = «1»..«n»)"], ["Π", "product(«f», «k» = «1»..«n»)"], ["series", "series(«f», «x» = «0», «6»)"],
      ["taylor", "taylor(«f», «x» = «0», «6»)"], ["Int (inert)", "Int(«f», «x» = «a»..«b»)"], ["evalf(Int)", "evalf(Int(«f», «x» = «0»..«1»))"], ["D(f)", "D(«f»)"]]],
    ["Lineaire algebra", [["with", "with(LinearAlgebra):"], ["Matrix 2×2", "Matrix([[«a», «b»], [«c», «d»]])"], ["Matrix 3×3", "Matrix([[«1», 0, 0], [0, 1, 0], [0, 0, 1]])"],
      ["kolom <a,b>", "<«a», «b», «c»>"], ["rij <a|b>", "<«a» | «b» | «c»>"], ["A . B", "«A» . «B»"], ["det", "Determinant(«A»)"], ["A⁻¹", "MatrixInverse(«A»)"],
      ["Aᵀ", "Transpose(«A»)"], ["rang", "Rank(«A»)"], ["eigenw.", "Eigenvalues(«A»)"], ["eigenv.", "Eigenvectors(«A»)"], ["Ax = b", "LinearSolve(«A», «b»)"],
      ["RREF", "ReducedRowEchelonForm(«A»)"], ["nulruimte", "NullSpace(«A»)"], ["u · v", "DotProduct(«u», «v»)"], ["u × v", "CrossProduct(«u», «v»)"],
      ["|v|", "Norm(«v», 2)"], ["sing. w.", "SingularValues(«A»)"], ["I(n)", "IdentityMatrix(«3»)"]]],
    ["Vectoranalyse", [["with", "with(VectorCalculus):"], ["coörd.", "SetCoordinates('cartesian'[x, y, z]):"], ["veld F", "«F» := VectorField(<«x*y», «y*z», «z*x»>);"],
      ["∇f", "Gradient(«f», [x, y, z])"], ["div", "Divergence(«F»)"], ["rot", "Curl(«F»)"], ["Δf", "Laplacian(«f», [x, y, z])"],
      ["potentiaal", "ScalarPotential(«F»)"], ["Jacobiaan", "Jacobian([«f», «g»], [x, y])"], ["Hessiaan", "Hessian(«f», [x, y])"]]],
    ["DV's", [["y′", "diff(y(x), x)"], ["y″", "diff(y(x), x, x)"], ["dsolve", "dsolve(«diff(y(x), x) = y(x)», y(x))"],
      ["met BV", "dsolve({«diff(y(x), x) = y(x)», y(0) = «1»}, y(x))"], ["2e orde", "dsolve(diff(y(x), x, x) + «2»*diff(y(x), x) + «5»*y(x) = «0», y(x))"],
      ["stelsel", "dsolve({diff(x(t), t) = «y(t)», diff(y(t), t) = «-x(t)»}, {x(t), y(t)})"],
      ["numeriek", "«sol» := dsolve({«diff(y(x), x) = -y(x)», y(0) = «1»}, y(x), numeric);"], ["odeplot", "plots:-odeplot(«sol», x = 0..«5»)"],
      ["pdsolve", "pdsolve(«diff(u(x, t), t) = diff(u(x, t), x)», u(x, t))"]]],
    ["Transformaties", [["with", "with(inttrans):"], ["laplace", "laplace(«f», t, s)"], ["invlaplace", "invlaplace(«F», s, t)"],
      ["fourier", "fourier(«f», t, w)"], ["invfourier", "invfourier(«F», w, t)"], ["Heaviside", "Heaviside(«t»)"], ["Dirac", "Dirac(«t»)"]]],
    ["Plots", [["with", "with(plots):"], ["plot", "plot(«sin(x)», «x» = «-5»..«5»)"], ["meerdere", "plot([«sin(x)», «cos(x)»], x = «-5»..«5», color = [red, blue])"],
      ["parametr.", "plot([cos(t), sin(t), t = 0..2*Pi])"], ["plot3d", "plot3d(«x^2 - y^2», x = «-2»..«2», y = «-2»..«2»)"],
      ["impliciet", "plots:-implicitplot(«x^2 + y^2 = 1», x = «-2»..«2», y = «-2»..«2»)"], ["contour", "plots:-contourplot(«x^2 + y^2», x = «-2»..«2», y = «-2»..«2»)"],
      ["vectorveld", "plots:-fieldplot([«-y», «x»], x = «-2»..«2», y = «-2»..«2»)"], ["ruimtekr.", "plots:-spacecurve([cos(t), sin(t), t], t = 0..«4*Pi»)"],
      ["polair", "plots:-polarplot(«1 + cos(t)», t = 0..2*Pi)"], ["punten", "plots:-pointplot([[0, 0], [1, 1], [2, 4]])"], ["display", "plots:-display(«p1», «p2»)"]]],
    ["Griekse letters", "alpha:α beta:β gamma:γ delta:δ epsilon:ε zeta:ζ eta:η theta:θ kappa:κ lambda:λ mu:μ nu:ν xi:ξ pi:π rho:ρ sigma:σ tau:τ phi:φ chi:χ psi:ψ omega:ω Gamma:Γ Delta:Δ Theta:Θ Lambda:Λ Sigma:Σ Phi:Φ Psi:Ψ Omega:Ω"
      .split(" ").map(function (s) { var p = s.split(":"); return [p[1], p[0]]; })]];

  function buildPalettes() {
    var openState = lsGet(LSPAL, { "Expressie": 1, "Calculus": 1 }), box = $("palettes");
    P.forEach(function (p) {
      var d = el("details", "pal" + (p[0] === "Griekse letters" ? " greek" : "")); d.open = !!openState[p[0]];
      var s = el("summary", null, p[0]); d.appendChild(s);
      d.addEventListener("toggle", function () { openState[p[0]] = d.open ? 1 : 0; lsSet(LSPAL, openState); });
      var items = el("div", "items");
      p[1].forEach(function (it) {
        var b = el("button", null, it[0]); b.type = "button";
        b.title = it[1].replace(/[«»]/g, ""); b.dataset.tpl = it[1];
        items.appendChild(b);
      });
      d.appendChild(items); box.appendChild(d);
    });
    box.addEventListener("mousedown", function (e) { if (e.target.dataset.tpl) e.preventDefault(); }); // focus in de invoer houden
    box.addEventListener("click", function (e) {
      var t = e.target.dataset && e.target.dataset.tpl;
      if (t) { insertTemplate(t); if (mobile.matches) toggleSide(false); }
    });
    $("palsearch").addEventListener("input", function () {
      var q = this.value.trim().toLowerCase();
      Array.prototype.forEach.call(box.querySelectorAll(".pal"), function (d) {
        var any = false;
        Array.prototype.forEach.call(d.querySelectorAll(".items button"), function (b) {
          var hit = !q || (b.textContent + " " + b.title).toLowerCase().indexOf(q) >= 0;
          b.hidden = !hit; any = any || hit;
        });
        d.hidden = !any; if (q && any) d.open = true;
      });
    });
  }
  function insertTemplate(tpl) {
    var g = S.cur && S.cur.dataset.type === "input" && S.cur.isConnected ? S.cur : null;
    if (!g) g = insertGroup("input", S.cur, "after");
    var t = ta(g), a = t.selectionStart, z = t.selectionEnd, sel = t.value.slice(a, z);
    var marks = [], text = "", i = 0, re = /«([^»]*)»/g, m, k = 0;
    while ((m = re.exec(tpl))) {
      text += tpl.slice(i, m.index);
      var fill = (k === 0 && sel) ? sel : m[1];
      marks.push([a + text.length, a + text.length + fill.length]);
      text += fill; i = re.lastIndex; k++;
    }
    text += tpl.slice(i);
    t.focus();
    t.setSelectionRange(a, z);
    if (!document.execCommand || !document.execCommand("insertText", false, text)) {   // execCommand houdt undo intact
      t.value = t.value.slice(0, a) + text + t.value.slice(z);
    }
    var pick = marks.length ? (sel && marks.length > 1 ? marks[1] : (sel ? null : marks[0])) : null;
    if (pick) t.setSelectionRange(pick[0], pick[1]); else t.setSelectionRange(a + text.length, a + text.length);
    autosize(t); setCurrent(g); changed();
  }
  function toggleSide(force) {
    var b = document.body;
    if (mobile.matches) b.classList.toggle("side-open", force == null ? !b.classList.contains("side-open") : force);
    else b.classList.toggle("side-hidden", force == null ? !b.classList.contains("side-hidden") : !force);
  }

  // ------------------------------------------------------------------ commando's (menu, werkbalk, toetsen)
  function curOrLast() { return S.cur && S.cur.isConnected ? S.cur : groupsEl.lastElementChild; }
  // ---------------------------------------------------------------- werkblad meenemen app <-> web
  // Formaat: #ws=<base64url(deflate-raw(JSON {name, groups}))>. Niets wordt op een server bewaard.
  var IS_APP = /^(127\.0\.0\.1|localhost)$/.test(location.hostname) && /^1875\d$/.test(location.port);
  document.documentElement.classList.add(IS_APP ? "is-app" : "is-web");
  function b64u(buf) { var s = "", a = new Uint8Array(buf); for (var i = 0; i < a.length; i += 0x8000) s += String.fromCharCode.apply(null, a.subarray(i, i + 0x8000)); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
  function unb64u(t) { t = t.replace(/-/g, "+").replace(/_/g, "/"); while (t.length % 4) t += "="; var s = atob(t), a = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i); return a; }
  function packWs() {
    var data = new TextEncoder().encode(JSON.stringify({ name: S.name || "werkblad", groups: serialize() }));
    if (!window.CompressionStream) return Promise.resolve("j" + b64u(data));
    return new Response(new Blob([data]).stream().pipeThrough(new CompressionStream("deflate-raw"))).arrayBuffer().then(function (b) { return "z" + b64u(b); });
  }
  function unpackWs(t) {
    var kind = t.charAt(0), bytes = unb64u(t.slice(1));
    var p = kind === "z" ? new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).arrayBuffer() : Promise.resolve(bytes.buffer);
    return p.then(function (b) { return JSON.parse(new TextDecoder().decode(b)); });
  }
  function openOther() {
    packWs().then(function (t) {
      if (IS_APP) { window.open("https://maple.hydrargyrum.be/#ws=" + t, "_blank", "noopener"); return; }
      var left = false;
      window.addEventListener("blur", function once() { left = true; window.removeEventListener("blur", once); });
      location.href = "minimaple://open#ws=" + t;
      setTimeout(function () {
        if (!left) notice("Ging de Windows-app niet open? Dan is ze nog niet geïnstalleerd of nog nooit gestart. <a href=\"/download\">Download de app</a>, start ze één keer, en probeer opnieuw.", false);
      }, 1800);
    });
  }
  (function () {
    var m = /^#ws=([A-Za-z0-9_-]+)$/.exec(location.hash || "");
    if (!m) return;
    try { history.replaceState(null, "", location.pathname + location.search); } catch (e) {}
    unpackWs(m[1]).then(function (d) {
      if (!d || !Array.isArray(d.groups)) return;
      if (hasContent() && S.dirty && !window.confirm("Het huidige werkblad vervangen door het meegestuurde werkblad?")) return;
      stop(); post("/api/reset"); S.label = 0;
      loadGroups(d.groups.map(function (g) { return { type: g.type === "text" ? "text" : "input", code: String(g.code || "") }; }));
      setName(String(d.name || "werkblad")); S.dirty = false;
      lsSet(LS, { name: S.name, groups: serialize() });
      notice("Werkblad meegenomen" + (IS_APP ? " uit de webversie" : " uit de app") + ". Nog niets uitgevoerd.", false,
        [{ label: "Alles uitvoeren", primary: true, fn: function () { noticeEl.hidden = true; runAll(); } }]);
    }).catch(function (e) { notice("Kon het meegestuurde werkblad niet lezen: " + esc(String(e)), true); });
  })();

  var CMD = {
    openother: function () { openOther(); },
    download: function () { location.href = "/download"; },
    "new": newSheet, open: function () { $("file").click(); },
    savemw: function () { download(toMw(serialize()), baseName() + ".mw", "application/xml"); },
    savempl: function () { download(toMpl(serialize()), baseName() + ".mpl", "text/plain"); },
    exporthtml: exportHtml, print: function () { window.print(); },
    addafter: function () { focusGroup(insertGroup("input", curOrLast(), "after")); },
    addbefore: function () { focusGroup(insertGroup("input", curOrLast(), "before")); },
    addtext: function () { focusGroup(insertGroup("text", curOrLast(), "after")); },
    append: function () { focusGroup(insertGroup("input", groupsEl.lastElementChild, "after")); },
    moveup: function () { var g = S.cur; if (g && g.previousElementSibling) { groupsEl.insertBefore(g, g.previousElementSibling); refocus(g); changed(); } },
    movedown: function () { var g = S.cur; if (g && g.nextElementSibling) { groupsEl.insertBefore(g.nextElementSibling, g); refocus(g); changed(); } },
    "delete": function () {
      var g = S.cur; if (!g) return;
      var n = g.nextElementSibling || g.previousElementSibling;
      g.remove(); S.cur = null;
      if (!inputs().length) n = insertGroup("input", null);
      changed(); info(); focusGroup(n);
    },
    clearout: function () { Array.prototype.forEach.call(groupsEl.querySelectorAll(".out"), function (o) { o.textContent = ""; }); S.label = 0; },
    run: function () { runCurrent(false); }, runall: runAll, stop: stop, restart: restart,
    help: function () { helpDialog(wordAtCursor()); }, commands: commandsDialog, examples: examplesDialog,
    keys: keysDialog, about: aboutDialog, palettes: function () { toggleSide(); }
  };
  function refocus(g) { if (g.dataset.type === "input") { var t = ta(g), p = t.selectionStart; t.focus(); t.setSelectionRange(p, p); } keepVisible(g); }

  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-cmd]");
    if (b && CMD[b.dataset.cmd]) { closeMenus(); CMD[b.dataset.cmd](); return; }
    var top = e.target.closest(".mi>button");
    if (top) { var open = top.getAttribute("aria-expanded") === "true"; closeMenus(); if (!open) openMenu(top); return; }
    if (!e.target.closest(".menu")) closeMenus();
  });
  function openMenu(top) {
    top.setAttribute("aria-expanded", "true"); var m = top.nextElementSibling; m.hidden = false;
  }
  function closeMenus() {
    Array.prototype.forEach.call(document.querySelectorAll(".mi>button"), function (b) { b.setAttribute("aria-expanded", "false"); b.nextElementSibling.hidden = true; });
  }
  $("menubar").addEventListener("mouseover", function (e) {   // menu's wisselen met hover zodra er één open is
    var top = e.target.closest(".mi>button");
    if (top && document.querySelector('.mi>button[aria-expanded="true"]') && top.getAttribute("aria-expanded") !== "true") { closeMenus(); openMenu(top); }
  });
  $("menubar").addEventListener("keydown", function (e) {
    var items = Array.prototype.slice.call(document.querySelectorAll('.mi>button[aria-expanded="true"] + .menu button'));
    if (!items.length) return;
    var i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  });
  $("scrim").onclick = function () { toggleSide(false); };

  // toetsen in groepen
  groupsEl.addEventListener("focusin", function (e) { var g = e.target.closest(".grp"); if (g) setCurrent(g); });
  groupsEl.addEventListener("click", function (e) {
    var v = e.target.closest(".md"); if (v && !e.target.closest("a")) editText(v.parentNode);
  });
  groupsEl.addEventListener("input", function (e) { if (e.target.tagName === "TEXTAREA") { autosize(e.target); changed(); } });
  groupsEl.addEventListener("focusout", function (e) {
    if (e.target.classList.contains("txt")) { var g = e.target.parentNode; setTimeout(function () { if (document.activeElement !== e.target) renderText(g); }, 0); }
  });
  groupsEl.addEventListener("keydown", function (e) {
    var t = e.target, g = t.closest && t.closest(".grp");
    if (!g) return;
    if (t.classList.contains("md")) { if (e.key === "Enter") { e.preventDefault(); editText(g); } return; }
    if (t.classList.contains("txt")) {
      if (e.key === "Escape" || (e.key === "Enter" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); renderText(g); var n = g.nextElementSibling; if (n) focusGroup(n, false); }
      return;
    }
    if (!t.classList.contains("code") || e.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey && !e.altKey && !(e.ctrlKey && e.shiftKey)) { e.preventDefault(); runCurrent(true); return; }
    var v = t.value, p = t.selectionStart;
    if (e.key === "ArrowUp" && !e.altKey && t.selectionEnd === p && v.lastIndexOf("\n", p - 1) < 0 && g.previousElementSibling) {
      e.preventDefault(); focusGroup(g.previousElementSibling); return;
    }
    if (e.key === "ArrowDown" && !e.altKey && t.selectionEnd === p && v.indexOf("\n", p) < 0 && g.nextElementSibling) {
      e.preventDefault(); focusGroup(g.nextElementSibling, false); return;
    }
  });
  document.addEventListener("keydown", function (e) {
    var k = e.key, c = e.ctrlKey || e.metaKey;
    if (k === "Escape") { closeMenus(); if (document.body.classList.contains("side-open")) toggleSide(false); return; }
    if (k === "F1") { e.preventDefault(); CMD.help(); return; }
    if (c && e.shiftKey && k === "Enter") { e.preventDefault(); runAll(); return; }
    if (c && !e.shiftKey && (k === "j" || k === "J")) { e.preventDefault(); CMD.addafter(); return; }
    if (c && !e.shiftKey && (k === "k" || k === "K")) { e.preventDefault(); CMD.addbefore(); return; }
    if (c && (k === "o" || k === "O")) { e.preventDefault(); CMD.open(); return; }
    if (c && (k === "s" || k === "S")) { e.preventDefault(); CMD.savemw(); return; }
    if (c && k === "Delete") { e.preventDefault(); CMD["delete"](); return; }
    if (e.altKey && k === "ArrowUp") { e.preventDefault(); CMD.moveup(); return; }
    if (e.altKey && k === "ArrowDown") { e.preventDefault(); CMD.movedown(); return; }
  });

  // openen: bestandskiezer en slepen
  $("file").addEventListener("change", function () { openFile(this.files[0]); this.value = ""; });
  var dragN = 0;
  function isFileDrag(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0; }
  window.addEventListener("dragenter", function (e) { if (isFileDrag(e)) { dragN++; document.body.classList.add("dragging"); } });
  window.addEventListener("dragleave", function (e) { if (isFileDrag(e) && --dragN <= 0) { dragN = 0; document.body.classList.remove("dragging"); } });
  window.addEventListener("dragover", function (e) { if (isFileDrag(e)) e.preventDefault(); });
  window.addEventListener("drop", function (e) {
    if (!isFileDrag(e)) return;
    e.preventDefault(); dragN = 0; document.body.classList.remove("dragging");
    openFile(e.dataTransfer.files[0]);
  });

  // ------------------------------------------------------------------ start
  buildPalettes();
  var saved = lsGet(LS, null);
  if (saved && saved.groups && saved.groups.length) { loadGroups(saved.groups); setName(saved.name); }
  else {
    loadGroups([{ type: "text", code: "# Nieuw werkblad\nTyp Maple-commando's na de `>`. **Enter** voert een groep uit en springt naar de volgende, **Shift+Enter** maakt een nieuwe regel. Paletten links voegen sjablonen in; `?diff` toont help." },
                { type: "input", code: "" }]);
    setName("naamloos");
  }
  S.dirty = false;
  ta(inputs()[0]).placeholder = "int(x^2*sin(x), x);";
  setStatus("Ready"); info();
  if (!mobile.matches) focusGroup(inputs()[0]);

  // Windows-launcher: /?open=<token> -> bestand ophalen en tonen (niet uitvoeren).
  // Op de gewone server bestaat /api/launcher/file niet (404): dan niets doen.
  (function () {
    var tok = null;
    try { tok = new URLSearchParams(location.search).get("open"); } catch (e) {}
    if (!tok) return;
    try { history.replaceState(null, "", location.pathname); } catch (e) {}
    fetch("/api/launcher/file?token=" + encodeURIComponent(tok))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || typeof d.content !== "string") return;
        var name = d.name || ("werkblad" + (d.ext ? "." + String(d.ext).replace(/^\./, "") : ""));
        S.dirty = false;   // expliciet geopend: niet vragen om te vervangen
        parseAndShow(name, d.content);
      })
      .catch(function () {});
  })();
})();
