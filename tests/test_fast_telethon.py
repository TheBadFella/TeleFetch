import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from utils.fast_telethon import fast_download_file, CHUNK_SIZE


class TestFastTelethon(unittest.TestCase):

    def test_chunk_size_validity(self):
        self.assertEqual(CHUNK_SIZE, 512 * 1024)

    def test_zero_size_guard(self):
        import asyncio
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(fast_download_file(None, None, "dummy.mp4", 0))
        self.assertFalse(res)
        loop.close()


if __name__ == "__main__":
    unittest.main()
