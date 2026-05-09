import hashlib
import unittest
from pathlib import Path


class DownloaderTests(unittest.TestCase):
    def test_hash_verification_accepts_matching_file(self):
        from mythweaver.builders.downloader import verify_file_hashes

        path = Path.cwd() / "output" / "test-downloads" / "sample.jar"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = b"mythweaver"
        path.write_bytes(content)

        result = verify_file_hashes(
            path,
            {
                "sha1": hashlib.sha1(content).hexdigest(),
                "sha512": hashlib.sha512(content).hexdigest(),
            },
        )

        self.assertTrue(result)

    def test_hash_verification_rejects_mismatch(self):
        from mythweaver.builders.downloader import verify_file_hashes

        path = Path.cwd() / "output" / "test-downloads" / "bad.jar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"wrong")

        self.assertFalse(verify_file_hashes(path, {"sha1": "0" * 40, "sha512": "0" * 128}))


if __name__ == "__main__":
    unittest.main()
