"""Werkbladen lezen en schrijven: .mw (worksheet-XML) en .mpl/.txt (platte Maple-code).

Eigen implementatie; het formaat is afgeleid uit voorbeeldbestanden:
  <Worksheet> ... <Section><Title><Text-field style="Heading 1">..</Text-field></Title>
     <Presentation-Block>
       <Group view="code"><Input><Text-field prompt="> " style="Maple Input">code</Text-field></Input>
          <Output>..</Output></Group>
       <Group view="presentation"><Input><Text-field style="Text">tekst <Equation ...>base64</Equation></Text-field></Input></Group>
Uitvoer (<Output>) wordt genegeerd: de groepen worden opnieuw uitgerekend.
Groepen: {"type": "input"|"text", "code": str}. Tekst is markdown-light ("# " = kop).
"""
import base64
import html
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

MAX_BYTES = 5 * 1024 * 1024
_SKIP = {"Styles", "Startup-Code", "Label-Scheme", "View-Properties", "MapleNet-Properties",
         "Task-table", "Version", "Output", "Pencil-style", "Highlighter-style", "Hide", "Layout"}
_HEADINGS = {"Title": "# ", "Heading 1": "# ", "Heading 2": "## ", "Heading 3": "### ", "Heading 4": "#### "}
_INVISIBLE = dict.fromkeys(map(ord, "⁡⁢⁣⁤​"), None)


class WorksheetError(ValueError):
    pass


# ---------------------------------------------------------------- 2D-math (best effort)
def _math_tokens(b64):
    """Een <Equation> bewaart een geserialiseerde boom (mrow/mi/mo/mn ...) in base64.
    Strings staan erin als 'Q' + lengtebyte (len+33) + tekst; het eerste argument van
    een knoop volgt op '6' + aantal-byte. We nemen die eerste argumenten in volgorde:
    dat zijn de zichtbare tokens. Lukt het niet, dan None."""
    try:
        raw = base64.b64decode(b64.strip(), validate=False).decode("utf-8", "replace")
    except Exception:
        return None
    toks = []
    for m in re.finditer(r"6[!-~]Q([!-~])", raw):
        n = ord(m.group(1)) - 33
        s = raw[m.end():m.end() + n]
        if len(s) == n:
            toks.append(s)
    if not toks:
        return None
    out = html.unescape("".join(toks)).translate(_INVISIBLE).replace("~", " ")
    return out.strip()


# ---------------------------------------------------------------- .mw lezen
_OCT = re.compile(r"(?:\\[23][0-7]{2})+")


def _unoctal(s):
    """Niet-ASCII staat in de XML als octale UTF-8-escapes (\\303\\251 = é)."""
    def dec(m):
        b = bytes(int(x, 8) for x in m.group().split("\\")[1:])
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return m.group()
    return _OCT.sub(dec, s)

def _field_text(tf, warn):
    """Tekst van een Text-field, inclusief <Font>-kinderen en <Equation> (benaderd)."""
    parts = [tf.text or ""]
    for ch in tf:
        if ch.tag == "Equation":
            t = _math_tokens(ch.text or ch.get("display", ""))
            if t is None:
                warn("2d", "2D-wiskunde zonder tekstvorm overgeslagen")
                parts.append("[2D-math]")
            elif t:
                warn("2dok", "2D-wiskunde in tekst als platte tekst benaderd")
                parts.append(t)
        else:
            parts.append(_field_text(ch, warn))
        parts.append(ch.tail or "")
    return "".join(parts)


