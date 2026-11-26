"""Lexer + Pratt-parser voor Maple-syntax. AST = tuples met een tag op positie 0.

Knopen: ('int',n) ('float',txt) ('str',s) ('name',n) ('seq',[..]) ('list',[..]) ('set',[..])
('call',head,args) ('index',head,args) ('bin',op,l,r) ('un',op,x) ('assign',lhs,rhs) ('range',lo,hi)
('fact',x) ('arrow',params,body,src) ('proc',info) ('if',[(c,body)],else) ('for',info) ('ditto',n)
('mat',kind,items) ('modget',l,r) ('concat',l,r) ('uneval',e) ('typeop',l,r) ('dollar',l,r)
('assuming',e,c) ('elemwise',e) ('return',args) ('break',) ('next',) ('try',body,catches,fin)
"""
import re


class ParseError(Exception):
    def __init__(self, msg, pos=None):
        super().__init__(msg)
        self.pos = pos


KEYWORDS = {
    "if", "then", "elif", "else", "end", "fi", "do", "od", "for", "from", "to", "by", "while", "proc",
    "local", "global", "option", "options", "description", "return", "break", "next", "try", "catch",
    "finally", "and", "or", "not", "xor", "union", "minus", "intersect", "mod", "subset", "assuming",
    "implies", "in", "uses", "module", "use", "export", "RETURN_", "done", "quit", "stop",
}
OPS = [":=", "::", ":-", "->", "..", "**", "@@", "||", "<=", ">=", "<>", "&^", "&*", "&x",
       "+", "-", "*", "/", "^", "!", "$", "@", ".", ",", ";", ":", "(", ")", "[", "]", "{", "}",
       "<", ">", "=", "|", "~", "'", "&"]
OPS.sort(key=len, reverse=True)
# operatoren met een elementsgewijze variant op~ (L ^~ 2, L1 +~ L2, ...)
ELEM_BASE = {"+", "-", "*", "/", "^", "=", "<>", "<", "<=", ">", ">=", ".", "||", "@", "**", "mod", "and", "or",
             "xor", "implies", "union", "intersect", "minus", "subset", "in"}
VALUE_END_OPS = {")", "]", "}", "^%T", "^%H"}


class Tok:
    __slots__ = ("t", "v", "s", "e")

    def __init__(self, t, v, s, e):
        self.t, self.v, self.s, self.e = t, v, s, e

    def __repr__(self):
        return f"{self.t}:{self.v!r}"


