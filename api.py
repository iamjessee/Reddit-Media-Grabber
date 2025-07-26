import requests
import os

def download_image(url, filename):
    """Download an image from a URL and save it to a file."""
    try:
        img_data = requests.get(url).content
        os.makedirs("downloads", exist_ok=True)
        filepath = os.path.join("downloads", filename)
        with open(filepath, "wb") as f:
            f.write(img_data)
        print(f"Downloaded {filename}")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")

def process_gallery(post):
    media_ids = [item['media_id'] for item in post['gallery_data']['items']]
    media_meta = post['media_metadata']

    for idx, media_id in enumerate(media_ids):
        media = media_meta[media_id]
        media_type = media.get("e")
        base_filename = f"{post['id']}_media_{idx+1}"

        if media_type == "Image":
            url = media['s']['u'].replace("&amp;", "&")
            filename = base_filename + ".jpg"
        elif media_type == "AnimatedImage":
            url = media['s'].get('mp4') or media['s'].get('gif')
            url = url.replace("&amp;", "&")
            ext = ".mp4" if "mp4" in url else ".gif"
            filename = base_filename + ext
        else:
            print(f"Unsupported media type: {media_type}")
            continue

        print(f"Downloading: {filename} from {url}")
        download_image(url, filename)

def main():
    secrets = {}
    with open("secrets.txt") as file:
        for line in file:
            key, value = line.strip().split("=", 1)
            secrets[key] = value

    username = secrets["USERNAME"]
    password = secrets["PASSWORD"]
    CLIENT_ID = secrets["CLIENT_ID"]
    CLIENT_SECRET = secrets["CLIENT_SECRET"]

    auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    data = {
        "grant_type": "password",
        "username": username,
        "password": password
    }
    headers = {
        "User-Agent": "MEDIA_GRABBER/1.0"
    }

    res = requests.post("https://www.reddit.com/api/v1/access_token", auth=auth, data=data, headers=headers)
    TOKEN = res.json()['access_token']
    headers["Authorization"] = f"bearer {TOKEN}"

    # Get post data
    post_id = input("Enter Reddit post ID (e.g. 1m990a6): ").strip()
    res = requests.get(f"https://oauth.reddit.com/comments/{post_id}", headers=headers)
    post = res.json()[0]['data']['children'][0]['data']

    # Process the post
    if 'gallery_data' in post and 'media_metadata' in post:
        print("Gallery detected.")
        process_gallery(post)
    else:
        print("Not a gallery post.")
        print("Post Title:", post.get("title"))
        print("URL:", post.get("url"))

if __name__ == "__main__":
    main()
