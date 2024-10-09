[//]: # (This is just a little project of mine to automaticly download multiple anime episodes from gogoanime &#40;current domain https://anitaku.to&#41;.)

[//]: # (Since the download servers have a download limit i added multithreading. One episode downloads at 3.3MBit/s, which means in order to get everything out of your own network you can use multiple threads for multiple episodes &#40;note that the download time for single episodes is not affected by the number of threads&#41;. If you have a 50MBit Network &#40;you can test this with almost every speedtest out there&#41; you can calculate the number of threads: 50/3.3 ~ 15. There is one error, that occures when the script tries to download with more treads than your network can handle. It works just fine, but your console will be flooded with errors about a failed download.)

[//]: # ()
[//]: # (1. Install the requirements: pip install -r requirements.txt)

[//]: # (2. Specify the anime you want to search for)

[//]: # (3. Select one of the found animes)

[//]: # (4. Select download type &#40;if 1 go to no. 5 else no. 6&#41;)

[//]: # (5. Select which episodes you want to download &#40;only from x to y currently&#41;)

[//]: # (6. Enter the episodes to download &#40;seperated by space&#41;)

[//]: # (7. Select a foldername that will either be created or used &#40;if you want it somewhere else than the ./downloads you can specify the base path for all downloads in the setup.json file&#41;)

[//]: # (8. Wait )

[//]: # (It apparently can also happen, that an episode is not downloaded correctly, in that case just redownload it.)

[//]: # ()
[//]: # (If the domain name has changed again, change the gogoanime_main in the setup.json file. In case a weird error apears the hardcoded captcha might be outdated, maybe this will get fixed.)

[//]: # (To change the quality of the downloads you can change it in the setup &#40;360, 480, 720 or 1080&#41;, if a download in the prefered quality is not available the highest quality will automaticly be chosen. If the quality is not 1080p the time estimates might be very inaccurate.)


# Anime Downloader

Forked from https://github.com/sls2561b1/gogoanime-downloader

Anime Downloader is a powerful and user-friendly command-line tool that allows you to download anime episodes from the popular streaming site(Gogoanime). With support for both single anime downloads and batch processing, it's the perfect tool for anime enthusiasts who want to build their local collection.

## Features

- Search and download anime episodes from popular streaming sites
- Single anime download mode
- Batch download manager for multiple anime series
- Customizable download quality
- Multi-threaded downloads for improved speed
- Save and load batch download lists
- User-friendly command-line interface with color-coded output

## Requirements
To use Anime Downloader, you'll need:

- Python 3.7 or higher
- pip (Python package installer)

## Installation

Clone the repository or download the source code:
``` 
git clone https://github.com/yourusername/anime-downloader.git
cd anime-downloader
```
Install the required libraries:
```
pip install -r requirements.txt
```

## Setup

Create a setup.json file in the same directory as the script with the following structure ONLY if it is not already there when you clone the script:
```
{
  "gogoanime_main": "https://gogoanime.gg",
  "downloads": "/path/to/your/download/folder",
  "captcha_v3": "your_captcha_v3_key",
  "download_quality": 1080,
  "max_threads": 5
}
```


Replace the values in the setup.json file with your preferred settings:

- gogoanime_main: The base URL for the anime streaming site
- downloads: The default folder where anime will be downloaded
- captcha_v3: Your captcha v3 key (if required by the streaming site)
- download_quality: Preferred download quality (e.g., 360, 480, 720, 1080)
- max_threads: Maximum number of concurrent download threads(Limit to your network max/3.3)
     - eg if your network max is 50 MB/s, calculate 50/3.3 ~ 15 and use that(in this case 15) as max threads)


## Usage
Simply run the script using Python:
```
python anime_downloader.py
```
Follow the on-screen prompts to:

1. Choose between single anime download or batch download manager
2. Search for anime by name
3. Select the desired anime from search results
4. Choose episodes to download (by range or specific episodes)
5. Start the download process

## Batch Download Manager
The Batch Download Manager allows you to:

- Add multiple anime series to a download queue
- View and manage your download queue
- Save your batch list for future use
- Load previously saved batch lists
- Start batch downloads

## Upcoming Features

- Support for multiple anime streaming sites (Redundancy)
- GUI interface
- Scheduling downloads for off-peak hours
- Integration with MyAnimeList for tracking watched episodes

## Advantages

- **Time-saving**: Download multiple episodes or series in one go
- **Flexible**: Choose between single downloads or batch processing
- **Customizable**: Set your preferred download quality and save location
- **Efficient**: Multi-threaded downloads for faster processing
- **Persistent**: Save and load batch lists for convenient future use
- **User-friendly** : Clear, color-coded command-line interface for easy navigation

## Disclaimer
This tool is for personal use only. Please respect copyright laws and support the anime industry by using legal streaming services when available.
## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
## License
This project is licensed under the MIT License - see the LICENSE file for details.