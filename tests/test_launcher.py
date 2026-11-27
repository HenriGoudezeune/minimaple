import importlib.util
from pathlib import Path


def _launcher():
    p = Path(__file__).parent.parent / "windows" / "template" / "app" / "launcher.py"
    spec = importlib.util.spec_from_file_location("mm_launcher", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_versievergelijking_en_assets():
    L = _launcher()
    assert L.newer("0.3.0", "0.2.0") and L.newer("v0.10.0", "0.9.9") and L.newer("1.0", "0.9.9")
    assert not L.newer("0.2.0", "0.2.0") and not L.newer("0.2.0", "0.3.0") and not L.newer("0.3.0-rc1", "0.3.0")
    assert L.asset_for("win-setup") == "mini-Maple-setup.exe"
    assert L.asset_for("appimage") == "mini-Maple-x86_64.AppImage"
    assert L.asset_for("deb") == "mini-maple_amd64.deb"
    assert L.asset_for("mac").startswith("mini-Maple-macos-") and L.asset_for("win-zip") is None
    rel = {"assets": [{"name": "a.exe", "digest": "sha256:" + "ab" * 32}]}
    assert L._expected_sha(rel, "a.exe") == "ab" * 32 and L._expected_sha(rel, "b.exe") is None


def test_download_weigert_foute_url(tmp_path):
    L = _launcher()
    rel = {"tag_name": "v9.9.9", "assets": [{"name": "x.AppImage", "size": 1, "digest": "sha256:" + "0" * 64,
                                             "browser_download_url": "https://evil.example/x.AppImage"}]}
    try:
        L.download_asset(rel, "x.AppImage", tmp_path); assert False
    except RuntimeError as e:
        assert "URL" in str(e)