ESC = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def tokenize(src):
    toks = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n\f\v":
            i += 1
        elif c == "#":
            while i < n and src[i] != "\n":
                i += 1
        elif c == "(" and src.startswith("(*", i):
            j = src.find("*)", i + 2)
            if j < 0:
                raise ParseError("unterminated comment", i)
            i = j + 2
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and src[j] != '"':
                if src[j] == "\\" and j + 1 < n:
                    nx = src[j + 1]
                    if nx == "\n":
                        j += 2
                        continue
                    buf.append(ESC.get(nx, "\\" + nx))
                    j += 2
                else:
                    buf.append(src[j])
                    j += 1
            if j >= n:
                raise ParseError("unterminated string", i)
            toks.append(Tok("str", "".join(buf), i, j + 1))
            i = j + 1
        elif c == "`":
            j = src.find("`", i + 1)
            if j < 0:
                raise ParseError("unterminated name", i)
            toks.append(Tok("qname", src[i + 1:j], i, j + 1))
            i = j + 1
        elif c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit() and not _value_end(toks)):
            j = i
            isf = False
            while j < n and src[j].isdigit():
                j += 1
            if j < n and src[j] == "." and not (j + 1 < n and src[j + 1] == "."):
                # 1.5  of  1.  (maar niet 1..5 en niet 1.x met x naam)
                if not (j + 1 < n and (src[j + 1].isalpha() or src[j + 1] == "_")):
                    isf = True
                    j += 1
                    while j < n and src[j].isdigit():
                        j += 1
            if j < n and src[j] in "eE":
                k = j + 1
                if k < n and src[k] in "+-":
                    k += 1
                if k < n and src[k].isdigit():
                    while k < n and src[k].isdigit():
                        k += 1
                    j = k
                    isf = True
            txt = src[i:j]
            toks.append(Tok("float" if isf else "int", txt, i, j))
            i = j
        elif c.isalpha() or c == "_":
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            toks.append(Tok("name", src[i:j], i, j))
            i = j
        elif c == "&" and i + 1 < n and (src[i + 1].isalpha() or src[i + 1] in "+-/<>=!@~|%$") and \
                not src.startswith("&*", i) and not src.startswith("&^", i) and \
                not (src.startswith("&x", i) and not (i + 2 < n and (src[i + 2].isalnum() or src[i + 2] == "_"))):
            j = i + 1
            if src[j].isalpha():
                while j < n and (src[j].isalnum() or src[j] == "_"):
                    j += 1
            else:
                while j < n and src[j] in "+-/<>=!@~|%$":
                    j += 1
            toks.append(Tok("op", "&" + src[i + 1:j], i, j))
            i = j
        elif c == "^" and src[i + 1:i + 3] in ("%T", "%H") and not src[i + 3:i + 4].isalnum():
            toks.append(Tok("op", "^" + src[i + 1:i + 3], i, i + 3))
            i += 3
        elif c == "%":
            j = i
            while j < n and src[j] == "%" and j - i < 3:
                j += 1
            toks.append(Tok("ditto", j - i, i, j))
            i = j
        else:
            for op in OPS:
                if src.startswith(op, i):
                    if op in ELEM_BASE and src.startswith("~", i + len(op)):
                        toks.append(Tok("op", op + "~", i, i + len(op) + 1))
                        i += len(op) + 1
                        break
                    toks.append(Tok("op", op, i, i + len(op)))
                    i += len(op)
                    break
            else:
                raise ParseError(f"unexpected character {c!r}", i)
    toks.append(Tok("eof", None, n, n))
    return toks


def _value_end(toks):
    if not toks:
        return False
    t = toks[-1]
    if t.t in ("int", "float", "str", "qname", "ditto"):
        return True
    if t.t == "name":
        return t.v not in KEYWORDS
    return t.t == "op" and t.v in VALUE_END_OPS


# (prec, rechts-associatief)
BIN = {
    ":=": (1, True), "assuming": (2, False), "->": (3, True), "$": (4, False), "implies": (5, False),
    "or": (6, False), "xor": (6, False), "and": (7, False),
    "<": (9, False), "<=": (9, False), ">": (9, False), ">=": (9, False), "=": (9, False), "<>": (9, False),
    "in": (9, False), "subset": (9, False), "::": (10, False), "mod": (10, False), "..": (11, False),
    "+": (12, False), "-": (12, False), "union": (12, False), "minus": (12, False),
    "*": (13, False), "/": (13, False), "&x": (13, False), "intersect": (13, False), "&*": (13, False),
    ".": (15, False), "@": (16, False), "@@": (16, False),
    "^": (17, True), "**": (17, True), "&^": (17, True),
}
for _o in list(BIN):
    if _o in ELEM_BASE:
        BIN[_o + "~"] = BIN[_o]
P_NEG = 14
P_POW = 17
# tokens die een blok afsluiten
BLOCK_END = {"end", "fi", "od", "elif", "else", "catch", "finally", "done"}


