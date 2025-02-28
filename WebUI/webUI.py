import streamlit as st
import json
from bs4 import BeautifulSoup
import requests
import asyncio
import os
import aiohttp
import aiofiles
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime
import re
import time
import psutil
import math
from pathlib import Path

st.set_page_config(
    page_title="Anime Downloader",
    page_icon="⛩️"
)

with open("../WebUI/setup.json", "r") as f:
    setup = json.load(f)

base_url = setup["gogoanime_main"]
download_folder = setup["downloads"]
captcha_v3 = setup["captcha_v3"]
download_quality = int(setup["download_quality"])
max_threads = setup["max_threads"]
preview_status = setup["preview_status"]


class DownloadState(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    total_bytes: int
    downloaded_bytes: int
    speed: float
    percentage: float


class DownloadTask:
    def __init__(self, url: str, filename: str, folder: str, episode: int):
        self.url = url
        self.filename = filename
        self.folder = folder
        self.episode = episode
        self.file_path = os.path.join(folder, filename)
        self.state = DownloadState.QUEUED
        self.progress = DownloadProgress(0, 0, 0, 0)
        self.start_time = None
        self.status_text = None
        self.cancel_event = asyncio.Event()
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Initially not paused

    def setup_progress_ui(self):
        col1, col2 = st.columns([0.1, 0.9])

        # with col1:
        #     button_key = f"play_pause_button_{self.episode}"
        #     state_key = f"download_state_{self.episode}"
        #
        #     # Initialize state if not exists
        #     if state_key not in st.session_state:
        #         st.session_state[state_key] = self.state
        #
        #     if st.session_state[state_key] == DownloadState.PAUSED:
        #         if st.button("▶️", key=button_key):
        #             self.resume()
        #             st.session_state[state_key] = DownloadState.DOWNLOADING
        #     else:
        #         if st.button("⏸️", key=button_key):
        #             self.pause()
        #             st.session_state[state_key] = DownloadState.PAUSED
        #
        with col2:
            self.status_text = st.empty()
            self.progress_bar = st.progress(0)

    def update_progress(self):
        if self.progress_bar and self.status_text:
            self.progress_bar.progress(int(self.progress.percentage) / 100)
            self.status_text.text(
                f"Episode {self.episode}: {self.progress.percentage:.1f}% "
                f"({self.progress.downloaded_bytes / 1024 / 1024:.1f} MB / "
                f"{self.progress.total_bytes / 1024 / 1024:.1f} MB) - "
                f"Speed: {self.progress.speed / 1024 / 1024:.1f} MB/s"
            )

            # Update the download page manager
            if 'download_page_manager' in st.session_state:
                st.session_state['download_page_manager'].update_download_progress(
                    url=self.url,
                    status='downloading' if self.state == DownloadState.DOWNLOADING else str(self.state.value),
                    progress=self.progress.percentage,
                    downloaded_bytes=self.progress.downloaded_bytes,
                    total_bytes=self.progress.total_bytes,
                    speed=self.progress.speed
                )

    # def pause(self):
    #     print("DownloadTask pause")
    #     """Pause the download"""
    #     self.pause_event.clear()
    #     self.state = DownloadState.PAUSED
    #
    # def resume(self):
    #     print("DownloadTask pause")
    #     """Resume the download"""
    #     self.pause_event.set()
    #     self.state = DownloadState.DOWNLOADING


class DownloadManager:
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.download_queue = asyncio.Queue()
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = True
        self.worker_tasks = []

    async def start(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

        # Create worker tasks but don't wait for them
        self.worker_tasks = [
            asyncio.create_task(self._worker())
            for _ in range(self.max_concurrent)
        ]

    async def stop(self):
        """Stop the download manager and clean up"""
        self.running = False

        # Cancel all remaining downloads
        while not self.download_queue.empty():
            try:
                task = self.download_queue.get_nowait()
                task.state = DownloadState.CANCELLED
                self.download_queue.task_done()
            except asyncio.QueueEmpty:
                break

        # Cancel all worker tasks
        for worker_task in self.worker_tasks:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        # Close the session
        if self.session:
            await self.session.close()
            self.session = None

        self.worker_tasks = []

    async def add_download(self, url: str, filename: str, folder: str, episode: int) -> DownloadTask:
        """Add a new download task to the queue"""
        task = DownloadTask(url, filename, folder, episode)
        task.setup_progress_ui()
        # Now we await putting the task in the queue
        await self.download_queue.put(task)
        self.active_downloads[task.file_path] = task
        return task

    async def _worker(self):
        """Worker coroutine that processes downloads from the queue"""
        try:
            while self.running:
                try:
                    # Use timeout to allow checking self.running periodically
                    task: DownloadTask = await asyncio.wait_for(
                        self.download_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

                if task.state == DownloadState.CANCELLED:
                    self.download_queue.task_done()
                    continue

                try:
                    while task.state == DownloadState.PAUSED:
                        await task.pause_event.wait()

                    await self._process_download(task)
                except Exception as e:
                    task.state = DownloadState.ERROR
                    if task.status_text:
                        task.status_text.error(f"Error downloading episode {task.episode}: {str(e)}")
                finally:
                    self.download_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Worker error: {str(e)}")

    async def _process_download(self, task: DownloadTask):
        """Process a single download task"""
        if not os.path.exists(task.folder):
            os.makedirs(task.folder)

        task.start_time = datetime.now()
        task.state = DownloadState.DOWNLOADING

        try:
            async with self.session.get(task.url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}: Failed to download {task.url}")

                total_size = int(response.headers.get('content-length', 0))
                task.progress.total_bytes = total_size
                downloaded = 0

                async with aiofiles.open(task.file_path, 'wb') as file:
                    async for chunk in response.content.iter_chunked(512 * 512):
                        if task.cancel_event.is_set():
                            task.state = DownloadState.CANCELLED
                            return

                        if task.pause_event is not None:
                            await task.pause_event.wait()

                        await file.write(chunk)
                        downloaded += len(chunk)

                        elapsed_time = (datetime.now() - task.start_time).total_seconds()
                        speed = downloaded / elapsed_time if elapsed_time > 0 else 0
                        percentage = (downloaded / total_size * 100) if total_size > 0 else 0

                        task.progress = DownloadProgress(
                            total_bytes=total_size,
                            downloaded_bytes=downloaded,
                            speed=speed,
                            percentage=percentage
                        )
                        task.update_progress()

            if downloaded == 0:
                raise Exception("Downloaded file is empty")

            if task.state != DownloadState.CANCELLED:
                task.state = DownloadState.COMPLETED
                if task.status_text:
                    task.status_text.success(f"Episode {task.episode} downloaded successfully!")

        except Exception as e:
            # If download fails, remove the empty file
            if os.path.exists(task.file_path):
                os.remove(task.file_path)
            task.state = DownloadState.ERROR
            if task.status_text:
                task.status_text.error(f"Download error for episode {task.episode}: {str(e)}")
            raise

    # async def pause_download(self, file_path: str):
    #     """Pause a download"""
    #     if file_path in self.active_downloads:
    #         task = self.active_downloads[file_path]
    #         if task.state == DownloadState.DOWNLOADING:
    #             task.state = DownloadState.PAUSED
    #             if task.pause_event:
    #                 task.pause_event.clear()  # Block until resumed
    #             if task.status_text:
    #                 task.status_text.info(f"Paused download for episode {task.episode}")
    #
    # async def resume_download(self, file_path: str):
    #     """Resume a paused download"""
    #     if file_path in self.active_downloads:
    #         task = self.active_downloads[file_path]
    #         if task.state == DownloadState.PAUSED:
    #             task.state = DownloadState.DOWNLOADING
    #             if task.pause_event:
    #                 task.pause_event.set()  # Allow download to continue
    #             if task.status_text:
    #                 task.status_text.info(f"Resumed download for episode {task.episode}")


@dataclass
class AnimeDownloadItem:
    name: str
    url: str
    episodes: List[int]
    total_episodes: int

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data['name'],
            url=data['url'],
            episodes=data['episodes'],
            total_episodes=data['total_episodes']
        )


# Manage Batch page
class BatchManager:
    def __init__(self):
        self.download_list: List[AnimeDownloadItem] = []
        self.save_directory = Path("batch_lists")
        self.save_directory.mkdir(exist_ok=True)

    def add_item(self, item: AnimeDownloadItem):
        # Check for duplicates
        if any(existing.name == item.name for existing in self.download_list):
            raise ValueError(f"Anime '{item.name}' already exists in the batch list")
        self.download_list.append(item)

    def remove_item(self, index: int):
        if 0 <= index < len(self.download_list):
            return self.download_list.pop(index)
        raise IndexError("Invalid index for batch list removal")

    def clear_list(self):
        self.download_list.clear()

    def get_all_saved_lists(self) -> List[Path]:
        """Returns a list of all saved batch files."""
        return sorted(self.save_directory.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    def save_list(self, filename: str) -> Path:
        """
        Save the current batch list to a JSON file.
        Returns the path to the saved file.
        """
        if not filename.endswith('.json'):
            filename += '.json'

        save_path = self.save_directory / filename

        # Create backup if file exists
        if save_path.exists():
            col1, col2 = st.columns(2)

            with st.warning(f"File '{filename} already exists!"):
                if col1.button("Replace Existing File"):
                    try:
                        # Create backup before replacing
                        backup_name = f"{save_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        backup_path = self.save_directory / backup_name
                        save_path.rename(backup_path)
                        st.success(f"Backup created: {backup_name}")
                        print(f"replacing with {backup_name}")
                    except Exception as e:
                        raise IOError(f"Failed to create backup: {str(e)}")
                else:
                    return None  # User didn't confirm replacement

        data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "items": [item.to_dict() for item in self.download_list]
        }

        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return save_path
        except Exception as e:
            raise IOError(f"Failed to save batch list: {str(e)}")

    def load_list(self, filename: Path) -> bool:
        """
        Load a batch list from a JSON file.
        Returns True if successful, raises exception otherwise.
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate file format
            if not isinstance(data, dict) or "items" not in data:
                raise ValueError("Invalid batch list file format")

            # Create new list from loaded data
            new_list = []
            for item_data in data["items"]:
                try:
                    new_list.append(AnimeDownloadItem.from_dict(item_data))
                except (KeyError, TypeError) as e:
                    raise ValueError(f"Invalid item data in batch list: {str(e)}")

            # Only update if all items were loaded successfully
            self.download_list = new_list
            return True

        except json.JSONDecodeError:
            raise ValueError("Invalid JSON format in batch list file")
        except Exception as e:
            raise IOError(f"Failed to load batch list: {str(e)}")

    def delete_list(self, filename: Path) -> bool:
        try:
            Path(filename).unlink()
            return True
        except FileNotFoundError:
            return False

    def merge_list(self, filename: Path) -> int:
        """
        Merge another batch list into the current one.
        Returns the number of new items added.
        """
        temp_manager = BatchManager()
        temp_manager.load_list(filename)

        added_count = 0
        for item in temp_manager.download_list:
            try:
                self.add_item(item)
                added_count += 1
            except ValueError:
                continue  # Skip duplicates

        return added_count

    def export_list(self, filename: str, format: str = 'json') -> Path:
        """
        Export the batch list in different formats.
        Currently supports: json, txt
        Returns the path to the exported file.
        """
        export_path = self.save_directory / filename

        if format == 'json':
            return self.save_list(filename)
        elif format == 'txt':
            with open(export_path.with_suffix('.txt'), 'w', encoding='utf-8') as f:
                for item in self.download_list:
                    f.write(f"Anime: {item.name}\n")
                    f.write(f"Episodes: {', '.join(map(str, item.episodes))}\n")
                    f.write(f"Total Episodes: {item.total_episodes}\n")
                    f.write("-" * 50 + "\n")
            return export_path.with_suffix('.txt')
        else:
            raise ValueError(f"Unsupported export format: {format}")


class DownloadPageManager:
    def __init__(self):
        if 'downloads' not in st.session_state:
            st.session_state['downloads'] = []
        if 'download_manager' not in st.session_state:
            st.session_state['download_manager'] = DownloadManager(max_concurrent=max_threads)
        if 'active_downloads' not in st.session_state:
            st.session_state['active_downloads'] = set()

    async def start_downloads(self):
        """Process any queued downloads that aren't already being processed"""
        download_manager = st.session_state['download_manager']

        # Start download manager if needed
        if not hasattr(download_manager, 'session') or download_manager.session is None:
            await download_manager.start()

        downloads_by_anime = {}
        for download in self.downloads:
            if download['status'] == 'queued' and download['url'] not in st.session_state['active_downloads']:
                anime_name = download['anime-name']
                if anime_name not in downloads_by_anime:
                    downloads_by_anime[anime_name] = []
                downloads_by_anime[anime_name].append(download)

        for anime_name, anime_downloads in downloads_by_anime.items():
            try:
                episodes = [{
                    'url': download['url'],
                    'episode': download['episode']
                } for download in anime_downloads]

                for download in anime_downloads:
                    st.session_state['active_downloads'].add(download['url'])

                # Start the download process
                asyncio.create_task(self.process_anime_downloads(
                    episodes=episodes,
                    anime_name=anime_name,
                    save_path=anime_downloads[0]['save_path']
                ))

            except Exception as e:
                st.error(f"Error starting downloads for {anime_name}: {str(e)}")

    async def process_anime_downloads(self, episodes: List[dict], anime_name: str, save_path: str):
        """Process downloads for a specific anime"""
        try:
            await download_episodes(episodes, anime_name, save_path)
        except Exception as e:
            st.error(f"Error downloading {anime_name}: {str(e)}")
        finally:
            # Remove from active downloads
            for episode in episodes:
                st.session_state['active_downloads'].discard(episode['url'])

    def update_download_progress(self, url: str, status: str, progress: float = 0,
                                 downloaded_bytes: int = 0, total_bytes: int = 0,
                                 speed: float = 0):
        """Update the progress of a specific download"""
        for download in self.downloads:
            if download['url'] == url:
                download['status'] = status
                download['progress'] = progress
                download['downloaded_bytes'] = downloaded_bytes
                download['total_bytes'] = total_bytes
                download['speed'] = speed
                break


def downloads_page():
    st.title("Downloads")

    if 'download_page_manager' not in st.session_state:
        st.session_state['download_page_manager'] = DownloadPageManager()

    if st.session_state['downloads']:
        asyncio.create_task(st.session_state['download_page_manager'].start_downloads())

    downloads_by_anime = {}
    for download in st.session_state['downloads']:
        anime_name = download['anime_name']
        if anime_name not in downloads_by_anime:
            downloads_by_anime[anime_name] = []
        downloads_by_anime[anime_name].append(download)

    # Display downloads grouped by anime
    for anime_name, downloads in downloads_by_anime.items():
        with st.expander(f"{anime_name} ({len(downloads)} episodes)", expanded=True):
            for download in downloads:
                col1, col2, col3 = st.columns([2, 6, 2])

                # Episode info
                with col1:
                    st.write(f"Episode {download['episode']}")

                # Progress bar
                with col2:
                    if download['status'] == 'queued':
                        st.progress(0)
                        st.write("Queued")
                    elif download['status'] == 'downloading':
                        progress = download['progress'] / 100
                        st.progress(progress)
                        st.write(
                            f"{download['progress']:.1f}% - "
                            f"{download['downloaded_bytes'] / 1024 / 1024:.1f}MB / "
                            f"{download['total_bytes'] / 1024 / 1024:.1f}MB - "
                            f"{download['speed'] / 1024 / 1024:.1f}MB/s"
                        )
                    elif download['status'] == 'completed':
                        st.progress(1.0)
                        st.write("Completed")
                    elif download['status'] == 'error':
                        st.error("Download failed")

                # Controls
                with col3:
                    if download['status'] == 'queued':
                        st.button("Cancel", key=f"cancel_{anime_name}_{download['episode']}")
                    elif download['status'] == 'downloading':
                        col3_1, col3_2 = st.columns(2)
                        with col3_1:
                            st.button("Pause", key=f"pause_{anime_name}_{download['episode']}")
                        with col3_2:
                            st.button("Cancel", key=f"cancel_{anime_name}_{download['episode']}")


def batch_download_page():
    if 'batch_manager' not in st.session_state:
        st.session_state['batch_manager'] = BatchManager()

    st.title("Batch Download Manager")

    tab1, tab2, tab3, tab4 = st.tabs(["Add Anime", "View Current List", "Manage List", "Start Download"])

    with tab1:
        st.header("Add Anime to Batch")
        col1, col2 = st.columns([0.65, 0.35])

        with col1:
            anime_name = col1.text_input("Search Anime:", key="batch_search")
            selected_url = None  # Initialize selected_url outside the conditional block
            animes = []  # Initialize animes list

            if anime_name:
                response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={anime_name}").text,
                                         "html.parser")
                try:
                    pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
                    animes = [anime for page in pages for anime in get_names(
                        BeautifulSoup(requests.get(f"{base_url}/search.html{page.a.get('href')}").text, "html.parser"))]
                except AttributeError:
                    animes = get_names(response)

                if animes:
                    selected_anime = st.radio("Select Anime:", [name for name, _ in animes])
                    if selected_anime:
                        selected_index = [name for name, _ in animes].index(selected_anime)
                        selected_url = animes[selected_index][1]

                        # Get episode count
                        response = BeautifulSoup(requests.get(f"{base_url}{selected_url}").text, "html.parser")
                        movie_id = response.find("input", {"id": "movie_id"}).get("value")
                        last_ep = response.find("ul", {"id": "episode_page"}).find_all("a")[-1].get("ep_end")
                        total_episodes = int(last_ep)

                        # Episode selection
                        st.write(f"Total Episodes: {total_episodes}")
                        episode_selection = st.text_input(
                            "Enter episodes (e.g., 1 3 5-7):",
                            key="batch_episode_selection"
                        )

                        if st.button("Add to Batch"):
                            try:
                                selected_episodes = parse_episode_selection(episode_selection, total_episodes)
                                if selected_episodes:
                                    new_item = AnimeDownloadItem(
                                        name=selected_anime,
                                        url=selected_url,
                                        episodes=selected_episodes,
                                        total_episodes=total_episodes
                                    )
                                    st.session_state['batch_manager'].add_item(new_item)
                                    st.success(f"Added {selected_anime} to batch list")
                                else:
                                    st.error("Invalid episode selection")
                            except ValueError:
                                st.error("Invalid episode selection format")

        with col2:
            if animes and selected_url:
                if preview_status == "Plain Preview":
                    display_anime_preview_vanilla(selected_url)
                elif preview_status == "Styled Preview":
                    display_anime_preview_markdown(selected_url)

    with tab2:
        st.header("View Current list")
        if st.session_state['batch_manager'].download_list:
            selected_anime = st.radio(
                "Select anime to modify:",
                [item.name for item in st.session_state['batch_manager'].download_list]
            )

            if selected_anime:
                # Find the selected anime item
                anime_item = next(
                    item for item in st.session_state['batch_manager'].download_list
                    if item.name == selected_anime
                )

                # Display current episodes
                st.write("Current episodes:",
                         ', '.join(str(ep) for ep in sorted(anime_item.episodes)))

                # Modify episodes
                new_episodes = st.text_input(
                    "Modify episodes (e.g., 1 3 5-7):",
                    key=f"modify_{selected_anime}"
                )

                if st.button("Update Episodes"):
                    try:
                        new_episode_list = parse_episode_selection(
                            new_episodes,
                            anime_item.total_episodes
                        )
                        if new_episode_list:
                            # Update the episodes
                            anime_item.episodes = new_episode_list
                            st.success("Episodes updated successfully!")
                            st.rerun()
                        else:
                            st.error("Invalid episode selection")
                    except ValueError:
                        st.error("Invalid episode selection format")

                # Option to remove anime from list
                if st.button("Remove from List", key=f"remove_{selected_anime}"):
                    st.session_state['batch_manager']['download_list'] = [
                        item for item in st.session_state['batch_manager'].download_list
                        if item.name != selected_anime
                    ]
                    st.success(f"Removed {selected_anime} from list")
                    st.rerun()
        else:
            st.info("No anime in the list")

    with tab3:
        st.header("Manage Batch List")

        # Save/Load/Export section
        col1, col2, col3 = st.columns(3)

        with col1:
            save_name = st.text_input("Save list as:", placeholder="batch_list.json")
            if st.button("Save List"):
                try:
                    saved_path = st.session_state['batch_manager'].save_list(save_name)
                    if saved_path is not None:
                        st.success(f"List saved as {saved_path.name}")
                except Exception as e:
                    st.error(f"Error saving list: {str(e)}")

        with col2:
            saved_lists = st.session_state['batch_manager'].get_all_saved_lists()
            if saved_lists:
                selected_list = st.selectbox("Load saved list:", saved_lists)
                load_method = st.radio("Load method:", ["Replace", "Merge"])
                col1, col2 = st.columns(2)
                if col1.button("Load List"):
                    try:
                        if load_method == "Replace":
                            st.session_state['batch_manager'].load_list(selected_list)
                            st.success("List loaded successfully!")
                        else:
                            added = st.session_state['batch_manager'].merge_list(selected_list)
                            st.success(f"Merged successfully! Added {added} new items.")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error loading list: {str(e)}")
                if col2.button("Delete list"):
                    st.session_state['batch_manager'].delete_list(selected_list)
                    time.sleep(2)
                    st.error("List Deleted")
            else:
                st.info("No saved lists found")

        with col3:
            export_format = st.selectbox("Export format:", ["json", "txt"])
            export_name = st.text_input("Export filename:", value="exported_list")
            if st.button("Export List"):
                try:
                    export_path = st.session_state['batch_manager'].export_list(export_name, export_format)
                    st.success(f"List exported as {export_path.name}")
                except Exception as e:
                    st.error(f"Error exporting list: {str(e)}")

    with tab4:
        st.header("Start Batch Download")
        if not st.session_state['batch_manager'].download_list:
            st.warning("Batch list is empty. Please add some anime first.")
        else:
            total_episodes = sum(len(item.episodes) for item in st.session_state['batch_manager'].download_list)
            st.write(f"Total anime: {len(st.session_state['batch_manager'].download_list)}")
            st.write(f"Total episodes: {total_episodes}")

            if st.button("Start Batch Download"):
                if 'download_started' not in st.session_state:
                    st.session_state['download_started'] = True

                    if 'download_manager' not in st.session_state:
                        st.session_state['download_manager'] = DownloadManager(max_concurrent=max_threads)

                    st.write("### Download Progress")
                    # Create a single event loop for all downloads
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        for item in st.session_state['batch_manager'].download_list:
                            st.write(f"#### {item.name}")
                            item.name = re.sub(r'[<>:"/\\|?*]', '_', item.name)

                            download_path = os.path.join(download_folder, item.name)

                            episode_list = [
                                {
                                    "episode": str(ep),
                                    "url": f"{base_url}{item.url.replace('/category', '')}-episode-{ep}"
                                }
                                for ep in item.episodes
                            ]

                            # Run download for this anime
                            loop.run_until_complete(
                                download_episodes(
                                    episode_list,
                                    item.name,
                                    download_path
                                )
                            )
                            # Reset download manager for next anime
                            loop.run_until_complete(st.session_state['download_manager'].stop())
                            st.session_state['download_manager'] = DownloadManager(max_concurrent=max_threads)
                            loop.run_until_complete(st.session_state['download_manager'].start())

                    except Exception as e:
                        st.error(f"Error in batch download: {str(e)}")
                    finally:
                        loop.close()
                        st.session_state['download_started'] = False


def clean_filename(filename):
    cleaned_filename = re.sub(r'[\\/*?:"<>|]', '§', filename)
    return cleaned_filename


def get_preview(link):
    try:
        response = requests.get(f"{base_url}{link}")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        anime_info_section = soup.find(class_="anime_info_body_bg")
        anime_data = []

        # for section in anime_info_sections:
        # Extract individual fields
        title = anime_info_section.find("h1").get_text(strip=True) if anime_info_section.find("h1") else None
        synopsis = anime_info_section.find("div", class_="description").get_text(strip=True) if anime_info_section.find(
            "div", class_="description") else None
        genre_div = anime_info_section.find_all("p", class_='type')[2] if len(
            anime_info_section.find_all("p", class_="type")) > 2 else None
        genres = [genre.get_text(strip=True).replace(', ', '') for genre in
                  genre_div.find_all("a")] if genre_div else []
        release_date_tag = anime_info_section.find_all("p", class_="type")[3] if len(
            anime_info_section.find_all("p", class_="type")) > 3 else None
        release_date = release_date_tag.get_text(strip=True).replace("Released: ", "") if release_date_tag else None
        release_date = release_date.replace("Released:", "")
        image_link = anime_info_section.find("img")["src"] if anime_info_section.find("img") else None

        # Append the extracted data as a dictionary
        anime_data.append({
            "title": title,
            "synopsis": synopsis,
            "genres": genres,
            "release_date": release_date,
            "image_link": image_link
        })

        return anime_data

    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching anime data: {str(e)}")
        return None


def display_anime_preview_markdown(selected_anime_link):
    st.markdown("""
        <style>
        .anime-preview {
            background-color: #f0f4f8;
            border-radius: 8px;
            border: 1px solid #e1e4e8;
            padding: 15px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .anime-title {
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 10px;
            color: #1f77b4;  /* Streamlit blue */
        }
        .anime-details {
            font-size: 0.9rem;
            color: #718096;
            margin-bottom: 10px;
        }
        .genre-pill {
            background-color: #e6f3ff;
            color: #1c7ed6;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            margin: 2px;
            display: inline-block;
            border: 1px solid #a5d8ff;
        }
        .synopsis {
            font-size: 0.85rem;
            color: #2d3748;
            text-align: left;
            max-height: 150px;
            overflow-y: auto;
            background-color: #ffffff;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.spinner("Loading details..."):
        anime_data = get_preview(selected_anime_link)

    anime = anime_data[0]

    st.markdown(f'<div class="anime-preview">', unsafe_allow_html=True)

    if anime["image_link"]:
        if anime["image_link"]:
            st.image(anime["image_link"], caption=None, use_container_width=True)

    st.markdown(f'<div class="anime-title">{anime["title"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="anime-details">Released: {anime["release_date"]}</div>', unsafe_allow_html=True)

    if anime["genres"]:
        genre_pills = ' '.join([
            f'<span class="genre-pill">{genre}</span>'
            for genre in anime["genres"][:4]
        ])
        st.markdown(f'<div class="anime-details">{genre_pills}</div>', unsafe_allow_html=True)

    if anime["synopsis"]:
        truncated_synopsis = anime["synopsis"][:200] + "..." if len(anime["synopsis"]) > 200 else anime["synopsis"]
        st.markdown(f'<div class="synopsis">{truncated_synopsis}</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    with st.expander("Full Anime Details"):
        st.json(anime)


def display_anime_preview_vanilla(selected_anime_link):
    with st.spinner("Loading anime details..."):
        anime_data = get_preview(selected_anime_link)

    if anime_data and len(anime_data) > 0:
        anime = anime_data[0]

        # Image
        st.image(anime["image_link"], caption=anime["title"], use_container_width=True)

        # Title and Release Date
        st.subheader(anime["title"])
        st.caption(f"Released: {anime['release_date']}")

        # Genres
        st.write("### Genres")
        st.write(" • ".join(anime["genres"]))

        # Synopsis
        st.write("### Synopsis")
        st.write(anime["synopsis"])

        # Expandable details
        with st.expander("Full Details"):
            st.json(anime)


async def download_link_async(session, link):
    """Async version of download_link function"""
    async with session.get(link) as response:
        soup = BeautifulSoup(await response.text(), "html.parser")
        base_download_url = BeautifulSoup(str(soup.find("li", {"class": "dowloads"})), "html.parser").a.get("href")
        id = base_download_url[base_download_url.find("id=") + 3:base_download_url.find("&typesub")]
        base_download_url = base_download_url[:base_download_url.find("id=")]

        async with session.post(f"{base_download_url}&id={id}") as response:
            title = BeautifulSoup(await response.text(), "html.parser")
            title = clean_filename(title.find("span", {"id": "title"}).text)

        async with session.post(f"{base_download_url}&id={id}&captcha_v3={captcha_v3}") as response:
            soup = BeautifulSoup(await response.text(), "html.parser")
            backup_link = []

            for i in soup.find_all("div", {"class": "dowload"}):
                if str(BeautifulSoup(str(i), "html.parser").a).__contains__('download=""'):
                    link = (BeautifulSoup(str(i), "html.parser").a.get("href"))
                    quality = BeautifulSoup(str(i), "html.parser").a.string.replace(" ", "").replace("Download", "")
                    try:
                        quality = int(quality[2:quality.find("P")])
                    except ValueError:
                        print("Failed to parse quality information. Using default quality.")
                        quality = 0
                    if quality == download_quality:
                        print(f"Downloading in {quality}p")
                        return [link, title]
                    backup_link = [link, quality]

            # print(f"Downloading in {backup_link[1]}p")
            return [backup_link[0], title]


async def download_episodes(episodes: List[dict], anime_name: str, save_path):
    """Downloads multiple episodes using the download manager"""
    # Disable sidebar during downloads
    st.sidebar.empty()
    st.sidebar.info("⏳ Download in progress. Please wait...")
    disable_sidebar = st.markdown("""
       <style>[data-testid="stSidebar"] {pointer-events: none; opacity: 0.4;}</style>
    """, unsafe_allow_html=True)

    if 'download_manager' not in st.session_state:
        st.session_state['download_manager'] = DownloadManager(max_concurrent=max_threads)
    download_manager = st.session_state['download_manager']
    try:
        if not hasattr(download_manager, 'session') or download_manager.session is None:
            await download_manager.start()

        download_tasks = []
        for episode in episodes:
            try:
                # Get the legitimate download link using the async version
                download_info = await download_link_async(download_manager.session, episode['url'])
                download_url = download_info[0]
                episode_title = download_info[1]

                # Create filename using the extracted title
                filename = f"{episode_title}_episode_{episode['episode']}.mp4"

                # Queue the download task - now awaiting the add_download
                download_task = await download_manager.add_download(
                    url=download_url,
                    filename=filename,
                    folder=save_path,
                    episode=int(episode['episode'])
                )
                download_tasks.append(download_task)
            except Exception as e:
                st.error(f"Error processing episode {episode['episode']}: {str(e)}")
                continue

        # Since tasks are already running,  wait for them to complete
        for task in download_tasks:
            while task.state not in [DownloadState.COMPLETED, DownloadState.ERROR, DownloadState.CANCELLED]:
                await asyncio.sleep(0.5)

        disable_sidebar.empty()
        st.rerun()

    except Exception as e:
        st.error(f"Download manager error: {str(e)}")
        raise e
    finally:
        try:
            await download_manager.stop()
        except Exception as e:
            st.error(f"Error stopping download manager: {str(e)}")


def get_names(response):
    titles = response.find("ul", {"class": "items"}).find_all("li")
    names = []
    for i in titles:
        name = i.p.a.get("title")
        url = i.p.a.get("href")
        names.append([name, url])
    return names


def parse_episode_selection(selections: str, max_episodes: int) -> List[int]:
    """
    Parse user's episode selection string.

    Args:
        selections (str): User's episode selection string.
        max_episodes (int): Maximum number of available episodes.

    Returns:
        List[int]: List of selected episode numbers.
    """
    episodes = set()
    for part in selections.split():
        if '-' in part:
            start, end = map(int, part.split('-'))
            episodes.update(range(start, end + 1))
        else:
            episodes.add(int(part))

    if not all(1 <= ep <= max_episodes for ep in episodes):
        return []

    return sorted(episodes)


def single_download_page():
    st.title("Single Anime Download")

    col1, col2 = st.columns(2)
    anime_name = col1.text_input("Enter Anime name: ", placeholder="Search").title()
    response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={anime_name}").text, "html.parser")

    try:
        pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
        animes = []
        for page in pages:
            page_url = f"{base_url}/search.html{page.a.get('href')}"
            response = requests.get(page_url)
            soup = BeautifulSoup(response.text, "html.parser")
            animes.extend(get_names(soup))

    except AttributeError:
        animes = get_names(response)

    if 'page' not in st.session_state:
        st.session_state['page'] = 'search'

    col1, col2 = st.columns([0.6, 0.4])

    if st.session_state['page'] == 'search' and animes and anime_name:
        with col1:
            st.write("### Anime Search Results")

            options = [name for name, _ in animes]
            selected_anime = st.radio("Select an anime:", options, key="anime_radio")

        with col2:
            selected_index = options.index(selected_anime)
            selected_url = animes[selected_index][1]
            if preview_status == "Plain Preview":
                display_anime_preview_vanilla(selected_url)
            elif preview_status == "Styled Preview":
                display_anime_preview_markdown(selected_url)
            else:
                pass

        if selected_anime:
            selected_index = options.index(selected_anime)

        if st.button("Continue to Episode Selection"):
            st.session_state['page'] = 'episodes'  # Change page state
            st.session_state['selected_anime'] = animes[selected_index]  # Store selected anime
            st.rerun()  # Reload the page

    elif st.session_state['page'] == 'episodes':
        if st.button("Back to Search"):
            st.session_state['page'] = 'search'
            st.rerun()

        st.write(f"### {st.session_state.selected_anime[0]} episodes")
        # print(f"{base_url}{st.session_state.selected_anime[1]}")
        # print(get_preview(st.session_state.selected_anime[1]))
        response = BeautifulSoup(requests.get(f"{base_url}{st.session_state.selected_anime[1]}").text, "html.parser")
        base_url_cdn_api = re.search(r"base_url_cdn_api\s*=\s*'([^']*)'",
                                     str(response.find("script", {"src": ""}))).group(1)
        movie_id = response.find("input", {"id": "movie_id"}).get("value")
        last_ep = response.find("ul", {"id": "episode_page"}).find_all("a")[-1].get("ep_end")

        episodes_response = BeautifulSoup(
            requests.get(f"{base_url_cdn_api}ajax/load-list-episode?ep_start=0&ep_end={last_ep}&id={movie_id}").text,
            "html.parser").find_all("a")

        episodes = [
            {
                "episode": re.search(r"</span>(.*?)</div", str(ep.find("div"))).group(1),
                "url": f'{base_url}{ep.get("href").replace(" ", "")}'
            }
            for ep in reversed(episodes_response)
        ]

        st.write(f"Found {len(episodes)} episodes")

        if len(episodes) > 1:
            # Create download options
            download_method = st.radio(
                "Select download method:",
                ["Range", "Specific episodes"],
                key="download_method"
            )

            if download_method == "Range":
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    start = st.number_input("Start episode", min_value=1, max_value=len(episodes), value=1)
                with col2:
                    end = st.number_input("End episode", min_value=start + 1, max_value=len(episodes),
                                          value=min(start + 1, len(episodes)))

                if st.button("Download Range"):
                    if 'download_started' not in st.session_state or st.session_state['download_started'] is False:
                        st.session_state['download_started'] = True
                        selected_episodes = episodes[start - 1:end]
                        anime_name = re.sub(r'[<>:"/\\|?*]', '_', anime_name)
                        save_path = os.path.join(download_folder, anime_name)
                        st.session_state['episodes_to_download'] = selected_episodes

                        try:
                            st.write("### Downloads")

                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                            loop.run_until_complete(
                                download_episodes(
                                    selected_episodes,
                                    st.session_state.selected_anime[0],
                                    save_path
                                )
                            )
                            loop.close()
                            st.session_state['download_started'] = False
                        except Exception as e:
                            st.session_state['download_started'] = False
                            st.error(f"Error starting download: {str(e)}")
                            raise e
                        finally:
                            st.session_state['download_started'] = False

            # Select individual episodes
            else:
                col1, col2 = st.columns(2)

                episode_input = col1.text_input(
                    "Enter episode numbers (e.g., 1 3 5-7):",
                    key="episode_selection"
                )

                if st.button("Download Selected"):
                    try:
                        selected_numbers = parse_episode_selection(episode_input, len(episodes))
                        selected_episodes = [episodes[ep - 1] for ep in selected_numbers]
                        st.session_state.episodes_to_download = selected_episodes
                        anime_name = re.sub(r'[<>:"/\\|?*]', '_', anime_name)
                        save_path = os.path.join(download_folder, anime_name)

                        st.write("### Downloads")

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                        # Run the download in the event loop
                        loop.run_until_complete(
                            download_episodes(
                                selected_episodes,
                                st.session_state.selected_anime[0],
                                save_path
                            )
                        )
                        loop.close()
                        st.session_state['download_started'] = False

                    except ValueError:
                        st.error("Invalid episode selection. Please try again.")
                    except Exception as e:
                        st.session_state.download_started = False
                        st.error(f"Error starting download: {str(e)}")
                        raise e

        else:
            if st.button("Download"):
                if 'download_started' not in st.session_state or st.session_state['download_started'] is False:
                    st.session_state['download_started'] = True
                    selected_episode = [episodes[0]]
                    anime_name = re.sub(r'[<>:"/\\|?*]', '_', anime_name)
                    save_path = os.path.join(download_folder, anime_name)
                    st.session_state['episodes_to_download'] = selected_episode

                    try:
                        st.write("### Downloading...")

                        loop = asyncio.new_event_loop()

                        loop.run_until_complete(
                            download_episodes(
                                selected_episode,
                                st.session_state.selected_anime[0],
                                save_path
                            )
                        )

                    except Exception as e:
                        st.session_state['download_started'] = False
                        st.error(f"Error starting download: {str(e)}")
                        raise e


def save_setup(settings):
    """Save settings to setup.json"""
    with open("../WebUI/setup.json", "w") as f:
        json.dump(settings, f, indent=4)


def settings_page():
    st.title("Settings")

    # Create a copy of settings to track changes
    temp_settings = setup.copy()
    changes_made = []  # List to track what changes were made

    # Download Location Section
    st.header("Download Location")
    default_path = setup["downloads"]
    save_path = st.text_input("Download Location:", value=default_path, help="Copy and Paste file path")

    if st.button("Browse..."):
        st.info("Please manually enter the folder path where you want to save the downloads.")

    if not os.path.exists(os.path.dirname(save_path)):
        st.error("Invalid path. Please enter a valid directory path.")
    else:
        if save_path != setup["downloads"]:
            changes_made.append(f"Download location changed from '{setup['downloads']}' to '{save_path}'")
        temp_settings["downloads"] = save_path

    st.header("Preview Status")

    previews = ['No Preview', "Plain Preview", "Styled Preview"]

    selected_preview = st.radio(
        "Select Preview Status:",
        previews,
        index=previews.index(setup.get("preview_status", "No Preview"))
        )

    if selected_preview != setup.get('preview_status'):
        changes_made.append(
            f"Preview status changed from {setup.get('preview_status')} to {selected_preview}"
        )
    temp_settings['preview_status'] = selected_preview

    # Resolution Settings
    st.header("Resolution Settings")

    resolutions = ['360', '480', '720', '1080']
    selected_resolution = st.radio(
        "Select Default Download Resolution:",
        resolutions,
        index=resolutions.index(setup.get("download_quality", '360'))
    )

    if selected_resolution != setup.get("download_quality"):
        changes_made.append(
            f"Default resolution changed from '{setup.get('default_resolution')}' to '{selected_resolution}'")
    temp_settings["download_quality"] = selected_resolution

    # Concurrent Downloads Settings
    st.header("Concurrency Settings")

    Col1, Col2 = st.columns([0.7, 0.3])

    concurrent_downloads = Col1.empty()

    # Function to create the number input
    def create_number_input(value):
        return concurrent_downloads.number_input(
            "Maximum Concurrent Downloads:",
            min_value=1,
            max_value=10,
            value=value,
            help="Set the maximum number of videos that can be downloaded simultaneously"
        )

    current_value = create_number_input(setup.get("max_threads", 3))

    status_container = st.empty()
    details_container = st.empty()

    col1, col2 = st.columns(2)

    with Col2:
        if st.button("Optimize\nThreads", help="Finds the Optimum number of Concurrent Downloads"):
            async def estimate_optimal_workers(
                    test_url: str = "https://www.google.com",
                    max_workers: int = 10,
                    min_workers: int = 1,
            ):
                # Show testing status
                status_container.info("🔄 Optimizing concurrent downloads... Please wait.")

                # Get CPU info
                cpu_count = os.cpu_count() or 4
                details_container.write(f"CPU Cores detected: {cpu_count}")

                # Get memory info
                memory = psutil.virtual_memory()
                available_memory_gb = memory.available / (1024 * 1024 * 1024)
                details_container.write(f"Available memory: {available_memory_gb:.2f} GB")

                base_workers = cpu_count * 2
                memory_based_workers = int(available_memory_gb * 5)

                details_container.write(f"Base worker estimate (CPU-based): {base_workers}")
                details_container.write(f"Memory-based worker estimate: {memory_based_workers}")

                try:
                    details_container.write("Testing network conditions...")
                    async with aiohttp.ClientSession() as session:
                        start_time = asyncio.get_event_loop().time()
                        async with session.get(test_url) as response:
                            await response.read()
                        latency = asyncio.get_event_loop().time() - start_time

                        details_container.write(f"Network latency: {latency:.3f} seconds")
                        latency_factor = 1 / (1 + math.exp(latency - 0.5))
                        network_based_workers = int(max_workers * latency_factor)
                        details_container.write(f"Network-based worker estimate: {network_based_workers}")

                except Exception as e:
                    details_container.write("⚠️ Network test failed, using CPU-based estimate")
                    network_based_workers = base_workers

                optimal_workers = min(
                    base_workers,
                    memory_based_workers,
                    network_based_workers,
                    max_workers
                )

                optimal_workers = max(optimal_workers, min_workers)
                return optimal_workers

            # Run the optimization
            try:
                # Create and run event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                optimal_value = loop.run_until_complete(estimate_optimal_workers())
                loop.close()

                # Update the number input with the optimal value
                if optimal_value != current_value:
                    changes_made.append(
                        f"Maximum concurrent downloads optimized from {current_value} to {optimal_value}")
                    temp_settings["max_threads"] = int(optimal_value)

                    # Update the number input
                    current_value = create_number_input(optimal_value)

                status_container.success(f"✅ Optimization complete! Recommended concurrent downloads: {optimal_value}")

            except Exception as e:
                status_container.error(f"❌ Error during optimization: {str(e)}")
                details_container.empty()

    # Handle manual changes to the number input
    if current_value != setup.get("max_threads"):
        changes_made.append(
            f"Maximum concurrent downloads changed from {setup.get('max_threads', 3)} to {current_value}")
        temp_settings["max_threads"] = int(current_value)

    with col1:
        if st.button("Save Changes"):
            if not changes_made:
                st.info("No changes to save.")
            else:
                # Validate all settings before saving
                if os.path.exists(os.path.dirname(temp_settings["downloads"])):
                    save_setup(temp_settings)

                    st.success("Settings saved successfully!")
                    st.write("Changes made:")
                    for change in changes_made:
                        st.write(f"• {change}")

                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Cannot save: Invalid download path")

    with col2:
        if st.button("Reset to Default Settings"):
            default_settings = {
                "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
                "download_quality": "360p",
                "max_threads": 3
            }

            # Track what will be reset
            reset_changes = []
            if default_settings["downloads"] != setup["downloads"]:
                reset_changes.append(f"Download location reset to '{default_settings['downloads']}'")
            if default_settings["default_resolution"] != setup.get("default_resolution"):
                reset_changes.append(f"Default resolution reset to '{default_settings['default_resolution']}'")
            if default_settings["max_concurrent_downloads"] != setup.get("max_concurrent_downloads"):
                reset_changes.append(
                    f"Maximum concurrent downloads reset to {default_settings['max_concurrent_downloads']}")

            save_setup(default_settings)

            st.success("Settings reset to default!")
            if reset_changes:
                st.write("Changes made:")
                for change in reset_changes:
                    st.write(f"  • {change}")

            time.sleep(5)
            st.rerun()


def main():
    st.sidebar.title("Anime Downloader")

    # if 'sidebar_content' not in st.session_state:
    #     st.session_state['sidebar_con']

    page = st.sidebar.radio(
        "Navigation",
        ["Single", "Batch", "Settings"],
    )

    # if st.sidebar.checkbox("Show Session State Debug", True):
    #     st.sidebar.write(st.session_state)

    if page == "Single":
        single_download_page()
    elif page == "Batch":
        batch_download_page()
    elif page == "Settings":
        settings_page()
    else:
        downloads_page()


main()
