import logging
import logging.handlers
import os
import sys
from platformdirs import user_data_dir

# Color settings for console output
class LogColors:
    RESET = '\033[0m'
    RED = '\033[31m'
    YELLOW = '\033[33m'
    GREEN = '\033[32m'
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'

# Custom Formatter with color support for console
class ColorFormatter(logging.Formatter):
    def format(self, record):
        color = LogColors.RESET
        if record.levelno == logging.DEBUG:
            color = LogColors.CYAN
        elif record.levelno == logging.INFO:
            color = LogColors.GREEN
        elif record.levelno == logging.WARNING:
            color = LogColors.YELLOW
        elif record.levelno == logging.ERROR:
            color = LogColors.RED
        elif record.levelno == logging.CRITICAL:
            color = LogColors.MAGENTA

        record.levelname = f"{color}{record.levelname}{LogColors.RESET}"
        return super().format(record)

# Initialize Logger
def setup_logger(env='DEV', backup_count=30):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if env == 'DEV' else logging.INFO)

    if env == "DEV":
        log_dir = 'logs'

    else:
        log_dir = user_data_dir(
            appname="Can-LW",
            appauthor="Can-LW"
        )
    
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app.log')  # fixed filename (auto rotate)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s %(filename)s %(funcName)s %(lineno)d %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Timed Rotating File Handler (rotate every midnight, keep backup_count days)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',        # Xoay file vào 0h mỗi ngày
        backupCount=backup_count, # Giữ bao nhiêu file cũ
        encoding='utf-8',
        utc=False
    )
    file_handler.suffix = "%Y%m%d"  # Suffix cho file, vd: app.log.2025-04-27
    file_handler.setFormatter(formatter)

    # Console Handler (with color)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = ColorFormatter(
        '%(asctime)s %(filename)s %(funcName)s %(lineno)d %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

LOG = logging.getLogger()
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[logging.StreamHandler(sys.stderr)]
)
logging.getLogger('matplotlib').setLevel(logging.WARNING)
logging.getLogger("PIL.PngImagePlugin").setLevel(logging.WARNING)

# Example usage
if __name__ == '__main__':
    logger = setup_logger(env='development', backup_count=30)

    logger.debug('This is a debug message')
    logger.info('This is an info message')
    logger.warning('This is a warning message')
    logger.error('This is an error message')
    logger.critical('This is a critical message')
