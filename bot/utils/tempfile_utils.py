#tempfile_utils.py
import tempfile
import logging

logger = logging.getLogger(__name__)

def create_temp_dir(prefix: str) -> str:
    """
    Creates a temporary directory with the given prefix.
    """
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        return temp_dir
    except Exception as e:
        logger.error(f"Error creating temporary directory with prefix '{prefix}': {e}", exc_info=True)
        raise
