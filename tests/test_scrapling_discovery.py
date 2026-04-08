import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.search.engines.scrapling_engine import ScraplingEngine


def test_parallel_discovery_reduces_time(monkeypatch):
    engine = ScraplingEngine()

    # Mock DDGS.text to sleep per domain
    class FakeDDGS:
        def __init__(self, delays):
            self.delays = delays
            self.calls = 0

        def text(self, q, max_results=2):
            # simulate per-call delay
            delay = self.delays[self.calls % len(self.delays)]
            self.calls += 1
            time.sleep(delay)
            # return a fake result
            return [{"href": f"https://example{self.calls}.com/article", "title": "Title", "body": "Snippet"}]

    # Make target_sites with 3 domains
    target_sites = {"example1.com": {}, "example2.com": {}, "example3.com": {}}

    # Patch DDGS in engine._discover_urls scope
    delays = [1.5, 1.5, 1.5]
    fake = FakeDDGS(delays)

    monkeypatch.setattr('backend.search.engines.scrapling_engine.DDGS', lambda : fake)

    start = time.time()
    discovered = engine._discover_urls("test query", target_sites, max_results=5)
    duration = time.time() - start

    print(f"Discovered {len(discovered)} urls in {duration:.2f}s")

    # If discovery was parallel, wall-clock should be ~1.5s, not ~4.5s
    assert duration < 3.0


if __name__ == '__main__':
    test_parallel_discovery_reduces_time(None)
