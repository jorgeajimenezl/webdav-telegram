import youtube_dl
from pprint import pprint

ydl_opts = {}
with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    meta = ydl.extract_info(
        "https://www.youtube.com/watch?v=L3054pRMbw8", download=True
    )
    formats = meta.get("formats", [meta])
    ydl.list_formats
    pprint(ydl.prepare_filename(meta))
