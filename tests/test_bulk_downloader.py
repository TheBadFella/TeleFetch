import unittest
import sys
import os
import tempfile
import shutil
import asyncio

# Add src to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core_downloader import get_unique_filepath, get_messages_by_type


class MockDocument:
    def __init__(self, mime_type="", size=1024):
        self.mime_type = mime_type
        self.size = size


class MockMessage:
    def __init__(self, id, media=None, photo=None, video=None, document=None, message=""):
        self.id = id
        self.media = media
        self.photo = photo
        self.video = video
        self.document = document
        self.message = message


class MockTelethonClient:
    def __init__(self, messages):
        self._messages = messages

    async def get_messages(self, channel, **kwargs):
        filter_obj = kwargs.get("filter")
        limit = kwargs.get("limit")
        msgs = self._messages
        
        if filter_obj is not None:
            # Simulate filter
            f_name = filter_obj.__class__.__name__
            if "Photo" in f_name:
                msgs = [m for m in msgs if m.photo is not None]
            elif "Video" in f_name:
                msgs = [m for m in msgs if m.video is not None]
            elif "Document" in f_name:
                msgs = [m for m in msgs if m.document is not None]
            elif "Music" in f_name or "Voice" in f_name:
                msgs = [m for m in msgs if m.document and m.document.mime_type.startswith("audio/")]
                
        if limit is not None:
            msgs = msgs[:limit]
        return msgs


class TestBulkDownloader(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_unique_filepath_non_destructive(self):
        # 1. Path generation when file does not exist (should NOT create file)
        target = get_unique_filepath(self.temp_dir, "test.mp4")
        self.assertEqual(os.path.basename(target), "test.mp4")
        self.assertFalse(os.path.exists(target), "get_unique_filepath must not create empty files on disk beforehand")

        # 2. When file with content exists
        with open(target, "w") as f:
            f.write("content")
        
        target2 = get_unique_filepath(self.temp_dir, "test.mp4")
        self.assertEqual(os.path.basename(target2), "test (2).mp4")

        # 3. When 0-byte file exists (abandoned attempt), it should reuse it
        empty_file = os.path.join(self.temp_dir, "empty.mp4")
        with open(empty_file, "w"):
            pass
        target3 = get_unique_filepath(self.temp_dir, "empty.mp4")
        self.assertEqual(target3, empty_file)

    def test_get_messages_by_type_filtering(self):
        raw_msgs = [
            MockMessage(id=1, media=True, photo=True),
            MockMessage(id=2, media=True, video=True),
            MockMessage(id=3, media=True, document=MockDocument(mime_type="application/pdf")),
            MockMessage(id=4, media=True, document=MockDocument(mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")), # docx
            MockMessage(id=5, media=True, document=MockDocument(mime_type="application/zip")),
            MockMessage(id=6, media=True, document=MockDocument(mime_type="audio/mpeg")),
            MockMessage(id=7, media=None, message="Hello plain text chat message") # Text only
        ]

        client = MockTelethonClient(raw_msgs)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 1. Images (choice 1)
        photos = loop.run_until_complete(get_messages_by_type(client, "test_channel", 1))
        self.assertEqual([m.id for m in photos], [1])

        # 2. Videos (choice 2)
        videos = loop.run_until_complete(get_messages_by_type(client, "test_channel", 2))
        self.assertEqual([m.id for m in videos], [2])

        # 3. Documents (choice 3) - MUST include docx, pdf, zip (not just pdfs!)
        docs = loop.run_until_complete(get_messages_by_type(client, "test_channel", 3))
        self.assertEqual(sorted([m.id for m in docs]), [3, 4, 5, 6])

        # 4. ZIPs (choice 4)
        zips = loop.run_until_complete(get_messages_by_type(client, "test_channel", 4))
        self.assertEqual([m.id for m in zips], [5])

        # 5. Audio (choice 5)
        audios = loop.run_until_complete(get_messages_by_type(client, "test_channel", 5))
        self.assertEqual([m.id for m in audios], [6])

        # 6. All Media (choice 6) - MUST exclude text-only message (id=7)
        all_media = loop.run_until_complete(get_messages_by_type(client, "test_channel", 6))
        self.assertNotIn(7, [m.id for m in all_media])
        self.assertEqual(len(all_media), 6)

        loop.close()

    def test_ghost_card_resolution_matching(self):
        # Verify card matching logic for multi-category bulk downloads
        card_widgets = {
            "mychannel_1": "Card_Images",
            "mychannel_2": "Card_Videos",
            "mychannel_3": "Card_Docs",
        }

        def resolve_card(task_id, data):
            ch_resolved = str(data.get("channel_input", ""))
            original_in = str(data.get("original_input", ""))
            m_id = str(data.get("media_id", 6))
            topic_id = str(data.get("topic_id")) if data.get("topic_id") is not None else None

            matched_id = None
            for old_id, card in list(card_widgets.items()):
                parts = old_id.split('_')
                if len(parts) >= 3:
                    old_chan = "_".join(parts[:-2])
                    old_topic = parts[-2]
                    old_media = parts[-1]
                elif len(parts) == 2:
                    old_chan = parts[0]
                    old_topic = None
                    old_media = parts[1]
                else:
                    continue

                if old_media != m_id:
                    continue
                if topic_id is not None and old_topic != topic_id:
                    continue

                if (old_chan == original_in or 
                    old_chan == ch_resolved or 
                    old_chan.replace('-100', '', 1) == ch_resolved.replace('-100', '', 1)):
                    matched_id = old_id
                    break
            return matched_id

        # Resolving Videos (-100999_2) MUST match mychannel_2, NOT mychannel_1
        data_videos = {
            "task_id": "-100999_2",
            "channel_input": "-100999",
            "original_input": "mychannel",
            "media_id": 2
        }
        self.assertEqual(resolve_card("-100999_2", data_videos), "mychannel_2")

        # Resolving Images (-100999_1) MUST match mychannel_1
        data_images = {
            "task_id": "-100999_1",
            "channel_input": "-100999",
            "original_input": "mychannel",
            "media_id": 1
        }
        self.assertEqual(resolve_card("-100999_1", data_images), "mychannel_1")

    def test_unmark_media_completed(self):
        from database import mark_media_completed, unmark_media_completed, get_completed_state_db
        test_chan = "999888777"
        test_msg_id = 424242

        mark_media_completed(test_chan, test_msg_id)
        completed = get_completed_state_db()
        self.assertIn((test_chan, test_msg_id), completed)

        unmark_media_completed(test_chan, test_msg_id)
        completed_after = get_completed_state_db()
        self.assertNotIn((test_chan, test_msg_id), completed_after)


if __name__ == "__main__":
    unittest.main()
