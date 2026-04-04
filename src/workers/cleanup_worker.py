import asyncio
import os
import shutil
import sys
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QThread, Signal
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resource_utils import get_project_root


class CleanupWorkerSignals(QObject):
    connection_test_completed = Signal(bool, str)
    scan_progress = Signal(int, int, str)
    scan_completed = Signal(object, str)
    leave_completed = Signal(object)
    error = Signal(str)


class CleanupWorker(QThread):
    LOGIN_TIMEOUT_SECONDS = 30

    def __init__(self, session_name="default_session", parent=None):
        super().__init__(parent)
        self.session_name = session_name
        self.session_path = None
        self.cleanup_session_path = None
        self.signals = CleanupWorkerSignals()
        self.loop = None
        self.client = None
        self.api_id = 0
        self.api_hash = ""

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stop(self):
        if self.loop:
            async def _cleanup():
                tasks = [t for t in asyncio.all_tasks(self.loop) if t is not asyncio.current_task()]
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                if self.client:
                    await self.client.disconnect()

            future = asyncio.run_coroutine_threadsafe(_cleanup(), self.loop)
            try:
                future.result(timeout=2.0)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)

    def _load_credentials(self):
        env_path = os.path.join(get_project_root(), ".env")
        load_dotenv(dotenv_path=env_path, override=True)
        api_id_str = (os.getenv("API_ID") or "").strip("'").strip('"')
        api_hash = (os.getenv("API_HASH") or "").strip("'").strip('"')
        self.api_id = int(api_id_str) if api_id_str.isdigit() else 0
        self.api_hash = api_hash

    async def _ensure_client(self):
        self._load_credentials()
        if not self.api_id or not self.api_hash:
            raise Exception("API_ID or API_HASH is missing from .env.")

        self.session_path = os.path.join(get_project_root(), self.session_name)
        self.cleanup_session_path = os.path.join(get_project_root(), f"{self.session_name}_cleanup")
        source_session_file = f"{self.session_path}.session"
        cleanup_session_file = f"{self.cleanup_session_path}.session"

        if not os.path.exists(source_session_file):
            raise Exception("Main Telegram session file was not found. Please log in first.")

        source_mtime = os.path.getmtime(source_session_file)
        cleanup_mtime = os.path.getmtime(cleanup_session_file) if os.path.exists(cleanup_session_file) else -1
        if cleanup_mtime < source_mtime:
            if self.client:
                await self.client.disconnect()
                self.client = None
            shutil.copy2(source_session_file, cleanup_session_file)

        if self.client is None or self.client.api_id != self.api_id or self.client.api_hash != self.api_hash:
            if self.client:
                await self.client.disconnect()
            self.client = TelegramClient(self.cleanup_session_path, self.api_id, self.api_hash, loop=self.loop)

        await asyncio.wait_for(self.client.connect(), timeout=self.LOGIN_TIMEOUT_SECONDS)
        if not await asyncio.wait_for(self.client.is_user_authorized(), timeout=self.LOGIN_TIMEOUT_SECONDS):
            raise Exception("Telegram session is not authorized. Please log in first.")
        return self.client

    def test_connection(self):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._test_connection_coro(), self.loop)

    def scan_inactive_items(self, cutoff_iso):
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._scan_joined_items_coro(cutoff_iso=cutoff_iso, filter_stale_only=True),
                self.loop
            )

    def scan_all_joined_items(self):
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self._scan_joined_items_coro(cutoff_iso=None, filter_stale_only=False),
                self.loop
            )

    def leave_items(self, item_ids):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._leave_items_coro(item_ids), self.loop)

    def _parse_cutoff(self, cutoff_iso):
        cutoff = datetime.fromisoformat(cutoff_iso)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        return cutoff

    def _normalize_datetime(self, value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _is_cleanup_candidate(self, dialog):
        entity = dialog.entity
        if getattr(dialog, "is_user", False):
            return False
        if getattr(dialog, "is_group", False):
            return True
        if getattr(dialog, "is_channel", False):
            return True
        return isinstance(entity, (Chat, Channel))

    def _cleanup_type_label(self, dialog, entity):
        if getattr(dialog, "is_channel", False) and not getattr(dialog, "is_group", False):
            return "Channel"
        if isinstance(entity, Chat):
            return "Group"
        if getattr(entity, "gigagroup", False):
            return "Gigagroup"
        if getattr(entity, "megagroup", False):
            return "Supergroup"
        if isinstance(entity, Channel):
            return "Channel"
        return "Joined Chat"

    def _cleanup_status_label(self, dialog, entity, last_message_dt):
        if getattr(entity, "deactivated", False):
            return "Deactivated"
        if getattr(entity, "restricted", False):
            return "Restricted"
        if getattr(entity, "scam", False):
            return "Flagged Scam"
        if getattr(entity, "fake", False):
            return "Flagged Fake"
        if getattr(dialog, "is_channel", False) and getattr(entity, "broadcast", False):
            if last_message_dt is None:
                return "Channel, no visible posts"
            return "Active Channel"
        if last_message_dt is None:
            return "No visible messages"
        return "Active"

    async def _test_connection_coro(self):
        try:
            client = await self._ensure_client()
            me = await asyncio.wait_for(client.get_me(), timeout=self.LOGIN_TIMEOUT_SECONDS)
            label = getattr(me, "username", None) or getattr(me, "first_name", None) or "authorized account"
            self.signals.connection_test_completed.emit(True, f"Connected successfully as {label}.")
        except asyncio.TimeoutError:
            self.signals.connection_test_completed.emit(
                False,
                f"Telegram connection timed out after {self.LOGIN_TIMEOUT_SECONDS} seconds."
            )
        except Exception as e:
            self.signals.connection_test_completed.emit(False, str(e))

    async def _scan_joined_items_coro(self, cutoff_iso=None, filter_stale_only=True):
        try:
            client = await self._ensure_client()
            cutoff = self._parse_cutoff(cutoff_iso) if cutoff_iso else None
            rows = []
            seen_ids = set()
            scanned_dialogs = 0

            async def collect_dialogs(archived=False):
                nonlocal scanned_dialogs
                phase = "archived" if archived else "active"
                async for dialog in client.iter_dialogs(archived=archived):
                    if dialog.id in seen_ids:
                        continue
                    entity = dialog.entity
                    if not self._is_cleanup_candidate(dialog):
                        continue

                    seen_ids.add(dialog.id)
                    scanned_dialogs += 1
                    last_message = getattr(dialog, "message", None)
                    last_message_dt = self._normalize_datetime(
                        getattr(last_message, "date", None) or getattr(dialog, "date", None)
                    )

                    if filter_stale_only and cutoff is not None and last_message_dt is not None and last_message_dt >= cutoff:
                        continue

                    username = getattr(entity, "username", None)
                    rows.append({
                        "id": str(dialog.id),
                        "title": dialog.title or f"Dialog {dialog.id}",
                        "type": self._cleanup_type_label(dialog, entity),
                        "status": self._cleanup_status_label(dialog, entity, last_message_dt),
                        "last_message_iso": last_message_dt.isoformat() if last_message_dt else "",
                        "last_message_display": last_message_dt.strftime("%Y-%m-%d %H:%M UTC") if last_message_dt else "No messages found",
                        "archived": bool(archived),
                        "username": f"@{username}" if username else "",
                        "sort_key": last_message_dt or datetime(1970, 1, 1, tzinfo=timezone.utc)
                    })

                    if scanned_dialogs == 1 or scanned_dialogs % 25 == 0:
                        self.signals.scan_progress.emit(scanned_dialogs, len(rows), phase)

                self.signals.scan_progress.emit(scanned_dialogs, len(rows), phase)

            await collect_dialogs(archived=False)
            await collect_dialogs(archived=True)

            rows.sort(key=lambda item: (item["sort_key"], item["title"].lower()))
            for row in rows:
                row.pop("sort_key", None)

            result_label = cutoff.date().isoformat() if cutoff else "__ALL__"
            self.signals.scan_completed.emit(rows, result_label)
        except Exception as e:
            self.signals.error.emit(f"Joined item scan failed: {e}")

    async def _leave_items_coro(self, item_ids):
        try:
            client = await self._ensure_client()
            results = {"left_ids": [], "failed": []}
            for item_id in item_ids:
                try:
                    entity = await client.get_entity(int(item_id))
                    if not isinstance(entity, (Channel, Chat)):
                        raise Exception("Dialog is not a supported joined chat or channel.")
                    await client.delete_dialog(entity)
                    results["left_ids"].append(str(item_id))
                except Exception as leave_error:
                    results["failed"].append({"id": str(item_id), "error": str(leave_error)})
            self.signals.leave_completed.emit(results)
        except Exception as e:
            self.signals.error.emit(f"Leaving joined items failed: {e}")
