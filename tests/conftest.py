"""Per-test tijdslimiet zonder pytest-timeout: SIGALRM (standaard 60 s, override met @pytest.mark.timeout(n)
of de omgevingsvariabele MINIMAPLE_TEST_TIMEOUT)."""
import os
import signal

import pytest

DEFAULT = int(os.environ.get("MINIMAPLE_TEST_TIMEOUT", "60"))


def pytest_configure(config):
    config.addinivalue_line("markers", "timeout(seconds): tijdslimiet voor deze test")


@pytest.fixture(autouse=True)
def _test_timeout(request):
    if not hasattr(signal, "SIGALRM"):
        yield
        return
    m = request.node.get_closest_marker("timeout")
    secs = int(m.args[0]) if m and m.args else DEFAULT

    def boom(signum, frame):
        raise TimeoutError(f"test duurde langer dan {secs} s")
    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(secs)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
