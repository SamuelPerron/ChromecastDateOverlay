import requests
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

BASE_ALBUM_NAME = 'TV Album (base)'
TARGET_ALBUM_NAME = 'TV Album (live)'

# This is the "permissions" of the app
# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/photoslibrary.readonly',
    'https://www.googleapis.com/auth/photoslibrary',
    'https://www.googleapis.com/auth/photoslibrary.sharing'
]

creds = None
# The file token.pickle stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)

# If there are no (valid) credentials available, let the user log in.
# This will open a browser window, asking the user to auth and authorize the app.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)

    # Save the credentials for the next run
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)

google_photos = build('photoslibrary', 'v1', credentials=creds)


# Fetch pictures
albums = google_photos.albums().list().execute()['albums']
base_album = None
live_album = None
for album in albums:
    if album['title'] == BASE_ALBUM_NAME:
        base_album = album

    # Use this to create the album the first time, otherwise the app won't be able to update it.
    # create_body = {'album': {'title': TARGET_ALBUM_NAME}}
    # live_album = google_photos.albums().create(body=create_body).execute()
    # Otherwise 'find' it in the list
    if album['title'] == TARGET_ALBUM_NAME:
        live_album = album

if live_album and base_album:
    date = datetime.now().strftime('%A, %d %B %Y')
    upload_tokens = []


    # Remove old pictures
    # Sadly we can't delete them, the only action possible is to remove them from the album.
    search_body = {
        'albumId': live_album['id'],
        'pageSize': 100,
    }
    results = google_photos.mediaItems().search(body=search_body).execute()
    old_items = results.get('mediaItems', [])
    if len(old_items) > 0:
        remove_body = {'mediaItemIds': [item['id'] for item in old_items]}
        google_photos.albums().batchRemoveMediaItems(albumId=live_album['id'], body=remove_body).execute()


    # Fetch photos from the base album
    search_body = {
        'albumId': base_album['id'],
        'pageSize': 100,
    }
    results = google_photos.mediaItems().search(body=search_body).execute()
    items = results.get('mediaItems', [])

    for item in items:
        r = requests.get(f"{item['baseUrl']}=d")

        # Saving them
        path = f'photos/{item["filename"]}'
        with open(path, 'wb') as f:
            f.write(r.content)


        # Write date
        img = Image.open(path)
        drawing = ImageDraw.Draw(img)
        font = ImageFont.truetype('fonts/Comfortaa-Regular.ttf', 100)

        width, height = img.size
        text_width, text_height = drawing.textsize(date, font)
        margin = 100
        # This will write it in the down left corner
        x = margin
        y = height - text_height - margin

        drawing.text((x, y), date, font=font, fill=(255, 255, 255))
        img.save(path)


        # Upload tagged photos
        image_data = open(path, 'rb').read()
        r = requests.post('https://photoslibrary.googleapis.com/v1/uploads', headers={
                'Authorization': 'Bearer ' + creds.token,
                'Content-type': 'application/octet-stream',
                'X-Goog-Upload-Protocol': 'raw',
                'X-Goog-File-Name': item['filename'].split('.')[0]
            }, data=image_data)
        upload_tokens.append(r.content.decode('utf-8'))

print('Uploading...')
# Limit of 50 photos per batch
# This is dirty, but I only have 80 or so photos in my album
# It's a problem for future me hehe
parts = (upload_tokens[:50], upload_tokens[50:])
for part in range(0,1):
    new_media_items = [{'simpleMediaItem': {'uploadToken': tok}} for tok in parts[part]]
    request_body = {'newMediaItems': new_media_items, 'albumId': live_album['id']}
    google_photos.mediaItems().batchCreate(body=request_body).execute()
