from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

USER_AGENT = "RedditMediaGrabber/1.1"

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
    if ext := _ext_from_content_disposition(content_disposition):
        return ext

    if content_type:
        ct = content_type.split(";", 1)[0].lower().strip()
        if ct in EXT_MAP:
            return EXT_MAP[ct]

    host = urlparse(url).netloc.lower()
    if host.endswith("v.redd.it"):
        return ".mp4"
    if host.endswith(IMAGE_HOSTS):
        return ".jpg"

    path = urlparse(url).path.lower()
    for ext in (".mp4", ".gif", ".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext

    return ".bin"


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

# ---------------- Azure Blob Upload ---------------- #

from typing import List
from azure.core.exceptions import ResourceExistsError

def upload_directory_to_blob(outdir: Path) -> List[str]:
    """
    Upload all files in outdir to Azure Blob Storage.
    Returns list of blob URLs if env vars are set.
    """
    import os
    from azure.storage.blob import BlobServiceClient

    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_BLOB_CONTAINER")

    if not conn_str or not container_name:
        print("Azure storage env vars not set. Skipping upload.")
        return []

    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container_client = blob_service.get_container_client(container_name)

    # Create container if it doesn't already exist
    try:
        container_client.create_container()
        print(f"Created blob container: {container_name}")
    except ResourceExistsError:
        print(f"Blob container already exists: {container_name}")

    uploaded_urls = []

    for file in outdir.glob("*"):
        if not file.is_file():
            continue

        blob_name = file.name

        with open(file, "rb") as data:
            container_client.upload_blob(name=blob_name, data=data, overwrite=True)

        blob_url = f"{container_client.url}/{blob_name}"
        uploaded_urls.append(blob_url)
        print(f"Uploaded to Blob: {blob_url}")

    return uploaded_urls
