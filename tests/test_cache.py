import unittest
from pathlib import Path


class CacheTests(unittest.TestCase):
    def test_sqlite_cache_round_trips_json(self):
        from mythweaver.db.cache import SQLiteCache

        path = Path.cwd() / "output" / "test-cache" / "cache.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

        cache = SQLiteCache(path)
        cache.set_json("modrinth:search:winter", {"hits": [1, 2, 3]}, ttl_seconds=60)

        self.assertEqual(cache.get_json("modrinth:search:winter"), {"hits": [1, 2, 3]})


if __name__ == "__main__":
    unittest.main()
