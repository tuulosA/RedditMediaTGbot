import json
import os
import logging
from reddit.config import Paths

logger = logging.getLogger(__name__)

def load_blacklist():
    """Load the blacklist of dead links from a JSON file."""
    if not os.path.exists(Paths.BLACKLIST_FILE):
        logger.info(f"Blacklist file not found. Creating a new blacklist: {Paths.BLACKLIST_FILE}")
        return set()
    try:
        with open(Paths.BLACKLIST_FILE, "r", encoding="utf-8") as file:
            blacklist = set(json.load(file))
            return blacklist
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from blacklist file {Paths.BLACKLIST_FILE}: {e}")
        return set()
    except Exception as e:
        logger.error(f"Error loading blacklist file {Paths.BLACKLIST_FILE}: {e}")
        return set()

def save_blacklist(blacklist):
    """Save the blacklist of dead links to a JSON file."""
    try:
        with open(Paths.BLACKLIST_FILE, "w", encoding="utf-8") as file:
            json.dump(list(blacklist), file, indent=4)
        logger.info(f"Successfully saved {len(blacklist)} entries to blacklist.")
    except Exception as e:
        logger.error(f"Error saving blacklist to file {Paths.BLACKLIST_FILE}: {e}")

def add_to_blacklist(link):
    """Add a link to the blacklist and save it."""
    blacklist = load_blacklist()
    if link in blacklist:
        logger.warning(f"Link already in blacklist: {link}")
        return
    blacklist.add(link)
    logger.info(f"Added link to blacklist: {link}")
    save_blacklist(blacklist)

def is_blacklisted(link: str) -> bool:
    """
    Check if a given link is in the blacklist.
    """
    blacklist = load_blacklist()
    if link in blacklist:
        logger.info(f"Link is blacklisted: {link}")
        return True
    return False
