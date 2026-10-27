# ZENOS Images · Library and Studio

The Images app keeps a library of music and pictures and has a Studio for small pieces made from them: trim a
song, put a picture on it, and export one MP4. Optionally, an AI that the person registered themselves can turn the
picture into a short moving clip that loops under the audio.

Intended for the Personal and Family editions. In Office deployments the administrator can turn the AI part off.

Design: Figma file x0pQlpFnMH8BpNDARH7LlJ, frames 94:2 (Library · Music), 94:307 (Library · Pictures), 91:2 (Studio).

## What the library shows

Only plain files in L1 places: the Basic · L1 folder on the desktop, `~/Music`, `~/Pictures` and `~/Videos`.
Sealed files (`.zen`) and anything inside a higher-level folder are never listed and cannot be opened in the
Studio. Playlists, picture albums, which picture goes with which song, and Studio projects are kept in
`~/.config/zenos/studio.json`.

## Audio and video

Trimming, fades and the MP4 export use `ffmpeg` (H.264 video, AAC audio, 1920x1080, the picture letterboxed).
The original file is never overwritten.

## Motion with AI

ZENOS ships no video model and adds no AI service. The person enters the address and API key of a service they
use under their own account; the key is kept in the app's local storage on this PC and sent only with each request.

Rules, checked by `core/bin/zenos_studio.py` before anything leaves the PC:

- the picture must be an L1 file (not sealed, not in a higher-level folder);
- the address must be `https://` (plain `http://` only to `127.0.0.1` / `localhost`, for testing);
- `studio_ai = off` in `/etc/zenos/policy.conf` turns the feature off;
- every request is written to the audit log (`studio-ai`, the file name and the service's host name).

### The request

```
POST <address>
Authorization: Bearer <key>
Content-Type: application/json

{"model": "<optional>", "prompt": "<the person's words>", "image": "data:image/jpeg;base64,…", "duration_seconds": 5}
```

The service may answer in any of these ways:

- the video itself (`Content-Type: video/…`);
- JSON with a link: `{"video_url": "https://…"}` (also `url`, `video`, or `output` as a string or list);
- JSON with a job to check: `{"status": "queued", "status_url": "https://…"}` (or `poll_url`). ZENOS asks that
  address every 5 seconds, for up to 15 minutes, until the answer carries a video link; `status` of `failed`,
  `error` or `cancelled` stops it;
- JSON with `{"error": "…"}`, which is shown to the person.

Services with a different API need a small adapter in front of them that speaks this format.

The clip is saved in `~/Videos/ZENOS Studio`. Tests: `tests/test_studio.py` (a local mock service).
