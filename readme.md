[//]: # ()
[//]: # (# Anime Downloader)

[//]: # ()
[//]: # (Forked from https://github.com/sls2561b1/gogoanime-downloader)

[//]: # ()
[//]: # (Anime Downloader is a powerful and user-friendly command-line tool that allows you to download anime episodes from the popular streaming site&#40;Gogoanime&#41;. With support for both single anime downloads and batch processing, it's the perfect tool for anime enthusiasts who want to build their local collection.)

[//]: # ()
[//]: # (## Features)

[//]: # ()
[//]: # (- Search and download anime episodes from popular streaming sites)

[//]: # (- Single anime download mode)

[//]: # (- Batch download manager for multiple anime series)

[//]: # (- Customizable download quality)

[//]: # (- Multi-threaded downloads for improved speed)

[//]: # (- Save and load batch download lists)

[//]: # (- User-friendly command-line interface with color-coded output)

[//]: # ()
[//]: # (## Requirements)

[//]: # (To use Anime Downloader, you'll need:)

[//]: # ()
[//]: # (- Python 3.7 or higher)

[//]: # (- pip &#40;Python package installer&#41;)

[//]: # ()
[//]: # (## Installation)

[//]: # ()
[//]: # (Clone the repository or download the source code:)

[//]: # (``` )

[//]: # (git clone https://github.com/yourusername/anime-downloader.git)

[//]: # (cd anime-downloader)

[//]: # (```)

[//]: # (Install the required libraries:)

[//]: # (```)

[//]: # (pip install -r requirements.txt)

[//]: # (```)

[//]: # ()
[//]: # (## Setup)

[//]: # ()
[//]: # (Create a setup.json file in the same directory as the script with the following structure ONLY if it is not already there when you clone the script:)

[//]: # (```)

[//]: # ({)

[//]: # (  "gogoanime_main": "https://gogoanime.gg",)

[//]: # (  "downloads": "/path/to/your/download/folder",)

[//]: # (  "captcha_v3": "your_captcha_v3_key",)

[//]: # (  "download_quality": 1080,)

[//]: # (  "max_threads": 5)

[//]: # (})

[//]: # (```)

[//]: # ()
[//]: # ()
[//]: # (Replace the values in the setup.json file with your preferred settings:)

[//]: # ()
[//]: # (- gogoanime_main: The base URL for the anime streaming site)

[//]: # (- downloads: The default folder where anime will be downloaded)

[//]: # (- captcha_v3: Your captcha v3 key &#40;if required by the streaming site&#41;)

[//]: # (- download_quality: Preferred download quality &#40;e.g., 360, 480, 720, 1080&#41;)

[//]: # (- max_threads: Maximum number of concurrent download threads&#40;Limit to your network max/3.3&#41;)

[//]: # (     - eg if your network max is 50 MB/s, calculate 50/3.3 ~ 15 and use that&#40;in this case 15&#41; as max threads&#41;)

[//]: # ()
[//]: # ()
[//]: # (## Usage)

[//]: # (Simply run the script using Python:)

[//]: # (```)

[//]: # (python main.py)

[//]: # (```)

[//]: # (Follow the on-screen prompts to:)

[//]: # ()
[//]: # (1. Choose between single anime download or batch download manager)

[//]: # (2. Search for anime by name)

[//]: # (3. Select the desired anime from search results)

[//]: # (4. Choose episodes to download &#40;by range or specific episodes&#41;)

[//]: # (5. Start the download process)

[//]: # ()
[//]: # (## Batch Download Manager)

[//]: # (The Batch Download Manager allows you to:)

[//]: # ()
[//]: # (- Add multiple anime series to a download queue)

[//]: # (- View and manage your download queue)

[//]: # (- Save your batch list for future use)

[//]: # (- Load previously saved batch lists)

[//]: # (- Start batch downloads)

[//]: # ()
[//]: # (## Upcoming Features)

[//]: # ()
[//]: # (- Support for multiple anime streaming sites &#40;Redundancy&#41;)

[//]: # (- GUI interface)

[//]: # (- Scheduling downloads for off-peak hours)

[//]: # (- Integration with MyAnimeList for tracking watched episodes)

[//]: # ()
[//]: # (## Advantages)

[//]: # ()
[//]: # (- **Time-saving**: Download multiple episodes or series in one go)

[//]: # (- **Flexible**: Choose between single downloads or batch processing)

[//]: # (- **Customizable**: Set your preferred download quality and save location)

[//]: # (- **Efficient**: Multi-threaded downloads for faster processing)

[//]: # (- **Persistent**: Save and load batch lists for convenient future use)

[//]: # (- **User-friendly** : Clear, color-coded command-line interface for easy navigation)

[//]: # ()
[//]: # (## Disclaimer)

[//]: # (This tool is for personal use only. Please respect copyright laws and support the anime industry by using legal streaming services when available.)

[//]: # (## Contributing)

[//]: # (Contributions are welcome! Please feel free to submit a Pull Request.)

[//]: # (## License)

[//]: # (This project is licensed under the MIT License - see the LICENSE file for details.)

# 🎬 Anime Downloader: Multi-Interface Anime Download Toolkit
## 📦 Project Structure
```
Gogoanime-Downloader/
│
├── CommandLineUI/
│   ├── main.py
│   └── setup.json
│
├── DesktopGUI/
│   ├── gui.py
│   └── setup.json
│
├── WebUI/
│   ├── webUi.py
│   ├── setup.json
│   └── batchlists/
│
└── README.md

```
# 🚀 Project Overview
Anime Downloader is a versatile anime episode downloading application offering three distinct interfaces to cater to different user preferences:

- Command-Line Interface (CLI)
- Desktop Graphical User Interface (PyQt5)
- Web-Based User Interface (Streamlit)

# 🔍 Interface Characteristics
## 1. Command-Line Interface (CLI)

Core Technology: Traditional Python threading
### How to Run:
- Install requirements
```
pip install -r requirements.txt
```
- Navigate to the project folder subdirectory of /CommandLineUI
```
python main.py
```
### Features:

- Multi-threaded downloads
- Direct episode selection
- Comprehensive download management

Performance: Established, reliable threading mechanism

## 2. Desktop GUI (PyQt5)

Status: Currently Incomplete

### Planned Features:

- Graphical episode selection
- Download management
- Settings configuration

Technology: PyQt5 for desktop application development, async for downloading

## 3. Web UI (Streamlit)

Core Technology: Async downloading with aiohttp, Streamlit for frontend
### How to Run:
- Install requirements
```
pip install -r requirements.txt
```
- Navigate to the project folder subdirectory of /WebUI
```
streamlit run webUI.py
```
### Advanced Features:

- Asynchronous download handling
- Dynamic settings updates
- Resolution configuration
- Download path selection


### Upcoming Features:

- Download pause functionality
- Download cancellation


## 🛠 Download Mechanisms
Threading Approaches

- CLI: Traditional multi-threading
- Desktop GUI: Not yet implemented
- Web UI: Asynchronous downloading with aiohttp


Note: Each interface has a distinct backend implementation optimized for its specific use case.

## 🔧 Configuration
Each interface maintains its own setup.json with potential configurations:

Gogoanime base URL
Download directory
Preferred video resolution
Download threads/concurrency

## 📋 Planned Enhancements

 - Standardize backend across interfaces
 - Implement pause/cancel in all interfaces
 - Cross-platform compatibility
 - Enhanced error handling
 - Integration with anime tracking services

## 🚧 Current Development Focus
The Web UI (Streamlit) is currently the most advanced interface, with:

- Dynamic settings updates
- Efficient async download mechanism
- Upcoming pause/cancel features

## 🔒 Legal Disclaimer
This tool is for personal use. Always respect copyright laws and support the anime industry by using legal streaming services.
## 📜 License
MIT License
## 🤝 Contributing
Contributions are welcome! Please submit pull requests or open issues to help improve the project.