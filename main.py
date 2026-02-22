from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from utils import (
    USER_AGENT,
    get_download_dir,
    parse_post_id,
    is_valid_post_id,
    getenv_required,
    sanitize_url,
    sniff_ext_from_headers,
    yt_dlp_download,
    upload_directory_to_blob,
)

load_dotenv()

API_BASE = "https://oauth.reddit.com"
PUBLIC_BASE = "https://www.reddit.com"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "external-preview.redd.it", "i.imgur.com")

EXTERNAL_EXCLUDE_DOMAINS = {
    "reddit.com",
    "redd.it",
    "v.redd.it",
    "i.redd.it",
    "preview.redd.it",
    "external-preview.redd.it",
}


# ---------------- Input ---------------- #

def get_target() -> str:
    """Return Reddit URL/ID from CLI arg or env var; fail if missing."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()

    env_url = getenv_required("REDDIT_POST_URL")
    if env_url:
        return env_url

    raise SystemExit("Missing target URL/ID. Pass arg or set REDDIT_POST_URL.")


# ---------------- API ---------------- #

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
    r = requests.post(
        f"{API_BASE}/api/v1/access_token", auth=auth, data=data, headers=headers, timeout=20
    )
    r.raise_for_status()
    return r.json().get("access_token")


def fetch_post(post_id: str, token: Optional[str]) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    cookies = {"over18": "1"}
    if token:
        headers["Authorization"] = f"bearer {token}"
        url = f"{API_BASE}/comments/{post_id}?raw_json=1"
    else:
        url = f"{PUBLIC_BASE}/comments/{post_id}.json?raw_json=1"

    r = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data:
        return data[0]["data"]["children"][0]["data"]
    return data if isinstance(data, dict) else {}


def canonical_post(post: Dict[str, Any]) -> Dict[str, Any]:
    cpl = post.get("crosspost_parent_list")
    if isinstance(cpl, list) and cpl:
        return cpl[0]
    return post


# ---------------- Detect ---------------- #

def is_imageish_url(u: Optional[str]) -> bool:
    if not u:
        return False
    p = urlparse(u)
    if any(p.path.lower().endswith(ext) for ext in IMAGE_EXTS):
        return True
    return any(p.netloc.lower().endswith(h) for h in IMAGE_HOSTS)


def is_external_domain(host: str) -> bool:
    return not any(host.endswith(d) for d in EXTERNAL_EXCLUDE_DOMAINS)


def detect_media_type(post: Dict[str, Any]) -> str:
    """Return one of: video | gallery | direct_image | preview_image | external | unknown."""
    if (
        post.get("is_video")
        or post.get("post_hint") == "hosted:video"
        or (post.get("media") or {}).get("reddit_video")
        or (post.get("secure_media") or {}).get("reddit_video")
        or (post.get("domain") or "").lower() == "v.redd.it"
    ):
        return "video"

    if "gallery_data" in post and "media_metadata" in post:
        return "gallery"

    if post.get("post_hint") == "rich:video":
        return "external"

    uod = sanitize_url(post.get("url_overridden_by_dest"))
    if is_imageish_url(uod):
        return "direct_image"

    if (post.get("preview") or {}).get("images"):
        return "preview_image"

    if uod:
        return "external"

    return "unknown"


def extract_external_media_url(post: Dict[str, Any]) -> Optional[str]:
    """Pick best external URL for yt-dlp."""
    u = sanitize_url(post.get("url_overridden_by_dest") or post.get("url"))
    if u:
        host = urlparse(u).netloc.lower()
        if is_external_domain(host) and not is_imageish_url(u):
            return u

    for key in ("media", "secure_media"):
        m = post.get(key) or {}
        oe = m.get("oembed")
        if isinstance(oe, dict):
            if oe.get("url"):
                return sanitize_url(oe["url"])
            if oe.get("html"):
                msrc = re.search(r'src="([^"]+)"', oe["html"])
                if msrc:
                    return sanitize_url(msrc.group(1))
    return None


# ---------------- Download ---------------- #

def download_file(url: str, outpath_stem: Path) -> None:
    outpath_stem.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.reddit.com/"}
    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        r.raise_for_status()
        ct = r.headers.get("Content-Type")
        cd = r.headers.get("Content-Disposition")
        ext = sniff_ext_from_headers(ct, url, cd)
        outpath = outpath_stem.with_suffix(ext)
        with open(outpath, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 15):
                if chunk:
                    f.write(chunk)
    print(f"Saved {outpath} (Content-Type: {ct})")


# ---------------- Handlers ---------------- #

def handle_video(post: Dict[str, Any], outdir: Path) -> Dict[str, Any]:
    rv = (post.get("media") or {}).get("reddit_video") or (post.get("secure_media") or {}).get("reddit_video") or {}
    info = {
        "type": "video",
        "fallback_url": sanitize_url(rv.get("fallback_url")),
        "hls_url": sanitize_url(rv.get("hls_url")),
        "dash_url": sanitize_url(rv.get("dash_url")),
        "has_audio": rv.get("has_audio"),
    }
    print("Branch: VIDEO")
    if info["fallback_url"]:
        download_file(info["fallback_url"], outdir / post.get("id", "post"))
    else:
        print("Video detected but no fallback_url available")
    return info


def handle_gallery(post: Dict[str, Any], outdir: Path) -> Dict[str, Any]:
    print("Branch: GALLERY")
    meta = post["media_metadata"]
    items = []
    base = post.get("id", "post")

    for idx, it in enumerate(post["gallery_data"].get("items", []), 1):
        mid = it.get("media_id")
        m = meta.get(mid, {}) if isinstance(meta, dict) else {}
        kind = m.get("e")
        s = m.get("s") or {}
        base_name = f"{base}_{idx:02d}"

        if kind == "Image":
            url = sanitize_url(s.get("u"))
            if url:
                items.append({"type": "image", "url": url})
                download_file(url, outdir / base_name)

        elif kind == "AnimatedImage":
            gif = sanitize_url(s.get("gif"))
            mp4 = sanitize_url(s.get("mp4"))
            if gif:
                items.append({"type": "gif", "url": gif})
                download_file(gif, outdir / base_name)
            elif mp4:
                items.append({"type": "animated_mp4", "url": mp4})
                download_file(mp4, outdir / base_name)

    return {"type": "gallery", "items": items}


def handle_direct_image(post: Dict[str, Any], outdir: Path) -> Dict[str, Any]:
    print("Branch: DIRECT_IMAGE")
    u = sanitize_url(post.get("url_overridden_by_dest") or post.get("url"))
    if u:
        download_file(u, outdir / post.get("id", "post"))
    return {"type": "image", "url": u}


def handle_preview_image(post: Dict[str, Any], outdir: Path) -> Dict[str, Any]:
    print("Branch: PREVIEW_IMAGE (fallback)")
    preview = post.get("preview") or {}
    images = preview.get("images") or []
    url = None
    if images:
        url = sanitize_url((images[0].get("source") or {}).get("url"))
        if url:
            download_file(url, outdir / post.get("id", "post"))
    return {"type": "image_preview", "url": url}


def handle_external(post: Dict[str, Any], outdir: Path) -> Dict[str, Any]:
    print("Branch: EXTERNAL")
    target = extract_external_media_url(post) or sanitize_url(
        post.get("url_overridden_by_dest") or post.get("url")
    )
    info = {"type": "external", "url": target}
    if target:
        print(f"yt-dlp target: {target}")
        if yt_dlp_download(target, outdir):
            info["downloaded_via"] = "yt-dlp"
        else:
            info["downloaded_via"] = None
    else:
        print("No external target URL found for yt-dlp.")
        info["downloaded_via"] = None
    return info


# ---------------- Main ---------------- #

def main() -> None:
    url_or_id = get_target()
    outdir = get_download_dir()
    print(f"Output dir: {outdir}")

    post_id, _ = parse_post_id(url_or_id)
    token = get_token()

    try:
        post_raw = fetch_post(post_id, token) if is_valid_post_id(post_id) else {}
    except requests.HTTPError as e:
        print(f"Reddit API fetch failed: {e}")
        return

    if not post_raw:
        print("No post data fetched.")
        return

    post = canonical_post(post_raw)
    kind = detect_media_type(post)

    if kind == "video":
        handle_video(post, outdir)
    elif kind == "gallery":
        handle_gallery(post, outdir)
    elif kind == "direct_image":
        handle_direct_image(post, outdir)
    elif kind == "preview_image":
        handle_preview_image(post, outdir)
    elif kind == "external":
        handle_external(post, outdir)
    else:
        print("Branch: UNKNOWN")
        return

    # After download completes
    uploaded = upload_directory_to_blob(outdir)

    if uploaded:
        print("Uploaded blobs:")
        for url in uploaded:
            print(url)


if __name__ == "__main__":
    main()
    