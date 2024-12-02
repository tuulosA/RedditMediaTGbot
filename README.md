# RedditMediaTGbot

An asynchronous Reddit Media Telegram bot designed to fetch, process, and directly deliver images or videos from specified subreddits to Telegram.

---

## Features

- **Reddit Media Fetching**: Fetches posts from subreddits, with support for search terms, message count, media types, and time filters.
- **Media Processing**: Handles various media types (images, gallery posts, reddit video, imgur gifv, reddit GIFs) with validation, conversion, and compression if needed.
- **Telegram Integration**: Sends processed media directly to Telegram users/groups with the command /r.
- **Support for Comments**: Optionally fetches and includes top comments with the media.
- **Flexible Commands**: Allows flexible commands for fetching and filtering media posts.

---

## Installation

### Prerequisites

- Python 3.8+
- Telegram Bot API Token
- Reddit API credentials (`client_id`, `client_secret`, `user_agent`, `username`, `password`)
- `yt-dlp` and `ffmpeg` installed on your system.
    
### Steps
    
1. Clone this repository:
   ```
   git clone https://github.com/tuulosA/RedditMediaTGbot.git
   cd RedditMediaTGbot
   ```
2. Create a virtual environment and install dependencies:
   ```python -m venv venv
   # Create a virtual environment
   python -m venv venv

   # Activate the environment
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```
3. Install all required Python packages from the requirements.txt file:
   ```
   pip install -r requirements.txt
   ```
4. Configure environment variables for Reddit and Telegram API:
   
   Create a .env file in the project root with:
   ```TELEGRAM_API_TOKEN=your_bot_api_token
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USER_AGENT=your_user_agent
   REDDIT_USERNAME=your_username
   REDDIT_PASSWORD=your_password
   ```
4. Run the bot:
```python main.py```
    
---

## Usage

### Fetching Media from Reddit

To fetch media from Reddit, use the /r command in Telegram. For example:
    
/r time_filter subreddit_name(s) search_term(s) 3 image -c

Example Breakdown:

- `time_filter`: Filtered by all, year, month, or week (optional).
- `subreddit_name`: Name of the subreddit (e.g., pics).
- `search_term`: Keywords to search for (optional).
- `3`: Number of media posts to fetch (1-5) (optional).
- `image`: Type of media (image/video) (optional).
- `-c`: Include top comments with the media (optional).

## Command Structure

The bot recognizes flexible commands through Telegram:

| Command Example     | Description                                                  |
|---------------------|--------------------------------------------------------------|
| `/r all pics cool`  | Fetch all time top posts from r/pics with search term 'cool' |
| `/r trains video`   | Fetch videos from r/trains.                                  |
| `/r funny 5 image`  | Fetch 5 images from r/funny.                                 |
| `/r cats orange -c` | Fetch with search 'orange' from /r cats with top comments.   |
| `/r month movies`   | Fetch top posts from /r movies in the last month.            |

Multiple subreddits and search terms can also be specified, with a comma separation.

---

### Configuration Files

- `config.py`: Contains default settings like timeouts, retry attempts, and API limits.
- `.env`: Stores credentials and API keys.

---
