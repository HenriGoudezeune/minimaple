import json, threading, urllib.request
from http.server import ThreadingHTTPServer


def test_web_api():
    from minimaple.web import server
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        r = urllib.request.urlopen(base + "/")
        cookie = r.headers["Set-Cookie"].split(";")[0]
        assert b"mini-Maple" in r.read()
        assert len(json.load(urllib.request.urlopen(base + "/api/examples"))) >= 5
        req = urllib.request.Request(base + "/api/eval", json.dumps({"code": "a := 2; a;"}).encode(),
                                     {"Cookie": cookie, "Content-Type": "application/json"})
        res = json.load(urllib.request.urlopen(req))["results"]
        assert res and all("plots" in x for x in res)
        # werkblad openen: enkel parsen
        from pathlib import Path
        mw = (Path(__file__).parent / "fixtures" / "flat.mw").read_bytes()
        req = urllib.request.Request(base + "/api/open?name=flat.mw", mw, {"Content-Type": "application/octet-stream"})
        d = json.load(urllib.request.urlopen(req))
        assert d["name"] == "flat.mw" and [g["type"] for g in d["groups"]] == ["text", "input"]
        try:
            urllib.request.urlopen(urllib.request.Request(base + "/api/open?name=x.mw", b"<nope", {})); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 400 and "error" in json.load(e)
        h = json.load(urllib.request.urlopen(base + "/api/help?name=diff"))
        assert h["found"] and h["text"].startswith("diff")
        assert not json.load(urllib.request.urlopen(base + "/api/help?name=geenidee"))["found"]
        # path traversal en vreemde Host worden geweigerd
        try:
            urllib.request.urlopen(base + "/static/../server.py"); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown(); server.MGR.close()