def parse_mw(data):
    """bytes|str -> {"groups": [...], "warnings": [...]}"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise WorksheetError("bestand te groot (max 5 MB)")
    head = data[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data.upper():
        raise WorksheetError("DOCTYPE/ENTITY niet toegestaan")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise WorksheetError(f"geen geldige worksheet-XML: {e}") from None
    if root.tag != "Worksheet":
        raise WorksheetError("geen <Worksheet>-document")

    groups, notes = [], {}

    def warn(key, msg):
        notes[key] = (msg, notes.get(key, (msg, 0))[1] + 1)

    def add(kind, code):
        code = code.rstrip()
        if not code.strip():
            return
        if kind == "text" and groups and groups[-1]["type"] == "text":
            groups[-1]["code"] += "\n\n" + code
        else:
            groups.append({"type": kind, "code": code})

    def text_of(tf):
        style = tf.get("style", "")
        t = _unoctal(_field_text(tf, warn)).strip()
        if not t:
            return ""
        pre = _HEADINGS.get(style, "")
        return pre + " ".join(t.split()) if pre else t

    def group(g):
        code_lines, text_parts = [], []
        for inp in g.findall("Input"):
            for tf in inp.iter("Text-field"):
                is_code = tf.get("prompt") is not None or tf.get("style") == "Maple Input" \
                    or (g.get("view") == "code" and tf.get("style") in (None, "Maple Input"))
                if is_code:
                    if tf.find(".//Equation") is not None:
                        warn("2din", "2D-math-invoer benaderd als tekst: controleer die groepen")
                    code_lines.append(_unoctal(_field_text(tf, warn)))
                else:
                    t = text_of(tf)
                    if t:
                        text_parts.append(t)
        for t in text_parts:
            add("text", t)
        if code_lines:
            add("input", "\n".join(code_lines))
        out = g.find("Output")
        if out is not None:
            for el in out.iter():
                if el.tag in ("Plot", "Image", "Drawing-Canvas"):
                    warn("plot", "plots/afbeeldingen in de uitvoer niet overgenomen (opnieuw uitvoeren)")
        for el in g:   # geneste secties/groepen (zeldzaam)
            if el.tag in ("Section", "Group"):
                visit(el)

    def visit(el):
        tag = el.tag
        if tag in _SKIP:
            return
        if tag == "Title":
            for tf in el.iter("Text-field"):
                t = _field_text(tf, warn).strip()
                if t:
                    style = tf.get("style", "Heading 1")
                    add("text", _HEADINGS.get(style, "# ") + " ".join(t.split()))
            return
        if tag == "Group":
            return group(el)
        if tag == "Text-field":      # losse tekst buiten een groep
            return add("text", text_of(el))
        if "Component" in tag or tag in ("Plot", "Image", "Drawing-Canvas"):
            warn("comp", f"ingebedde onderdelen ({tag}) overgeslagen")
            return
        for ch in el:
            visit(ch)

    visit(root)
    su = root.find("Startup-Code")
    if su is not None and (su.get("startupcode") or "").strip():
        warn("startup", "startcode van het werkblad niet overgenomen")
    warnings = [f"{m} ({n}x)" if n > 1 else m for m, n in notes.values() if m]
    return {"groups": groups, "warnings": warnings}


# ---------------------------------------------------------------- .mpl lezen
_STR = re.compile(r'"(?:[^"\\]|\\.)*"|`[^`]*`|#[^\n]*')
_OPEN = re.compile(r"\b(proc|module|do|if)\b")
_CLOSE = re.compile(r"\bend\s+(proc|module|do|if)\b|\bend\b|\bfi\b|\bod\b")


def _depth(code):
    c = _STR.sub(" ", code)
    closes = len(_CLOSE.findall(c))
    c2 = _CLOSE.sub(" ", c)
    # 'elif' bevat geen \bif\b; 'for ... do' telt via 'do'
    return len(_OPEN.findall(c2)) - closes


def parse_mpl(text):
    """Platte Maple-code -> groepen. Splitst op lege regels, maar niet midden in een
    proc/if/do-blok of een onafgewerkt statement. Blokken van enkel '#'-regels worden tekst."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks, cur = [], []

    def flush():
        if any(l.strip() for l in cur):
            chunks.append("\n".join(cur).strip("\n"))
        cur.clear()

    for line in text.split("\n"):
        if not line.strip() and cur:
            body = "\n".join(cur)
            stripped = _STR.sub(lambda m: "" if m.group().startswith("#") else "s", body).rstrip()
            only_comments = all(l.lstrip().startswith("#") for l in cur if l.strip())
            if only_comments or (_depth(body) <= 0 and stripped.endswith((";", ":"))):
                flush()
                continue
        cur.append(line)
    flush()
    groups = []
    for ch in chunks:
        lines = [l for l in ch.split("\n") if l.strip()]
        if all(l.lstrip().startswith("#") for l in lines):
            t = "\n".join(re.sub(r"^\s*# ?", "", l) for l in lines)
            if groups and groups[-1]["type"] == "text":
                groups[-1]["code"] += "\n\n" + t
            else:
                groups.append({"type": "text", "code": t})
        else:
            groups.append({"type": "input", "code": ch})
    return {"groups": groups, "warnings": []}


def parse_file(name, data):
    name = (name or "").lower()
    if len(data) > MAX_BYTES:
        raise WorksheetError("bestand te groot (max 5 MB)")
    if name.endswith(".mw") or data.lstrip()[:5] == b"<?xml" or data.lstrip()[:10] == b"<Worksheet":
        return parse_mw(data)
    if name.endswith((".mpl", ".txt", ".mm", ".maple")) or not name:
        try:
            return parse_mpl(data.decode("utf-8"))
        except UnicodeDecodeError:
            return parse_mpl(data.decode("latin-1"))
    raise WorksheetError("onbekend bestandstype (gebruik .mw, .mpl of .txt)")


# ---------------------------------------------------------------- schrijven
def to_mpl(groups):
    out = []
    for g in groups:
        code = g.get("code", "").rstrip()
        if not code.strip():
            continue
        if g.get("type") == "text":
            out.append("\n".join("# " + l if l.strip() else "#" for l in code.split("\n")))
        else:
            # lege regels binnen een groep zouden bij het teruglezen een nieuwe groep starten
            code = "\n".join(l for l in code.split("\n") if l.strip())
            last = code.split("\n")[-1].strip()
            if not code.endswith((";", ":")) and not last.startswith("#"):
                code += ";"   # Maple toont een onafgesloten laatste statement ook
            out.append(code)
    return "\n\n".join(out) + "\n"


def to_mw(groups):
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', "<Worksheet>", '<Version major="2025" minor="2"/>']
    for g in groups:
        code = g.get("code", "").rstrip()
        if not code.strip():
            continue
        if g.get("type") == "text":
            for para in re.split(r"\n\s*\n", code):
                para = para.strip()
                m = re.match(r"^(#{1,4})\s+(.*)$", para, re.S)
                style = f"Heading {len(m.group(1))}" if m else "Text"
                body = m.group(2) if m else para
                rows.append(f'<Group view="presentation"><Input><Text-field style="{style}" layout="{style if m else "Normal"}">'
                            f"{escape(body, {chr(34): '&quot;'})}</Text-field></Input></Group>")
        else:
            rows.append('<Group view="code"><Input><Text-field prompt="&gt; " style="Maple Input" layout="Normal">'
                        f"{escape(code, {chr(34): '&quot;'})}</Text-field></Input></Group>")
    rows.append("</Worksheet>")
    return "\n".join(rows) + "\n"
