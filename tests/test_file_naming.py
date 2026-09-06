import unittest
import sys
import os
from datetime import datetime

# Add src to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from utils.file_utils import sanitize_filename, get_media_filename


class MockFile:
    def __init__(self, name=None, ext=None, size=1024, mime_type=None):
        self.name = name
        self.ext = ext
        self.size = size
        self.mime_type = mime_type


class MockDocument:
    def __init__(self, mime_type="", size=2048, attributes=None):
        self.mime_type = mime_type
        self.size = size
        self.attributes = attributes or []


class MockMessage:
    def __init__(self, id, date=None, photo=None, video=None, audio=None, voice=None, document=None, file=None):
        self.id = id
        self.date = date
        self.photo = photo
        self.video = video
        self.audio = audio
        self.voice = voice
        self.document = document
        self.file = file


class TestFileNaming(unittest.TestCase):

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("valid_name.mp4"), "valid_name.mp4")
        self.assertEqual(sanitize_filename("invalid:file?name*<>.mp4"), "invalid_file_name___.mp4")
        self.assertEqual(sanitize_filename("  spaces_and_dots...  "), "spaces_and_dots")
        self.assertEqual(sanitize_filename(""), "")

    def test_photo_naming_with_date(self):
        msg = MockMessage(
            id=101,
            date=datetime(2026, 1, 1, 12, 0, 0),
            photo=True,
            file=MockFile(ext=".jpg")
        )
        name = get_media_filename(msg, prefix_date=True)
        self.assertEqual(name, "2026-01-01_Photo_101.jpg")

    def test_photo_naming_without_date(self):
        msg = MockMessage(
            id=101,
            date=datetime(2026, 1, 1, 12, 0, 0),
            photo=True,
            file=MockFile(ext=".jpg")
        )
        name = get_media_filename(msg, prefix_date=False)
        self.assertEqual(name, "Photo_101.jpg")

    def test_video_with_original_name(self):
        msg = MockMessage(
            id=102,
            date=datetime(2026, 5, 20, 15, 30, 0),
            video=True,
            file=MockFile(name="presentation.mp4", ext=".mp4")
        )
        name = get_media_filename(msg, prefix_date=True)
        self.assertEqual(name, "2026-05-20_presentation.mp4")

    def test_video_without_original_name_fixes_random_id(self):
        # When video has no name attribute in Telegram
        msg = MockMessage(
            id=103,
            date=datetime(2026, 7, 10, 8, 0, 0),
            video=True,
            document=MockDocument(mime_type="video/mp4"),
            file=MockFile(name=None, ext=".mp4")
        )
        name = get_media_filename(msg, prefix_date=True)
        self.assertEqual(name, "2026-07-10_Video_103.mp4")

        # Without date prefix
        name_no_date = get_media_filename(msg, prefix_date=False)
        self.assertEqual(name_no_date, "Video_103.mp4")

    def test_audio_without_name(self):
        msg = MockMessage(
            id=104,
            date=datetime(2026, 3, 15, 10, 0, 0),
            audio=True,
            file=MockFile(name=None, ext=".mp3")
        )
        name = get_media_filename(msg, prefix_date=True)
        self.assertEqual(name, "2026-03-15_Audio_104.mp3")

    def test_document_types(self):
        # PDF document
        msg_pdf = MockMessage(
            id=105,
            date=datetime(2026, 2, 14),
            document=MockDocument(mime_type="application/pdf"),
            file=MockFile(name=None, ext=".pdf")
        )
        self.assertEqual(get_media_filename(msg_pdf, prefix_date=True), "2026-02-14_Document_105.pdf")

        # Named document
        msg_named = MockMessage(
            id=106,
            date=datetime(2026, 2, 14),
            file=MockFile(name="annual_report.xlsx", ext=".xlsx")
        )
        self.assertEqual(get_media_filename(msg_named, prefix_date=True), "2026-02-14_annual_report.xlsx")

    def test_no_duplicate_date_prefix(self):
        msg = MockMessage(
            id=107,
            date=datetime(2026, 1, 1),
            file=MockFile(name="2026-01-01_existing_name.mp4", ext=".mp4")
        )
        name = get_media_filename(msg, prefix_date=True)
        self.assertEqual(name, "2026-01-01_existing_name.mp4")

    def test_iso_string_date(self):
        msg = MockMessage(
            id=108,
            date="2026-08-15 18:30:00",
            photo=True,
            file=MockFile(ext=".jpg")
        )
        name = get_media_filename(msg, prefix_date=True)
        self.assertEqual(name, "2026-08-15_Photo_108.jpg")


if __name__ == "__main__":
    unittest.main()
