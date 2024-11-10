import streamlit as st
import json
from bs4 import BeautifulSoup
import requests
import asyncio
import os
import aiohttp
import aiofiles
from dataclasses import dataclass
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

    async def start(self):
        self.session = aiohttp.ClientSession()
        workers = [self._worker() for _ in range(self.max_concurrent)]
        await asyncio.gather(*workers)

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()

    def add_download(self, url: str, filename: str, folder: str, episode: int) -> DownloadTask:
        task = DownloadTask(url, filename, folder, episode)
        task.setup_progress_ui()
        asyncio.create_task(self.download_queue.put(task))
        self.active_downloads[task.file_path] = task
        return task

    async def _worker(self):
        while self.running:
            task: DownloadTask = await self.download_queue.get()

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

    async def _process_download(self, task: DownloadTask):
        if not os.path.exists(task.folder):
            os.makedirs(task.folder)

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


@dataclass
class AnimeDownloadItem:
    name: str
    url: str
    episodes: List[int]
    total_episodes: int


class BatchManager:
    def __init__(self):
        self.download_list: List[AnimeDownloadItem] = []

    def add_item(self, item: AnimeDownloadItem):
        self.download_list.append(item)

    def remove_item(self, index: int):
        if 0 <= index < len(self.download_list):
            self.download_list.pop(index)

    def save_list(self, filename: str):
        data = []
        for item in self.download_list:
            data.append({
                'name': item.name,
                'url': item.url,
                'episodes': item.episodes,
                'total_episodes': item.total_episodes
            })
        with open(filename, 'w') as f:
            json.dump(data, f)

    def load_list(self, filename: str):
        with open(filename, 'r') as f:
            data = json.load(f)
            self.download_list = []
            for item in data:
                self.download_list.append(AnimeDownloadItem(
                    name=item['name'],
                    url=item['url'],
                    episodes=item['episodes'],
                    total_episodes=item['total_episodes']
                ))


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

    # Manage List Tab
    with tab2:
        st.header("Manage Batch List")

        # Save/Load list
        col1, col2 = st.columns(2)
        with col1:
            save_name = st.text_input("Save list as:", value="batch_list.json")
            if st.button("Save List"):
                try:
                    save_path = Path("batch_lists")
                    save_path.mkdir(exist_ok=True)
                    st.session_state.batch_manager.save_list(save_path / save_name)
                    st.success("List saved successfully!")
                except Exception as e:
                    st.error(f"Error saving list: {str(e)}")

        with col2:
            saved_lists = list(Path("batch_lists").glob("*.json")) if Path("batch_lists").exists() else []
            if saved_lists:
                selected_list = st.selectbox("Load saved list:", saved_lists)
                if st.button("Load List"):
                    try:
                        st.session_state.batch_manager.load_list(selected_list)
                        st.success("List loaded successfully!")
                    except Exception as e:
                        st.error(f"Error loading list: {str(e)}")

        # Display current list
        st.subheader("Current Batch List")
        if st.session_state.batch_manager.download_list:
            for idx, item in enumerate(st.session_state.batch_manager.download_list):
                with st.expander(f"{item.name} ({len(item.episodes)} episodes)"):
                    st.write(f"Episodes: {', '.join(map(str, item.episodes))}")
                    if st.button("Remove", key=f"remove_{idx}"):
                        st.session_state.batch_manager.remove_item(idx)
                        st.rerun()
        else:
            st.info("No items in batch list")

    # Start Download Tab
    with tab3:
        st.header("Start Batch Download")
        if not st.session_state.batch_manager.download_list:
            st.warning("Batch list is empty. Please add some anime first.")
        else:
            total_episodes = sum(len(item.episodes) for item in st.session_state.batch_manager.download_list)
            st.write(f"Total anime: {len(st.session_state.batch_manager.download_list)}")
            st.write(f"Total episodes: {total_episodes}")

            if st.button("Start Batch Download"):
                st.write("### Download Progress")

                # Create progress tracking for all downloads
                for item in st.session_state.batch_manager.download_list:
                    st.write(f"#### {item.name}")
                    download_path = os.path.join(save_path, item.name)
                    asyncio.run(download_episodes(
                        [{"episode": ep} for ep in item.episodes],
                        item.name,
                        download_path
                    ))


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


async def download_episodes(episodes, anime_name, save_path):
    if 'download_page_manager' not in st.session_state:
        st.session_state.download_page_manager = DownloadPageManager()

    # Add downloads to the manager
    st.session_state.download_page_manager.add_download(anime_name, episodes, save_path)

    # Switch to downloads page
    st.session_state.page = "Downloads"
    st.rerun()


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
        print(animes[0], animes[0][0])
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
        base_url_cdn_api = re.search(r"base_url_cdn_api\s*=\s*'([^']*)'",
                                     str(response.find("script", {"src": ""}))).group(1)
        movie_id = response.find("input", {"id": "movie_id"}).get("value")
        last_ep = response.find("ul", {"id": "episode_page"}).find_all("a")[-1].get("ep_end")

        episodes_response = BeautifulSoup(requests.get(f"{base_url_cdn_api}ajax/load-list-episode?ep_start=0&ep_end={last_ep}&id={movie_id}").text,
            "html.parser"
        ).find_all("a")

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
                start = st.number_input("Start episode", min_value=1, max_value=len(episodes), value=1) - 1
            with col2:
                end = st.number_input("End episode", min_value=start + 2, max_value=len(episodes),
                                      value=min(start + 2, len(episodes)))

            if st.button("Download Range"):
                selected_episodes = episodes[start:end]
                st.session_state.episodes_to_download = selected_episodes
                print(st.session_state.selected_anime[0], selected_episodes)

                # Create a new section for downloads
                st.write("### Downloads")

                # Run the download process
                asyncio.run(download_episodes(
                    selected_episodes,
                    st.session_state.selected_anime[0]
                ))

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
                    print(st.session_state.selected_anime[0], selected_episodes)

                    # Create a new section for downloads
                    st.write("### Downloads")

                    # Run the download process
                    asyncio.run(
                        download_episodes(
                            selected_episodes,
                            st.session_state.selected_anime[0]
                        )
                    )
                except ValueError:
                    st.error("Invalid episode selection. Please try again.")

        # Add a back button
        if st.button("Back to Search"):
            st.session_state.page = 'search'
            st.rerun()


def main():
    st.sidebar.title("Anime Downloader")
    page = st.sidebar.radio("Navigation", ["Search", "Batch", "Downloads"])

    if page == "Search":
        single_download_page()
    elif page == "Batch":
        batch_download_page()
    else:
        downloads_page()

main()
