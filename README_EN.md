# SUNO Manager

English | [한국어](README.md)

A modern web application for AI music generation and management using SUNO AI.

## Features

- **Authentication**: Login using SUNO Bearer token (JWT)
- **Dashboard**: View generated music statistics and recent songs
- **Music Generation**: Generate music using AI prompts *(Coming Soon)*
- **Music Library**: Manage, play, download, and delete generated music
- **Global Audio Player**: Bottom-fixed player with equalizer animation
- **Lyrics View**: Display song lyrics/prompt in popup
- **Batch Download**: Download selected songs as ZIP file
- **Batch Delete**: Delete multiple selected songs at once
- **Credits Info**: Real-time credits and subscription info display

## Tech Stack

- **Backend**: Flask 3.0
- **Frontend**: Tailwind CSS (Dark Mode)
- **API**: SUNO Studio API (Real API Integration)

## Project Structure

```
suno-manager/
├── main.py                 # Flask application main file
├── suno_api.py            # SUNO API client
├── templates/             # HTML templates
│   ├── base.html         # Base layout (includes global player)
│   ├── login.html        # Login page
│   ├── dashboard.html    # Dashboard page
│   ├── generate.html     # Music generation page
│   └── library.html      # Library page
├── static/               # Static files
├── downloads/            # Downloaded music files
├── .env                  # Environment variables
├── .env.example          # Environment variables example
└── README.md
```

## Installation & Setup

### 1. Install Packages

Install required Python packages:

```bash
pip install Flask requests python-dotenv
```

### 2. Environment Setup

Copy `.env.example` to `.env` and modify with actual values:

```bash
cp .env.example .env
```

Set the following values in `.env`:

```
SUNO_BEARER_TOKEN=your_actual_bearer_token
SECRET_KEY=your_random_secret_key
```

### 3. Get SUNO Bearer Token

1. Log in to [SUNO website](https://suno.com)
2. Open browser developer tools (F12)
3. Select **Network** tab
4. Refresh the page (F5)
5. Click on any request starting with `feed` or `api`
6. Find `authorization` header in **Request Headers**
7. Copy the `Bearer eyJhbGciOiJSUzI1NiIs...` value (with or without Bearer prefix)
8. Paste it in `.env` file's `SUNO_BEARER_TOKEN`

Or you can enter it directly on the login page after running the application.

### 4. Run Application

```bash
python main.py
```

Open `http://localhost:5000` in your browser

## Usage

### Login

1. Open `http://localhost:5000` in your browser
2. Enter SUNO Bearer token (JWT token)
3. Click Login button

### Dashboard

- View total songs, generating songs, and today's songs statistics
- Preview 5 recently created songs
- Check credits info and subscription status

### Music Library

- View all generated music
- Search and sort features (by title, date)
- Actions available for each song:
  - **Play**: Play music in bottom player
  - **Lyrics**: Show lyrics/prompt popup
  - **Download**: Download MP3 file
  - **Delete**: Delete music
- Batch Download: Select multiple songs and download as ZIP file
- Batch Delete: Select and delete multiple songs at once

### Music Generation *(Coming Soon)*

> This feature is currently under development.

- Generate music by entering prompts
- Set advanced options like genre, mood, tempo
- Example prompts provided

## API Endpoints

### Authentication

```http
POST /login
Content-Type: application/json

{
  "token": "eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIs..."
}
```

### Get Credits Info

```http
GET /api/billing/info
```

### Get Songs List

```http
GET /api/songs?page=0
```

### Delete Song

```http
DELETE /api/songs/{song_id}
```

### Download Song

```http
GET /api/songs/{song_id}/download
```

### Batch Download

```http
POST /api/songs/batch-download
Content-Type: application/json

{
  "song_ids": ["id1", "id2", "id3"]
}
```

## SUNO API Integration

This project uses the actual SUNO Studio API:

- **API Endpoint**: `https://studio-api.prod.suno.com/api`
- **Authentication**: Bearer Token (JWT)
- **Response Structure**: Uses actual SUNO response structure (`clips` array)

## Highlights

- **Real-time Data**: View your SUNO account's music list in real-time
- **Global Audio Player**: Music playback continues during page navigation
- **Equalizer Animation**: Visualize currently playing song
- **Album Covers**: Display SUNO-generated images
- **Play Count**: View play count for each song
- **Tags Display**: Show genre/style tags
- **Credits Info**: Real-time credits balance and subscription info
- **Session Management**: Token management via Flask session

## Development Environment

- Python 3.8+
- Flask 3.0
- Modern browsers (Chrome, Firefox, Safari, Edge)

## Security Notes

- Never commit `.env` file to Git
- Keep Bearer tokens secure as they contain sensitive information
- Bearer tokens expire after some time and need periodic renewal
- Always change `SECRET_KEY` in production environment

## License

MIT License

## Contributing

Issues and pull requests are always welcome!
