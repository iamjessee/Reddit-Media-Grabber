import os
import sys
import json
import time
from pathlib import Path
from typing import Optional
import subprocess
import shutil
import tempfile
from urllib.parse import urlparse

import requests
from yt_dlp import YoutubeDL

from dotenv import load_dotenv
load_dotenv()

from utils import get_download_dir, parse_post_id, is_valid_post_id, USER_AGENT, sanitize_url, EXT_MAP, sniff_ext_from_headers, getenv_required, ffmpeg_convert_mp4_to_gif


API_BASE = "https://oauth.reddit.com"
PUBLIC_BASE = "https://www.reddit.com"


def get_token() -> Optional[str]:
    """Return OAuth token if credentials provided, else None."""
    cid = getenv_required("REDDIT_CLIENT_ID")
    csec = getenv_required("REDDIT_CLIENT_SECRET")
    user = getenv_required("REDDIT_USERNAME")
    pwd = getenv_required("REDDIT_PASSWORD")
    if not all([cid, csec, user, pwd]):
        return None

    auth = requests.auth.HTTPBasicAuth(cid, csec)
    data = {"grant_type": "password", "username": user, "password": pwd}
    headers = {"User-Agent": USER_AGENT}
    r = requests.post(f"{API_BASE}/api/v1/access_token", auth=auth, data=data, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json().get("access_token")


def get_post_json(post_id: str, token: Optional[str]) -> dict:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"bearer {token}"
        url = f"{API_BASE}/comments/{post_id}?raw_json=1"
    else:
        url = f"{PUBLIC_BASE}/comments/{post_id}.json?raw_json=1"

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data:
        return data[0]["data"]["children"][0]["data"]
    return data


def is_gallery(post: dict) -> bool:
    return "gallery_data" in post and "media_metadata" in post




def download_file(url: str, outpath_stem: Path):
    outpath_stem.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.reddit.com/"}
    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        r.raise_for_status()
        ext = sniff_ext_from_headers(r.headers.get("Content-Type"), url)
        outpath = outpath_stem.with_suffix(ext)
        with open(outpath, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 15):
                if chunk:
                    f.write(chunk)
        print(f"Saved {outpath.name} ({r.headers.get('Content-Type')})")


def download_gallery(post: dict, outdir: Path):
    media_ids = [item["media_id"] for item in post["gallery_data"]["items"]]
    meta = post["media_metadata"]
    base = post.get("id", "post")

    for idx, mid in enumerate(media_ids, start=1):
        m = meta[mid]
        kind = m.get("e")  # Image or AnimatedImage
        base_name = f"{base}_{idx:02d}"

        if kind == "Image":
            url = sanitize_url(m["s"]["u"])
            download_file(url, outdir / f"{base_name}.jpg")
            print(f"Saved {base_name}.jpg")
            continue

        if kind == "AnimatedImage":
            gif_url = sanitize_url(m.get("s", {}).get("gif") or "")
            mp4_url = sanitize_url(m.get("s", {}).get("mp4") or "")

            if gif_url:
                download_file(gif_url, outdir / f"{base_name}.gif")
                print(f"Saved {base_name}.gif")
                continue

            if mp4_url:
                # Convert MP4 → GIF so Preview opens it as a true GIF
                with tempfile.TemporaryDirectory() as td:
                    tmp_mp4 = Path(td) / f"{base_name}.mp4"
                    download_file(mp4_url, tmp_mp4)
                    out_gif = outdir / f"{base_name}.gif"
                    ffmpeg_convert_mp4_to_gif(tmp_mp4, out_gif)
                    print(f"Saved {out_gif.name} (converted from mp4)")
                continue

        print(f"Skipping unsupported item {mid}: kind={kind}")


def ytdlp_download(url: str, outdir: Path) -> bool:
    tmpl = str(outdir / "%(title).80s_%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": tmpl,
        "noplaylist": True,
        "quiet": False,
        "merge_output_format": "mp4",
        "cachedir": False,
        # Be explicit about cookie handling off by default
        "cookiesfrombrowser": None,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Check if a file was actually downloaded
            # info["_filename"] is set for single video/image, or check for entries in playlist
            output_files = []
            if info.get("_filename"):
                output_files.append(info["_filename"])
            elif "entries" in info:
                for entry in info["entries"] or []:
                    if entry and entry.get("_filename"):
                        output_files.append(entry["_filename"])
            # Only return True if at least one file exists
            for f in output_files:
                if f and Path(f).exists():
                    return True
            return False
    except Exception as e:
        print(f"yt-dlp failed: {e}")
        return False


def main():
    if len(sys.argv) > 1:
        url_or_id = sys.argv[1]
    else:
        url_or_id = input("Paste Reddit post URL or ID: ").strip()


    outdir = get_download_dir()
    print(f"Output directory: {outdir}")

    # Use utils to extract and validate post ID
    post_id, maybe_url = parse_post_id(url_or_id)
    if not is_valid_post_id(post_id):
        print("Could not extract valid post ID for Reddit API. Trying yt-dlp as fallback...")
        ok = ytdlp_download(url_or_id, outdir)
        if ok:
            print("Done.")
        else:
            print("No media downloaded. The post might have unsupported media or requires cookies.")
        return
    token = get_token()
    try:
        post = get_post_json(post_id, token)
    except requests.HTTPError as e:
        print(f"Reddit API fetch failed: {e}. Trying yt-dlp as fallback...")
        ok = ytdlp_download(url_or_id, outdir)
        if ok:
            print("Done.")
        else:
            print("No media downloaded. The post might have unsupported media or requires cookies.")
        return

    # Handle gallery
    if is_gallery(post):
        print("Detected gallery. Downloading via Reddit API.")
        download_gallery(post, outdir)
        print("Done.")
        return

    # Handle single-image posts
    post_hint = post.get("post_hint")
    url = post.get("url")
    if post_hint == "image" and url:
        print("Detected single image post. Downloading via Reddit API.")
        base = post.get("id", "post")
        download_file(url, outdir / f"{base}")
        print("Done.")
        return

    # Handle Reddit-hosted video posts
    if post_hint == "hosted:video" and "media" in post and "reddit_video" in post["media"]:
        video_url = post["media"]["reddit_video"].get("fallback_url")
        if video_url:
            print("Detected Reddit-hosted video post. Downloading via Reddit API.")
            base = post.get("id", "post")
            download_file(video_url, outdir / f"{base}")
            print("Done.")
            return

    # If not handled, try yt-dlp as fallback
    print("Post type not handled by API. Trying yt-dlp as fallback...")
    ok = ytdlp_download(url_or_id, outdir)
    if ok:
        print("Done.")
    else:
        print("No media downloaded. The post might have unsupported media or requires cookies.")


if __name__ == "__main__":
    main()
