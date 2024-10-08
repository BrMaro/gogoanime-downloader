import requests
from colorama import Fore, Style, init
from typing import List, Dict
import json
import os
from bs4 import BeautifulSoup
import re
import threading
import queue

f = open("setup.json", "r")
setup = json.load(f)
f.close()
base_url = setup["gogoanime_main"]
download_folder = setup["downloads"]
captcha_v3 = setup["captcha_v3"]
download_quality = int(setup["download_quality"])
max_threads = setup["max_threads"]
init(autoreset=True)  # Initialize colorama


def download(links, folder):
    if not os.path.exists(folder):
        os.makedirs(folder)
    task_queue = queue.Queue()
    threads = []
    for i in range(max_threads):
        t = threading.Thread(target=threaded_download, args=(task_queue, folder))
        t.start()
        threads.append(t)
    for item in links:
        task_queue.put(item)
    task_queue.join()
    for i in range(max_threads):
        task_queue.put(None)
    for t in threads:
        t.join()


def threaded_download(task_queue, folder):
    while True:
        item = task_queue.get()
        if item is None:
            break
        episode = item["episode"]
        download = download_link(item["url"])
        url = download[0]
        title = download[1]
        file_path = f"{folder}/{title}.mp4"
        if os.path.exists(file_path):
            print("File already exists, going to override current data.")
            os.remove(file_path)
        else:
            open(file_path, "x").close()
            print(f"Created new file: {title}.mp4")
        r = requests.get(url, stream=True)
        print(f"Started downloading {title}, episode {episode} to {file_path}.")
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=512 * 512):
                if chunk:
                    f.write(chunk)
        if os.path.getsize(file_path) == 0:
            print(f"Something went wrong while downloading {title}, retrying...")
            task_queue.put(item)
        else:
            print(f"Finished downloading {title}, episode {episode} to {file_path}.")
        task_queue.task_done()


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


def clean_filename(filename):
    cleaned_filename = re.sub(r'[\\/*?:"<>|]', '§', filename)
    return cleaned_filename


def estimate_chunks(size, quality):
    if quality == 360:
        return (size * 0.162).__round__()
    elif quality == 480:
        return (size * 0.244).__round__()
    elif quality == 720:
        return (size * 0.526).__round__()
    elif quality == 1080:
        return size


def get_names(response):
    titles = response.find("ul", {"class": "items"}).find_all("li")
    names = []
    for i in titles:
        name = i.p.a.get("title")
        url = i.p.a.get("href")
        names.append([name, url])
    return names


def search() -> List[Dict[str, str]]:
    """
    Search for anime and return download links for selected episodes.

    Returns:
        List[Dict[str, str]]: List of dictionaries containing episode information and download links.
    """
    while True:
        name = input(f"{Fore.CYAN}Anime name: {Style.RESET_ALL}")
        response = BeautifulSoup(requests.get(f"{base_url}/search.html?keyword={name}").text, "html.parser")

        try:
            pages = response.find("ul", {"class": "pagination-list"}).find_all("li")
            animes = [anime for page in pages for anime in get_names(
                BeautifulSoup(requests.get(f"{base_url}/search.html{page.a.get('href')}").text, "html.parser"))]
        except AttributeError:
            animes = get_names(response)

        if not animes:
            print(f"{Fore.RED}No results found. Try again.{Style.RESET_ALL}")
            continue

        print(f"{Fore.GREEN}Search results:{Style.RESET_ALL}")
        for i, (name, _) in enumerate(animes, 1):
            print(f"{Fore.YELLOW}{i}: {Fore.BLUE}{name}{Style.RESET_ALL}")

        while True:
            try:
                selected_anime = int(input(f"{Fore.CYAN}Select anime number: {Style.RESET_ALL}")) - 1
                if 0 <= selected_anime < len(animes):
                    break
                raise ValueError
            except ValueError:
                print(f"{Fore.RED}Invalid selection. Try again.{Style.RESET_ALL}")

        return create_links(animes[selected_anime])


def create_links(anime: tuple) -> List[Dict[str, str]]:
    """
    Create download links for the selected anime.

    Args:
        anime (tuple): Selected anime tuple (name, URL).

    Returns:
        List[Dict[str, str]]: List of dictionaries containing episode information and download links.
    """
    response = BeautifulSoup(requests.get(f"{base_url}{anime[1]}").text, "html.parser")

    base_url_cdn_api = re.search(r"base_url_cdn_api\s*=\s*'([^']*)'", str(response.find("script", {"src": ""}))).group(
        1)
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

    print(f"{Fore.GREEN}Found {Fore.YELLOW}{len(episodes)}{Fore.GREEN} episodes.{Style.RESET_ALL}")

    print(f"{Fore.CYAN}Download options:{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}1: {Fore.BLUE}Range{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}2: {Fore.BLUE}Specific episodes{Style.RESET_ALL}")

    while True:
        choice = input(f"{Fore.CYAN}Your choice (1/2): {Style.RESET_ALL}")

        if choice == "1":
            while True:
                try:
                    start = int(input(f"{Fore.CYAN}Start episode (1-{len(episodes)}): {Style.RESET_ALL}")) - 1
                    end = int(input(f"{Fore.CYAN}End episode ({start + 2}-{len(episodes)}): {Style.RESET_ALL}"))
                    if 0 <= start < end <= len(episodes):
                        print(
                            f"{Fore.GREEN}Preparing episodes {Fore.YELLOW}{start + 1}{Fore.GREEN} to {Fore.YELLOW}{end}{Fore.GREEN} for download...{Style.RESET_ALL}")
                        return episodes[start:end]
                    raise ValueError
                except ValueError:
                    print(f"{Fore.RED}Invalid range. Try again.{Style.RESET_ALL}")

        elif choice == "2":
            while True:
                try:
                    selections = input(f"{Fore.CYAN}Enter episode numbers (e.g., 1 3 5-7): {Style.RESET_ALL}")
                    selected_episodes = parse_episode_selection(selections, len(episodes))
                    if selected_episodes:
                        ep_list = ', '.join(map(str, selected_episodes[:-1])) + (f" and {selected_episodes[-1]}" if len(
                            selected_episodes) > 1 else f"{selected_episodes[0]}")
                        print(
                            f"{Fore.GREEN}Preparing episodes {Fore.YELLOW}{ep_list}{Fore.GREEN} for download...{Style.RESET_ALL}")
                        return [episodes[ep - 1] for ep in selected_episodes]
                    raise ValueError
                except ValueError:
                    print(f"{Fore.RED}Invalid selection. Try again.{Style.RESET_ALL}")

        else:
            print(f"{Fore.RED}Invalid choice. Try again.{Style.RESET_ALL}")


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


if __name__ == "__main__":
    links = search()
    download(links, f"{download_folder}/{input('Anime folder: ')}")
