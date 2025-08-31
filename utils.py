from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

# Basic UA
USER_AGENT = "RedditMediaGrabber/1.1 (by u/yourusername)"

# Content-Type -> extension map
EXT_MAP = {
    "video/mp4": ".mp4",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "external-preview.redd.it", "i.imgur.com")


def getenv_required(name: str) -> Optional[str]:
    val = os.getenv(name)
    return val.strip() if val and val.strip() else None


def get_download_dir() -> Path:
    env = os.getenv("OUTPUT_DIR")
    if env:
        p = Path(env).expanduser().resolve()
    else:
        p = Path.home() / "Downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- ID parsing ---
ID_PATTERNS = [
    re.compile(r"https?://(?:www\.)?redd\.it/([a-z0-9]{5,8})", re.I),
    re.compile(r"https?://(?:www\.)?reddit\.com/r/[^/]+/comments/([a-z0-9]{5,8})", re.I),
    re.compile(r"https?://(?:www\.)?reddit\.com/(?:u|user)/[^/]+/comments/([a-z0-9]{5,8})", re.I),
]
POST_ID_RE = re.compile(r"^[a-z0-9]{5,8}$", re.I)


def is_valid_post_id(s: str) -> bool:
    return bool(POST_ID_RE.fullmatch(s))


def parse_post_id(url_or_id: str) -> Tuple[str, Optional[str]]:
    s = (url_or_id or "").strip()
    for pat in ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1), s
    if s.lower().startswith(("http://", "https://")):
        return s, s
    return s, None


def sanitize_url(u: str | None) -> str | None:
    return u.replace("&amp;", "&") if isinstance(u, str) else u


def _ext_from_content_disposition(dispo: Optional[str]) -> Optional[str]:
    if not dispo:
        return None
    # crude filename= extractor
    m = re.search(r"filename\*=UTF-8''([^;\r\n]+)|filename=\"?([^;\r\n\"]+)\"?", dispo, re.I)
    filename = m.group(1) if m and m.group(1) else (m.group(2) if m else None)
    if not filename:
        return None
    filename = filename.split("?")[0]
    for ext in (".mp4", ".gif", ".jpg", ".jpeg", ".png", ".webp"):
        if filename.lower().endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return None


def sniff_ext_from_headers(content_type: Optional[str], url: str, content_disposition: Optional[str] = None) -> str:
    # 1) Try Content-Disposition filename
    if ext := _ext_from_content_disposition(content_disposition):
        return ext

    # 2) Try Content-Type map
    if content_type:
        ct = content_type.split(";", 1)[0].lower().strip()
        if ct in EXT_MAP:
            return EXT_MAP[ct]

    # 3) Heuristic by host if octet-stream or unknown
    host = urlparse(url).netloc.lower()
    if host.endswith("v.redd.it"):
        return ".mp4"
    if host.endswith(IMAGE_HOSTS):
        return ".jpg"

    # 4) Fallback by URL path
    path = urlparse(url).path.lower()
    for ext in (".mp4", ".gif", ".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext

    # 5) Last resort
    return ".bin"


# Optional yt-dlp fallback
try:
    from yt_dlp import YoutubeDL  # type: ignore
except Exception:
    YoutubeDL = None


def yt_dlp_download(url: str, outdir: Path) -> bool:
    if YoutubeDL is None:
        return False
    tmpl = str(outdir / "%(title).80s_%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": tmpl,
        "noplaylist": True,
        "quiet": False,
        "merge_output_format": "mp4",
        "cachedir": False,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return bool(info)
    except Exception:
        return False
