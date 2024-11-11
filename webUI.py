import streamlit as st
import json
from bs4 import BeautifulSoup
import requests
import asyncio
import os
import aiohttp
import aiofiles
from dataclasses import dataclass,asdict
from typing import List, Dict, Optional, Callable
from enum import Enum
from datetime import datetime
import re
from pathlib import Path


f = open("setup.json", "r")
setup = json.load(f)
f.close()
base_url = setup["gogoanime_main"]
download_folder = setup["downloads"]
captcha_v3 = setup["captcha_v3"]
download_quality = int(setup["download_quality"])
max_threads = setup["max_threads"]


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
        self.state = DownloadState.QUEUED
        self.progress = DownloadProgress(0, 0, 0.0, 0.0)
        self.start_time = None
        self.pause_event = asyncio.Event()
        self.cancel_event = asyncio.Event()
        self.pause_event.set()
        self.progress_bar = None
        self.status_text = None

    @property
    def file_path(self) -> str:
        return os.path.join(self.folder, f"{self.filename}.mp4")

    def setup_progress_ui(self):
        # Create a placeholder for this download's progress
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


class DownloadManager:
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.download_queue = asyncio.Queue()
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = True
        self.worker_tasks = []

    async def start(self):
        print(1)
        self.session = aiohttp.ClientSession()
        print(2)
        workers = [self._worker() for _ in range(self.max_concurrent)]
        print(3)
        # Create worker tasks but don't wait for them
        self.worker_tasks = [
            asyncio.create_task(self._worker())
            for _ in range(self.max_concurrent)
        ]
        print(4)

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

    def add_download(self, url: str, filename: str, folder: str, episode: int) -> DownloadTask:
        """Add a new download task to the queue"""
        task = DownloadTask(url, filename, folder, episode)
        task.setup_progress_ui()
        # Create task for queuing download
        asyncio.create_task(self.download_queue.put(task))
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

        async with aiofiles.open(task.file_path, 'wb') as f:
            pass

        task.start_time = datetime.now()
        task.state = DownloadState.DOWNLOADING

        try:
            async with self.session.get(task.url) as response:
                total_size = int(response.headers.get('content-length', 0))
                task.progress.total_bytes = total_size
                downloaded = 0

                async with aiofiles.open(task.file_path, 'wb') as file:
                    async for chunk in response.content.iter_chunked(512 * 512):
                        if task.cancel_event.is_set():
                            task.state = DownloadState.CANCELLED
                            return

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

            if task.state != DownloadState.CANCELLED:
                task.state = DownloadState.COMPLETED
                if task.status_text:
                    task.status_text.success(f"Episode {task.episode} downloaded successfully!")

        except Exception as e:
            task.state = DownloadState.ERROR
            if task.status_text:
                task.status_text.error(f"Download error for episode {task.episode}: {str(e)}")
            raise


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
            backup_name = f"{save_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_path = self.save_directory / backup_name
            save_path.rename(backup_path)

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
            if backup_path.exists():
                backup_path.rename(save_path)  # Restore backup if save fails
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
            st.session_state.downloads = []
        if 'download_manager' not in st.session_state:
            st.session_state.download_manager = DownloadManager(max_concurrent=max_threads)

    @property
    def downloads(self):
        return st.session_state.downloads

    def add_download(self, anime_name: str, episodes: List[dict], save_path: str):
        for episode in episodes:
            self.downloads.append({
                'anime_name': anime_name,
                'episode': episode['episode'],
                'status': 'queued',
                'progress': 0,
                'speed': 0,
                'save_path': save_path,
                'url': episode['url'],
                'downloaded_bytes': 0,
                'total_bytes': 0,
                'start_time': None
            })


def downloads_page():
    st.title("Downloads")

    if 'download_page_manager' not in st.session_state:
        st.session_state.download_page_manager = DownloadPageManager()

    downloads_by_anime ={}
    for download in st.session_state.downloads:
        anime_name = download['anime_name']
        if anime_name not in downloads_by_anime:
            downloads_by_anime[anime_name]=[]
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


