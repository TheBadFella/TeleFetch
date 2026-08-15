import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from database import (
    mark_media_completed, unmark_media_completed, update_media_downloaded_path,
    get_all_completed_media, delete_media_cache_item, delete_multiple_media_cache_items,
    get_cached_channels_summary
)


class TestFileManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_chan = "test_file_manager_chan_123"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        # Cleanup DB
        all_items = get_all_completed_media(channel_id=self.test_chan)
        delete_multiple_media_cache_items([(it["channel_id"], it["msg_id"]) for it in all_items])

    def test_add_and_query_completed_media(self):
        msg_id_1 = 1001
        msg_id_2 = 1002

        fpath_1 = os.path.join(self.temp_dir, "test1.mp4")
        fpath_2 = os.path.join(self.temp_dir, "test2.pdf")
        with open(fpath_1, "w") as f: f.write("video content")
        with open(fpath_2, "w") as f: f.write("pdf content")

        mark_media_completed(self.test_chan, msg_id_1)
        update_media_downloaded_path(self.test_chan, msg_id_1, fpath_1)

        mark_media_completed(self.test_chan, msg_id_2)
        update_media_downloaded_path(self.test_chan, msg_id_2, fpath_2)

        items = get_all_completed_media(channel_id=self.test_chan)
        msg_ids = [it["msg_id"] for it in items]
        self.assertIn(msg_id_1, msg_ids)
        self.assertIn(msg_id_2, msg_ids)

        # Test search filter
        search_res = get_all_completed_media(channel_id=self.test_chan, search="test1")
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["msg_id"], msg_id_1)

    def test_delete_media_cache_item(self):
        msg_id = 2001
        mark_media_completed(self.test_chan, msg_id)
        
        items_before = get_all_completed_media(channel_id=self.test_chan)
        self.assertTrue(any(it["msg_id"] == msg_id for it in items_before))

        delete_media_cache_item(self.test_chan, msg_id)

        items_after = get_all_completed_media(channel_id=self.test_chan)
        self.assertFalse(any(it["msg_id"] == msg_id for it in items_after))

    def test_bulk_delete_media_items(self):
        msg_ids = [3001, 3002, 3003]
        for m_id in msg_ids:
            mark_media_completed(self.test_chan, m_id)

        delete_multiple_media_cache_items([(self.test_chan, 3001), (self.test_chan, 3002)])

        remaining = get_all_completed_media(channel_id=self.test_chan)
        rem_ids = [it["msg_id"] for it in remaining]
        self.assertNotIn(3001, rem_ids)
        self.assertNotIn(3002, rem_ids)
        self.assertIn(3003, rem_ids)


if __name__ == "__main__":
    unittest.main()
