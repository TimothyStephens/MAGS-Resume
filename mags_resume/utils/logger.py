import logging
import os

def setup_logger():
    """Configures logging: plain-text to file only."""
    is_debug = os.getenv("MAGS_DEBUG")
    logger = logging.getLogger("mags_resume")
    level = logging.DEBUG if is_debug else logging.INFO
    logger.setLevel(level)
    
    # Prevent duplicate logs if called multiple times
    if logger.handlers:
        return logger

    # 1. File Handler (Plain text, no colors)
    log_dir = ".MAGS-Resume"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "workflow.log"), encoding="utf-8")
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    file_handler.setLevel(level)

    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()