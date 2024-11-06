import asyncio
import os
import aiohttp
import aiofiles
from dataclasses import dataclass
from typing import List,Dict, Optional, Callable
from enum import Enum
from datetime import datetime

class DownloadState(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

# # Equivalent of:
# def __init__(self, total_bytes: int, downloaded_bytes: int, speed: float, percentage: float):
#     self.total_bytes = total_bytes
#     self.downloaded_bytes = downloaded_bytes
#     self.speed = speed
#     self.percentage = percentage
@dataclass
class DownloadProgress:
    total_bytes: int
    downloaded_bytes: int
    speed: float  # bytes per second
    percentage: float

class DownloadTask:
    def __init__(self, url: str, filename: str, folder: str, episode: int):
        self.url = url
        self.filename = filename
        self.folder = folder
        self.episode = episode
        self.state = DownloadState.QUEUED
        self.progress = DownloadProgress(0, 0, 0.0, 0.0)
        self.start_time = None
        self.pause_event = asyncio.Event()
        self.cancel_event = asyncio.Event()
        self.pause_event.set()  # Not paused by default

    @property
    def file_path(self) -> str:
        return os.path.join(self.folder, f"{self.filename}.mp4")

    def pause(self):
        self.state = DownloadState.PAUSED
        self.pause_event.clear()

    def resume(self):
        self.state = DownloadState.DOWNLOADING
        self.pause_event.set()

    def cancel(self):
        self.state = DownloadState.CANCELLED
        self.cancel_event.set()


class DownloadManager:
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.download_queue = asyncio.Queue()
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self.session = aiohttp.ClientSession()
        workers = [self._worker() for _ in range(self.max_concurrent)]
        await asyncio.gather(*workers)

    async def stop(self):
        if self.session:
            await self.session.close()

    def add_download(self, url: str, filename: str, folder: str, episode: int) -> DownloadTask:
        task = DownloadTask(url, filename, folder, episode)
        asyncio.create_task(self.download_queue.put(task))
        self.active_downloads[task.file_path] = task
        return task

    async def _worker(self):
        while True:
            task: DownloadTask = await self.download_queue.get()

            if task.state == DownloadState.CANCELLED:
                self.download_queue.task_done()
                continue

            try:
                await self._process_download(task)
            except Exception as e:
                task.state = DownloadState.ERROR
                print(f"Error downloading {task.filename}: {str(e)}")
            finally:
                self.download_queue.task_done()

    async def _process_download(self, task: DownloadTask):
        if not os.path.exists(task.folder):
            os.makedirs(task.folder)

        # Create or clear the file
        async with aiofiles.open(task.file_path, 'wb') as f:
            pass

        task.start_time = datetime.now()
        task.state = DownloadState.DOWNLOADING

        async with self.session.get(task.url) as response:
            total_size = int(response.headers.get('content-length', 0))
            task.progress.total_bytes = total_size
            downloaded = 0

            async with aiofiles.open(task.file_path, 'wb') as file:
                async for chunk in response.content.iter_chunked(512 * 512):
                    # Check for cancellation
                    if task.cancel_event.is_set():
                        task.state = DownloadState.CANCELLED
                        return

                    # Handle pause
                    await task.pause_event.wait()

                    await file.write(chunk)
                    downloaded += len(chunk)

                    # Update progress
                    elapsed_time = (datetime.now() - task.start_time).total_seconds()
                    speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                    percentage = (downloaded / total_size * 100) if total_size > 0 else 0

                    task.progress = DownloadProgress(
                        total_bytes=total_size,
                        downloaded_bytes=downloaded,
                        speed=speed,
                        percentage=percentage
                    )

        if task.state != DownloadState.CANCELLED:
            task.state = DownloadState.COMPLETED


async def main():
    # Create download manager
    manager = DownloadManager(max_concurrent=3)

    # Start the download manager
    manager_task = asyncio.create_task(manager.start())

    download = manager.add_download(
        url="http://example.com/video1.mp4",
        filename="video1",
        folder="downloads",
        episode=1
    )
