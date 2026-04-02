"""Tests for the semantic cache."""

import time

import pytest

from src.cache.semantic_cache import SemanticCache


@pytest.fixture()
def cache():
    return SemanticCache(routing_ttl=1.0, output_ttl=0.5, capacity=10)


class TestMakeKey:
    def test_same_prompt_same_key(self):
        k1 = SemanticCache.make_key("hello world", "GL")
        k2 = SemanticCache.make_key("hello world", "GL")
        assert k1 == k2

    def test_normalisation(self):
        k1 = SemanticCache.make_key("  Hello   World  ", "GL")
        k2 = SemanticCache.make_key("hello world", "GL")
        assert k1 == k2

    def test_different_region_different_key(self):
        k1 = SemanticCache.make_key("hello", "GL")
        k2 = SemanticCache.make_key("hello", "OM")
        assert k1 != k2


class TestRoutingCache:
    def test_miss(self, cache):
        assert cache.get_routing("missing") is None

    def test_hit(self, cache):
        cache.set_routing("key1", {"skill_id": "test"})
        result = cache.get_routing("key1")
        assert result == {"skill_id": "test"}

    def test_expiry(self, cache):
        cache.set_routing("exp-key", "value")
        time.sleep(1.1)
        assert cache.get_routing("exp-key") is None


class TestOutputCache:
    def test_miss_returns_none(self, cache):
        assert cache.get_output("no-such-key") is None

    def test_hit(self, cache):
        cache.set_output("out-key", {"result": "data"})
        assert cache.get_output("out-key") == {"result": "data"}

    def test_expiry(self, cache):
        cache.set_output("exp-out", "val")
        time.sleep(0.6)
        assert cache.get_output("exp-out") is None


class TestCapacity:
    def test_lru_eviction(self):
        small_cache = SemanticCache(capacity=3, output_ttl=60)
        small_cache.set_output("k1", 1)
        small_cache.set_output("k2", 2)
        small_cache.set_output("k3", 3)
        small_cache.set_output("k4", 4)  # should evict k1
        assert small_cache.get_output("k1") is None
        assert small_cache.get_output("k4") == 4


class TestInvalidate:
    def test_flush_all(self, cache):
        cache.set_routing("r1", "v1")
        cache.set_output("o1", "v2")
        cache.invalidate()
        assert cache.get_routing("r1") is None
        assert cache.get_output("o1") is None

    def test_stats(self, cache):
        cache.set_routing("r", "v")
        cache.set_output("o", "v")
        stats = cache.stats()
        assert stats["routing_entries"] == 1
        assert stats["output_entries"] == 1
