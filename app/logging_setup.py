import logging

COLORS: dict[str, str] = {
    "DEBUG": "\033[94m",
    "INFO": "\033[92m",
    "WARNING": "\033[93m",
    "ERROR": "\033[91m",
    "CRITICAL": "\033[95m",
}


class ColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        color = COLORS.get(record.levelname, "")
        log_fmt = f"%(asctime)s - %(name)s - {color}%(levelname)s\033[0m - %(message)s"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def setup():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    logging.getLogger().handlers[0].setFormatter(ColoredFormatter())