class Parser:
    def __init__(self, src):
        self.src = src
        self.toks = tokenize(src)
        self.i = 0

    # ---- basis
    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else self.toks[-1]

    def next(self):
        t = self.toks[self.i]
        if t.t != "eof":
            self.i += 1
        return t

    def isop(self, v, k=0):
        t = self.peek(k)
        return t.t == "op" and t.v == v

    def iskw(self, v, k=0):
        t = self.peek(k)
        return t.t == "name" and t.v == v

    def expect_op(self, v):
        t = self.next()
        if not (t.t == "op" and t.v == v):
            raise ParseError(f"'{v}' expected", t.s)
        return t

    def expect_kw(self, v):
        t = self.next()
        if not (t.t == "name" and t.v == v):
            raise ParseError(f"'{v}' expected", t.s)
        return t

    def tokdesc(self, t):
        return "end of input" if t.t == "eof" else repr(t.v)

    # ---- statements
    def parse_toplevel(self):
        """Generator: (ast, show, src) of (None, False, src, ParseError)."""
        while True:
            while self.isop(";") or self.isop(":"):
                self.next()
            if self.peek().t == "eof":
                return
            start = self.peek().s
            try:
                node = self.statement()
                t = self.peek()
                end = self.toks[self.i - 1].e
                if t.t == "op" and t.v in (";", ":"):
                    self.next()
                    show = t.v == ";"
                elif t.t == "eof":
                    show = True
                else:
                    raise ParseError(f"unexpected {self.tokdesc(t)}", t.s)
                yield node, show, self.src[start:end].strip(), None
            except ParseError as e:
                end = self.peek().s
                # resync: tot na de volgende ; of : op diepte 0
                depth = 0
                prev = self.toks[self.i - 1] if self.i > 0 else None
                consumed_term = (prev is not None and prev.t == "op" and prev.v in (";", ":") and e.pos == prev.s)
                while not consumed_term:
                    t = self.peek()
                    if t.t == "eof":
                        break
                    if t.t == "op" and t.v in "([{":
                        depth += 1
                    elif t.t == "op" and t.v in ")]}":
                        depth = max(0, depth - 1)
                    elif t.t == "op" and t.v in (";", ":") and depth == 0:
                        self.next()
                        break
                    self.next()
                yield None, True, self.src[start:max(end, start + 1)].strip(), e

    def body(self, extra_end=()):
        """Statements tot een blok-afsluiter."""
        out = []
        while True:
            while self.isop(";") or self.isop(":"):
                self.next()
            t = self.peek()
            if t.t == "eof":
                raise ParseError("unexpected end of input (missing 'end')", t.s)
            if t.t == "name" and t.v in BLOCK_END:
                return out
            out.append(self.statement())
            t = self.peek()
            if t.t == "op" and t.v in (";", ":"):
                self.next()
            elif t.t == "name" and t.v in BLOCK_END:
                pass
            elif t.t == "eof":
                pass
            else:
                raise ParseError(f"unexpected {self.tokdesc(t)}", t.s)

    def statement(self):
        return self.exprseq_or_expr()

    def exprseq_or_expr(self):
        e = self.expr(0)
        if self.isop(","):
            items = [e]
            while self.isop(","):
                self.next()
                items.append(self.expr(0))
            items = self._merge_assuming(items)
            if len(items) == 1:
                return items[0]
            for k, it in enumerate(items):
                if it[0] == "assign":
                    # a, b := x, y  ->  meervoudige toekenning
                    if k >= 1 and all(p[0] in ("name", "index", "concat") for p in items[:k]):
                        return ("assign", ("seq", items[:k] + [it[1]]), ("seq", [it[2]] + items[k + 1:]))
                    if k == 0:
                        return ("assign", it[1], ("seq", [it[2]] + items[1:]))
                    break
            return ("seq", items)
        return e

    @staticmethod
    def _merge_assuming(items):
        """expr assuming a::T, b>0  ->  assuming-rhs wordt de reeks a::T, b>0."""
        def is_prop(x):
            return x[0] == "typeop" or (x[0] == "bin" and x[1] in ("<", "<=", ">", ">=", "<>", "="))
        for j, it in enumerate(items):
            tgt = it[2] if it[0] == "assign" else it
            if tgt[0] == "assuming" and j + 1 < len(items) and all(is_prop(x) for x in items[j + 1:]):
                cond = ("seq", [tgt[2]] + items[j + 1:])
                new = ("assuming", tgt[1], cond)
                if it[0] == "assign":
                    new = ("assign", it[1], new)
                return items[:j] + [new]
        return items

    def end_block(self, what):
        self.expect_kw("end") if self.iskw("end") else None
        t = self.peek()
        if t.t == "name" and t.v == what:
            self.next()

    # ---- expressies
    def expr(self, minp=0):
        left = self.nud()
        while True:
            t = self.peek()
            if t.t == "op" or (t.t == "name" and t.v in BIN):
                op = t.v
            else:
                break
            kw_elem = t.t == "name" and self.isop("~", 1) and op + "~" in BIN
            if kw_elem:
                op = op + "~"
            if op not in BIN:
                if t.t == "op" and op.startswith("&") and len(op) > 1:
                    prec, right = 15, False            # neutrale operator &name / &+
                else:
                    break
            else:
                prec, right = BIN[op]
            if prec < minp:
                break
            self.next()
            if kw_elem:
                self.next()
            left = self.led(op, left, prec, right)
        return left

    def led(self, op, left, prec, right):
        nextp = prec if right else prec + 1
        if len(op) > 1 and op.endswith("~"):
            base = {"**": "^"}.get(op[:-1], op[:-1])
            return ("elembin", base, left, self.expr(nextp))
        if op == ":=":
            rhs = self.expr(nextp)
            return ("assign", left, rhs)
        if op == "->":
            start = self.rhs_start_pos(left)
            body = self.expr(nextp)
            params = self.arrow_params(left)
            end = self.toks[self.i - 1].e
            return ("arrow", params, body, self.src[start:end].strip())
        if op == "assuming":
            return ("assuming", left, self.expr(nextp))
        if op == "$":
            return ("dollar", left, self.expr(nextp))
        if op == "..":
            # rechter operand mag ontbreken: M[i,..]
            t = self.peek()
            if t.t == "op" and t.v in (",", ")", "]", "}", ";", ":"):
                return ("range", left, None)
            return ("range", left, self.expr(nextp))
        if op == "::":
            return ("typeop", left, self.expr(nextp))
        if op in ("**", "&^"):
            op = "^"
        if op == "&*":
            op = "*"
        if op == "&x":
            return ("call", ("name", "CrossProduct"), [left, self.expr(nextp)])
        if op.startswith("&") and op not in BIN:
            return ("call", ("name", op), [left, self.expr(nextp)])
        return ("bin", op, left, self.expr(nextp))

    def rhs_start_pos(self, left):
        # bronpositie van de pijl-lhs: zoek terug vanaf huidige token
        # (we nemen de start van de statement-ish: zoek het begin via haakjesbalans)
        j = self.i - 2   # token voor '->'
        t = self.toks[j]
        if t.t == "op" and t.v == ")":
            depth = 0
            while j >= 0:
                tj = self.toks[j]
                if tj.t == "op" and tj.v == ")":
                    depth += 1
                elif tj.t == "op" and tj.v == "(":
                    depth -= 1
                    if depth == 0:
                        return tj.s
                j -= 1
        return t.s

    def arrow_params(self, left):
        while left[0] == "paren":
            left = left[1]
        items = left[1] if left[0] == "seq" else ([] if left[0] == "seq0" else [left])
        params = []
        for it in items:
            if it[0] == "name":
                params.append((it[1], None, None))
            elif it[0] == "typeop" and it[1][0] == "name":
                params.append((it[1][1], it[2], None))
            elif it[0] == "assign" and it[1][0] == "name":
                params.append((it[1][1], None, it[2]))
            else:
                raise ParseError("invalid parameter list in ->", self.peek().s)
        return params

    def nud(self):
        t = self.peek()
        if t.t == "op":
            v = t.v
            if v == "-":
                self.next()
                return ("un", "-", self.expr(P_NEG))
            if v == "+":
                self.next()
                return self.expr(P_NEG)
            if v == "<":
                return self.postfix(self.matrix())
            if v == "$":
                self.next()
                return ("dollar", None, self.expr(5))
            if v == "..":
                self.next()
                t2 = self.peek()
                if t2.t == "op" and t2.v in (",", ")", "]", "}", ";", ":"):
                    return ("range", None, None)
                return ("range", None, self.expr(12))
            if v == ":-":
                self.next()
                n = self.next()
                return ("name", n.v)
        elif t.t == "name" and t.v == "not":
            self.next()
            return ("un", "not", self.expr(9))
        return self.postfix(self.primary())

    def postfix(self, e):
        while True:
            t = self.peek()
            if t.t == "op":
                v = t.v
                if v == "(":
                    self.next()
                    args = self.args(")")
                    e = ("call", e, args)
                    continue
                if v == "[":
                    self.next()
                    args = self.args("]")
                    e = ("index", e, args)
                    continue
                if v == "!":
                    self.next()
                    e = ("fact", e)
                    continue
                if v == "~":
                    self.next()
                    e = ("elemwise", e)
                    continue
                if v in ("^%T", "^%H"):
                    self.next()
                    e = ("call", ("name", "Transpose" if v == "^%T" else "HermitianTranspose"), [e])
                    continue
                if v == ":-":
                    self.next()
                    n = self.next()
                    if n.t not in ("name", "qname"):
                        raise ParseError("name expected after :-", n.s)
                    e = ("modget", e, ("name", n.v))
                    continue
                if v == "||":
                    self.next()
                    r = self.postfix(self.primary())
                    e = ("concat", e, r)
                    continue
            break
        return e

    def args(self, close):
        out = []
        if self.isop(close):
            self.next()
            return out
        while True:
            out.append(self.expr(1) if False else self.expr(0))
            if self.isop(","):
                self.next()
                continue
            self.expect_op(close)
            return out

    def primary(self):
        t = self.next()
        k = t.t
        if k == "int":
            return ("int", int(t.v))
        if k == "float":
            return ("float", t.v)
        if k == "str":
            return ("str", t.v)
        if k == "qname":
            return ("name", t.v)
        if k == "ditto":
            return ("ditto", t.v)
        if k == "op":
            v = t.v
            if v == "(":
                if self.isop(")"):
                    self.next()
                    return ("seq", [])
                e = self.expr(0)
                if self.isop(","):
                    items = [e]
                    while self.isop(","):
                        self.next()
                        items.append(self.expr(0))
                    self.expect_op(")")
                    return ("seq", items)
                self.expect_op(")")
                return ("paren", e)
            if v == "[":
                return ("list", self.args("]"))
            if v == "{":
                return ("set", self.args("}"))
            if v == "'":
                k = 1
                while self.isop("'"):
                    self.next()
                    k += 1
                nt = self.peek()
                if k % 2 == 0 and (nt.t == "eof" or (nt.t == "op" and nt.v in (";", ":", ",", ")", "]", "}"))):
                    e = ("seq", [])          # '' (lege uitgestelde reeks), eventueel genest
                    for _ in range(k // 2 - 1):
                        e = ("uneval", e)
                    return ("uneval", e)
                e = self.expr(0)
                for _ in range(k):
                    self.expect_op("'")
                for _ in range(k):
                    e = ("uneval", e)
                return e
            raise ParseError(f"unexpected {self.tokdesc(t)}", t.s)
        if k == "name":
            v = t.v
            if v in KEYWORDS:
                return self.keyword(t)
            if v == "error" and not self.isop("("):
                nt = self.peek()
                if nt.t == "eof" or (nt.t == "op" and nt.v in (";", ":")) or (nt.t == "name" and nt.v in BLOCK_END):
                    return ("call", ("name", "error"), [])       # `error;` : opnieuw opwerpen
                if nt.t != "eof" and not (nt.t == "op" and nt.v in (";", ":")) and not (nt.t == "name" and nt.v in BLOCK_END):
                    items = [self.expr(0)]
                    while self.isop(","):
                        self.next()
                        items.append(self.expr(0))
                    return ("call", ("name", "error"), items)
            return ("name", v)
        raise ParseError(f"unexpected {self.tokdesc(t)}", t.s)

    # ---- sleutelwoord-constructies
    def keyword(self, t):
        v = t.v
        if v == "proc":
            return self.proc(t)
        if v == "module":
            return self.module(t)
        if v == "use":
            return self.use(t)
        if v == "if":
            return self.if_(t)
        if v in ("for", "while", "from", "to", "by", "do"):
            return self.loop(t)
        if v == "return":
            nt = self.peek()
            if nt.t == "eof" or (nt.t == "op" and nt.v in (";", ":")) or (nt.t == "name" and nt.v in BLOCK_END):
                return ("return", [])
            items = [self.expr(0)]
            while self.isop(","):
                self.next()
                items.append(self.expr(0))
            return ("return", items)
        if v == "break":
            return ("break",)
        if v == "next":
            return ("next",)
        if v == "try":
            return self.try_()
        if v in ("done", "quit", "stop"):
            return ("seq", [])
        raise ParseError(f"unexpected keyword '{v}'", t.s)

    def end_kw(self, *alts):
        t = self.next()
        if t.t == "name" and t.v in alts:
            return
        if t.t == "name" and t.v == "end":
            n = self.peek()
            if n.t == "name" and n.v in alts:
                self.next()
            return
        raise ParseError(f"'end' expected", t.s)

    def if_(self, t0):
        branches = []
        cond = self.expr(0)
        self.expect_kw("then")
        branches.append((cond, self.body()))
        els = None
        while True:
            t = self.peek()
            if t.t == "name" and t.v == "elif":
                self.next()
                c = self.expr(0)
                self.expect_kw("then")
                branches.append((c, self.body()))
            elif t.t == "name" and t.v == "else":
                self.next()
                els = self.body()
            else:
                break
        self.end_kw("fi", "if")
        return ("if", branches, els)

    def loop(self, t0):
        info = dict(var=None, frm=None, to=None, by=None, inn=None, cond=None, body=None)
        if t0.v == "for":
            n = self.next()
            if n.t not in ("name", "qname"):
                raise ParseError("loop variable expected", n.s)
            info["var"] = n.v
        else:
            self.i -= 1
        while True:
            t = self.peek()
            if t.t != "name":
                break
            if t.v == "from":
                self.next()
                info["frm"] = self.expr(5)
            elif t.v == "to":
                self.next()
                info["to"] = self.expr(5)
            elif t.v == "by":
                self.next()
                info["by"] = self.expr(5)
            elif t.v == "in":
                self.next()
                info["inn"] = self.expr(5)
            elif t.v == "while":
                self.next()
                info["cond"] = self.expr(5)
            elif t.v == "do":
                break
            else:
                break
        self.expect_kw("do")
        info["body"] = self.body()
        self.end_kw("od", "do")
        return ("for", info)

    def try_(self):
        body = self.body()
        catches = []
        fin = None
        while True:
            t = self.peek()
            if t.t == "name" and t.v == "catch":
                self.next()
                pats = []
                while self.peek().t == "str":
                    pats.append(self.next().v)
                    if self.isop(","):
                        self.next()
                if self.isop(":"):
                    self.next()
                catches.append((pats, self.body()))
            elif t.t == "name" and t.v == "finally":
                self.next()
                fin = self.body()
            else:
                break
        self.end_kw("try")
        return ("try", body, catches, fin)

    def _param(self):
        n = self.next()
        if n.t not in ("name", "qname"):
            raise ParseError("parameter name expected", n.s)
        typ = dflt = None
        if self.isop("::"):
            self.next()
            typ = self.expr(11)
        if self.isop(":=") or self.isop("="):
            self.next()
            dflt = self.expr(5)
        return (n.v, typ, dflt)

    def proc_params(self):
        """-> (positionele params, keyword-params, end-marker $)"""
        params, kw, dollar = [], [], False
        self.expect_op("(")
        if not self.isop(")"):
            while True:
                if self.isop("{"):
                    self.next()
                    if not self.isop("}"):
                        while True:
                            kw.append(self._param())
                            if self.isop(","):
                                self.next()
                                continue
                            break
                    self.expect_op("}")
                elif self.isop("$"):
                    self.next()
                    dollar = True
                else:
                    params.append(self._param())
                if self.isop(","):
                    self.next()
                    continue
                break
        self.expect_op(")")
        return params, kw, dollar

    def decls(self):
        rettype = None
        if self.isop("::"):
            self.next()
            rettype = self.expr(11)
        locs, globs, opts, inits, exports, uses = [], [], [], [], [], []
        while True:
            while self.isop(";") or self.isop(":"):
                self.next()
            t = self.peek()
            if t.t == "name" and t.v in ("local", "global", "option", "options", "description", "uses", "export"):
                self.next()
                if t.v == "description":
                    while self.peek().t == "str":
                        self.next()
                        if self.isop(","):
                            self.next()
                    continue
                while True:
                    n = self.next()
                    if n.t not in ("name", "qname"):
                        raise ParseError("name expected in declaration", n.s)
                    if self.isop("::"):
                        self.next()
                        self.expr(11)
                    if self.isop(":="):
                        self.next()
                        ini = self.expr(5)
                        if t.v in ("local", "export"):
                            inits.append(("assign", ("name", n.v), ini))
                    if t.v == "local":
                        locs.append(n.v)
                    elif t.v == "export":
                        exports.append(n.v)
                    elif t.v == "global":
                        globs.append(n.v)
                    elif t.v == "uses":
                        uses.append(n.v)
                    elif t.v in ("option", "options"):
                        opts.append(n.v)
                        if self.isop("("):          # option remember(...), option ... = ...
                            self.next()
                            self.args(")")
                    if self.isop(","):
                        self.next()
                        continue
                    break
                continue
            break
        self._uses = uses
        return locs, globs, opts, inits, exports, rettype

    def proc(self, t0):
        params, kwparams, dollar = self.proc_params()
        locs, globs, opts, inits, exports, rettype = self.decls()
        uses = self._uses
        body = inits + self.body()
        if uses:
            body = [("use", [("name", u) for u in uses], body)]
        self.end_kw("proc")
        src = self.src[t0.s:self.toks[self.i - 1].e]
        return ("proc", dict(params=params, locals=locs + exports, globals=globs, options=opts, body=body, src=src,
                             rettype=rettype, kwparams=kwparams, dollar=dollar))

    def module(self, t0):
        """module() export ..; local ..; option ..; stmts end module   (ook  module M() ... )"""
        name = None
        if self.peek().t in ("name", "qname") and self.isop("(", 1):
            name = self.next().v
        self.expect_op("(")
        self.expect_op(")")
        locs, globs, opts, inits, exports, _ = self.decls()
        body = inits + self.body()
        self.end_kw("module")
        src = self.src[t0.s:self.toks[self.i - 1].e]
        return ("module", dict(name=name, locals=locs, exports=exports, globals=globs, options=opts, body=body,
                               src=src))

    def use(self, t0):
        """use A, B, x = e in stmts end use"""
        binds = []
        while True:
            b = self.expr(10)
            if self.isop("="):
                self.next()
                b = ("bin", "=", b, self.expr(10))
            binds.append(b)
            if self.isop(","):
                self.next()
                continue
            break
        self.expect_kw("in")
        body = self.body()
        self.end_kw("use")
        return ("use", binds, body)

    def matrix(self):
        self.expect_op("<")
        groups = [[]]
        if self.isop(">"):
            self.next()
            return ("mat", "vstack", [])
        while True:
            groups[-1].append(self.expr(11))
            if self.isop("|"):
                self.next()
                continue
            if self.isop(","):
                self.next()
                groups.append([])
                continue
            break
        self.expect_op(">")
        if len(groups) == 1:
            g = groups[0]
            return ("mat", "hstack" if len(g) > 1 else "vstack", g)
        items = []
        for g in groups:
            items.append(g[0] if len(g) == 1 else ("mat", "hstack", g))
        return ("mat", "vstack", items)


def parse(src):
    """Parse hele code: lijst (ast, show, src, error)."""
    return list(Parser(src).parse_toplevel())