def save_folder_picker():
    """Create a folder picker widget"""
    default_path = setup["downloads"]
    save_path = st.text_input("Download Location:", value=default_path)
    if st.button("Browse..."):
        # Note: Streamlit can't directly open a folder picker dialog
        # This is a workaround to let users manually input the path
        st.info("Please manually enter the folder path where you want to save the downloads.")
    return save_path


def batch_download_page():
    if 'batch_manager' not in st.session_state:
        st.session_state.batch_manager = BatchManager()

    st.title("Batch Download Manager")

    # Save Location
    save_path = save_folder_picker()

    # Tabs for different functions
    tab1, tab2, tab3 = st.tabs(["Add Anime", "Manage List", "Start Download"])

    # Add Anime Tab
    with tab1:
        st.header("Add Anime to Batch")

        # Search functionality
        anime_name = st.text_input("Search Anime:", key="batch_search")
        if anime_name:
            response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={anime_name}").text, "html.parser")
            try:
                pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
                animes = [anime for page in pages for anime in get_names(
                    BeautifulSoup(requests.get(f"{base_url}/search.html{page.a.get('href')}").text, "html.parser"))]
            except AttributeError:
                animes = get_names(response)

            if animes:
                selected_anime = st.selectbox("Select Anime:", [name for name, _ in animes])
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
                                st.session_state.batch_manager.add_item(new_item)
                                st.success(f"Added {selected_anime} to batch list")
                            else:
                                st.error("Invalid episode selection")
                        except ValueError:
                            st.error("Invalid episode selection format")

    # In the Manage List Tab
    with tab2:
        st.header("Manage Batch List")

        # Save/Load/Export section
        col1, col2, col3 = st.columns(3)

        with col1:
            save_name = st.text_input("Save list as:", value="batch_list.json")
            if st.button("Save List"):
                try:
                    saved_path = st.session_state.batch_manager.save_list(save_name)
                    st.success(f"List saved as {saved_path.name}")
                except Exception as e:
                    st.error(f"Error saving list: {str(e)}")

        with col2:
            saved_lists = st.session_state.batch_manager.get_all_saved_lists()
            if saved_lists:
                selected_list = st.selectbox("Load saved list:", saved_lists)
                load_method = st.radio("Load method:", ["Replace", "Merge"])
                if st.button("Load List"):
                    try:
                        if load_method == "Replace":
                            st.session_state.batch_manager.load_list(selected_list)
                            st.success("List loaded successfully!")
                        else:
                            added = st.session_state.batch_manager.merge_list(selected_list)
                            st.success(f"Merged successfully! Added {added} new items.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error loading list: {str(e)}")
            else:
                st.info("No saved lists found")

        with col3:
            export_format = st.selectbox("Export format:", ["json", "txt"])
            export_name = st.text_input("Export filename:", value="exported_list")
            if st.button("Export List"):
                try:
                    export_path = st.session_state.batch_manager.export_list(export_name, export_format)
                    st.success(f"List exported as {export_path.name}")
                except Exception as e:
                    st.error(f"Error exporting list: {str(e)}")

    with tab3:
        st.header("Start Batch Download")
        if not st.session_state.batch_manager.download_list:
            st.warning("Batch list is empty. Please add some anime first.")
        else:
            total_episodes = sum(len(item.episodes) for item in st.session_state.batch_manager.download_list)
            st.write(f"Total anime: {len(st.session_state.batch_manager.download_list)}")
            st.write(f"Total episodes: {total_episodes}")

            if st.button("Start Batch Download"):
                if 'download_started' not in st.session_state:
                    st.session_state.download_started = True

                    # Initialize download manager if needed
                    if 'download_manager' not in st.session_state:
                        st.session_state.download_manager = DownloadManager()

                    st.write("### Download Progress")

                    for item in st.session_state.batch_manager.download_list:
                        st.write(f"#### {item.name}")
                        download_path = os.path.join(save_path, item.name)

                        # Create episode list in the format expected by download_episodes
                        episode_list = [
                            {"episode": str(ep), "url": f"{base_url}{item.url}/ep-{ep}"}
                            for ep in item.episodes
                        ]

                        try:
                            # Use asyncio.create_task instead of asyncio.run
                            asyncio.create_task(
                                download_episodes(
                                    episode_list,
                                    item.name,
                                    download_path
                                )
                            )
                        except Exception as e:
                            st.error(f"Error starting download for {item.name}: {str(e)}")

                    # Redirect to downloads page
                    st.switch_page("Downloads")


