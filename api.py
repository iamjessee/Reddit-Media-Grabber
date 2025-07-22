import requests

# run ./env/bin/python api.py

secrets = {}
with open("secrets.txt") as file:
    for line in file:
        key, value = line.strip().split("=", 1)
        secrets[key] = value

username = secrets["USERNAME"]
password = secrets["PASSWORD"]
CLIENT_ID = secrets["CLIENT_ID"]
CLIENT_SECRET = secrets["CLIENT_SECRET"]

CLIENT_ID = CLIENT_ID
CLIENT_SECRET = CLIENT_SECRET

auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)




data = {
    "grant_type": "password",
    "username": username,
    "password": password
}

header = {
    "User-Agent": "MEDIA_GRABBER/1.0 "
}

res = requests.post(
    "https://www.reddit.com/api/v1/access_token",
    auth=auth,
    data=data,
    headers=header
)

TOKEN = res.json()['access_token']

header["Authorization"] = f"bearer {TOKEN}"


post = requests.get(
    "https://oauth.reddit.com/r/osrs/hot",
    headers=header)

for post in post.json()['data']['children']:
    print(post['data']['title'])
    print(post['data']['url'])
    print()
    print("--------------------------------------------------")

