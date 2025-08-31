import os
import platform
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse


# Keep your UA clear and consistent
USER_AGENT = "RedditMediaGrabber/1.0 (by u/yourusername)"

EXT_MAP = {
    "video/mp4": ".mp4",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

def sniff_ext_from_headers(content_type: Optional[str], url: str) -> str:
    if content_type:
        ct = content_type.split(";", 1)[0].lower().strip()
        if ct in EXT_MAP:
            return EXT_MAP[ct]
    # fallback by URL path
    path = urlparse(url).path.lower()
    for ext in (".mp4", ".gif", ".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".bin"

def sanitize_url(u: str) -> str:
    return u.replace("&amp;", "&")

def getenv_required(name: str) -> Optional[str]:
    val = os.getenv(name)
    return val if val and val.strip() else None

import shutil
import subprocess
import tempfile
from pathlib import Path
def ffmpeg_convert_mp4_to_gif(src_mp4: Path, dst_gif: Path):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found. Install ffmpeg first.")
    # 2-pass palette for decent quality/size
    filt = (
        "fps=15,scale=640:-1:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_mp4), "-vf", filt, "-loop", "0", str(dst_gif)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

# Recognize common Reddit post URL shapes, including user profile comment permalinks
ID_PATTERNS = [
re.compile(r"https?://(?:www\.)?redd\.it/([a-z0-9]{5,8})(?:[/?#]|$)", re.I),
re.compile(r"https?://(?:www\.)?reddit\.com/r/[^/]+/comments/([a-z0-9]{5,8})(?:[/?#]|$)", re.I),
re.compile(r"https?://(?:www\.)?reddit\.com/(?:r/[^/]+/)?comments/([a-z0-9]{5,8})(?:[/?#]|$)", re.I),
re.compile(r"https?://(?:www\.)?reddit\.com/(?:u|user)/[^/]+/comments/([a-z0-9]{5,8})(?:[/?#]|$)", re.I),
]

POST_ID_RE = re.compile(r"^[a-z0-9]{5,8}$", re.I)

def is_valid_post_id(s: str) -> bool:
    """True if string is exactly a 5–8 char base36 Reddit post ID."""
    return bool(POST_ID_RE.fullmatch(s))


def get_download_dir() -> Path:
    """Return the output directory. If OUTPUT_DIR is set, use it; otherwise ~/Downloads."""
    env = os.getenv("OUTPUT_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Default to ~/Downloads on macOS, Windows, Linux
    home = Path.home()
    dl = home / "Downloads"
    dl.mkdir(parents=True, exist_ok=True)
    return dl


def parse_post_id(url_or_id: str) -> Tuple[str, Optional[str]]:
    """
    Given a Reddit URL or bare ID, return (post_id_or_input, original_url_or_None).

    - If a recognized Reddit URL contains a valid post ID, returns (id, full_url)
    - If input is a URL but we couldn't extract an ID, returns (input, full_url)
    - Otherwise assume it's a bare ID and return (input, None)
    """
    s = (url_or_id or "").strip()
    for pat in ID_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1), s

    if s.lower().startswith(("http://", "https://")):
        return s, s
    return s, None