def clean_filename(filename):
    cleaned_filename = re.sub(r'[\\/*?:"<>|]', '§', filename)
    return cleaned_filename


def download_link(link):
    soup = BeautifulSoup(requests.get(link).text, "html.parser")
    base_download_url = BeautifulSoup(str(soup.find("li", {"class": "dowloads"})), "html.parser").a.get("href")  #typo in the webcode?
    id = base_download_url[base_download_url.find("id=") + 3:base_download_url.find("&typesub")]
    base_download_url = base_download_url[:base_download_url.find("id=")]
    title = BeautifulSoup(requests.post(f"{base_download_url}&id={id}").text, "html.parser")
    title = clean_filename(title.find("span", {"id": "title"}).text)
    response = requests.post(f"{base_download_url}&id={id}&captcha_v3={captcha_v3}")  #will this captcha work for long?
    soup = BeautifulSoup(response.text, "html.parser")
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
    print(f"Downloading in {backup_link[1]}p")
    return [backup_link[0],
            title]  #if the prefered download quality is not available the highest quality will automaticly be chosen


async def download_episodes(episodes: List[dict], anime_name: str, save_path: str):
    """Downloads multiple episodes using the download manager"""
    if 'download_manager' not in st.session_state:
        st.session_state.download_manager = DownloadManager()

    download_manager = st.session_state.download_manager
    try:
        # Start the download manager if it's not running
        if not hasattr(download_manager, 'session') or download_manager.session is None:
            print('before donwloader  starts')
            await download_manager.start()
            print("after downloader starts")

        download_tasks = []
        for episode in episodes:
            try:
                # Get the episode page content using the manager's session
                async with download_manager.session.get(episode['url']) as response:
                    page_content = await response.text()
                    episode_page = BeautifulSoup(page_content, 'html.parser')
                    download_url = episode_page.find('a', {'class': 'download-link'}).get('href')

                    # Create filename
                    filename = f"{anime_name}_episode_{episode['episode']}.mp4"

                    # Queue the download task
                    download_task = download_manager.add_download(
                        url=download_url,
                        filename=filename,
                        folder=save_path,
                        episode=int(episode['episode'])
                    )
                    download_tasks.append(download_task)
            except Exception as e:
                st.error(f"Error processing episode {episode['episode']}: {str(e)}")
                continue

            # Wait for all download tasks to complete
        await asyncio.gather(*download_tasks, return_exceptions=True)

    except Exception as e:
        st.error(f"Download manager error: {str(e)}")
        raise e
    finally:
        # Always try to stop the download manager
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
    # st.title("Anime Search & Download")
    # options = ["Single", "Batch"]
    # st.radio("Choose type of download: ", options)
    st.title("Single Anime Download")

    save_path = save_folder_picker()

    col1, col2 = st.columns(2)
    anime_name = col1.text_input("Enter Anime name: ", placeholder="Search")
    response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={anime_name}").text, "html.parser")

    try:
        pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
        animes = [anime for page in pages for anime in get_names(
            BeautifulSoup(requests.get(f"{base_url}/search.html{page.a.get('href')}").text, "html.parser"))]
    except AttributeError:
        animes = get_names(response)

    if 'page' not in st.session_state:
        st.session_state.page = 'search'

    if st.session_state.page == 'search' and animes and anime_name:
        st.write("#### Anime Search Results")

        # Create radio options with anime names
        options = [name for name, _ in animes]
        selected_anime = st.radio("Select an anime:", options, key="anime_radio")

        if selected_anime:
            selected_index = options.index(selected_anime)
            selected_url = animes[selected_index][1]

        if st.button("Continue to Episode Selection"):
            st.session_state.page = 'episodes'  # Change page state
            st.session_state.selected_anime = animes[selected_index]  # Store selected anime
            st.rerun()  # Reload the page

    elif st.session_state.page == 'episodes':
        st.write(f"### {st.session_state.selected_anime[0]} episodes")

        # Get episodes data
        response = BeautifulSoup(requests.get(f"{base_url}{st.session_state.selected_anime[1]}").text, "html.parser")
        base_url_cdn_api = re.search(r"base_url_cdn_api\s*=\s*'([^']*)'",str(response.find("script", {"src": ""}))).group(1)
        movie_id = response.find("input", {"id": "movie_id"}).get("value")
        last_ep = response.find("ul", {"id": "episode_page"}).find_all("a")[-1].get("ep_end")

        episodes_response = BeautifulSoup(requests.get(f"{base_url_cdn_api}ajax/load-list-episode?ep_start=0&ep_end={last_ep}&id={movie_id}").text,"html.parser").find_all("a")

        episodes = [
            {
                "episode": re.search(r"</span>(.*?)</div", str(ep.find("div"))).group(1),
                "url": f'{base_url}{ep.get("href").replace(" ", "")}'
            }
            for ep in reversed(episodes_response)
        ]

        st.write(f"Found {len(episodes)} episodes")

        # Create download options
        download_method = st.radio(
            "Select download method:",
            ["Range", "Specific episodes"],
            key="download_method"
        )

        if download_method == "Range":
            col1, col2 = st.columns(2)
            with col1:
                start = st.number_input("Start episode", min_value=1, max_value=len(episodes), value=1)
                print(start)
            with col2:
                end = st.number_input("End episode", min_value=start + 1, max_value=len(episodes), value=min(start + 1, len(episodes)))
                print(end)

            if st.button("Download Range"):
                if 'download_started' not in st.session_state:
                    st.session_state.download_started = True
                    selected_episodes = episodes[start-1:end]
                    for i in selected_episodes:
                        print(i)
                    save_path = os.path.join(download_folder, anime_name)
                    print(save_path)
                    st.session_state.episodes_to_download = selected_episodes

                    try:
                        # Use asyncio.create_task instead of asyncio.run
                        # Create new event loop and run the download
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
                        st.switch_page("Downloads")
                    except Exception as e:
                        st.session_state.download_started = False
                        st.error(f"Error starting download: {str(e)}")
                        raise e  # Re-raise for debugging


        else:
            episode_input = st.text_input(
                "Enter episode numbers (e.g., 1 3 5-7):",
                key="episode_selection"
            )

            if st.button("Download Selected"):
                try:
                    selected_numbers = parse_episode_selection(episode_input, len(episodes))
                    selected_episodes = [episodes[ep - 1] for ep in selected_numbers]
                    st.session_state.episodes_to_download = selected_episodes
                    save_path = os.path.join(download_folder, anime_name)

                    # print(st.session_state.selected_anime[0], selected_episodes)

                    # Create a new section for downloads
                    st.write("### Downloads")

                    # Run the download process
                    asyncio.create_task(
                        download_episodes(
                            selected_episodes,
                            st.session_state.selected_anime[0],
                            save_path
                        )
                    )
                    st.switch_page("Downloads")

                except ValueError:
                    st.error("Invalid episode selection. Please try again.")

        # Add a back button
        if st.button("Back to Search"):
            st.session_state.page = 'search'
            st.rerun()


def main():
    st.sidebar.title("Anime Downloader")
    page = st.sidebar.radio("Navigation", ["Search", "Batch", "Downloads"])

    print(st.session_state)

    if page == "Search":
        single_download_page()
    elif page == "Batch":
        batch_download_page()
    else:
        downloads_page()

main()
