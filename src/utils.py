import re
import itertools
import asyncio
from typing import Iterator, List


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"
    "]+"
)

WEBDAV_REMOVE_CHARACTERS = "&%?="


def strip_emoji(x: str) -> str:
    return EMOJI_PATTERN.sub(r"", x)


def sanitaze_filename(x: str) -> str:
    x = strip_emoji(x)
    for c in WEBDAV_REMOVE_CHARACTERS:
        x = x.replace(c, "")
    return x


def get_str(x: str) -> str:
    return x if x is not None else "Unknown"


def get_bool(x: str) -> bool:
    if isinstance(x, bool):
        return x

    x = x.lower()
    if x in ["on", "true", "activate", "right"]:
        return True
    if x in ["off", "false", "desactivate", "wrong"]:
        return False

    raise ValueError("Impossible convert from this string to bool")


def cut(x: str, length: int) -> List[str]:
    ret = []
    while x is not None and x != "":
        ret.append(x[:length])
        x = x[length:]
    return ret


def expand_ranges(x: str) -> Iterator[str]:
    ranges = []

    for match in re.finditer("\{([\d\-,A-Za-z&\.]+)\}", x):
        items = match[1].split(",")
        r = []

        for item in items:
            item = item.strip()

            if "-" in item:
                m = re.fullmatch("(\d+)-(\d+)", item)
                if not m:
                    raise Exception(f"Invalid range operation: line({match.start()})")
                r.extend(range(int(m[1]), int(m[2]) + 1))
            else:
                r.append(item)

        ranges.append(r)
    x = re.sub("\{([\d\-,A-Za-z&\.]+)\}", "{}", x)

    for t in itertools.product(*ranges):
        yield x.format(*t)


def escape_markdown(x: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", x)


async def execute_process(program: str, *args: List[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        program,
        *args,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(
            f"Process return code: {proc.returncode} Stderr: {stderr or ''}"
        )
