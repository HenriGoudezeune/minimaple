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
        # path traversal en vreemde Host worden geweigerd
        try:
            urllib.request.urlopen(base + "/static/../server.py"); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown(); server.MGR.close()
