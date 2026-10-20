# Hookreel

Two ways to make a short ad for a game or app, as a finished MP4 in vertical, portrait, square or landscape:

1. **From a recording** (main page): upload a screen recording, pick the best moment, add an opening line,
   captions and an end card.
2. **From screenshots** (second page in the sidebar): upload 2 to 8 real screenshots (and optionally a short real
   clip). Claude writes the hook and captions from your description, the app adds slow zoom and pan to each
   screenshot, then your end card. No avatars, voices or invented gameplay: only your real visuals.

Built on the Apex pattern in APP_BLUEPRINT.md: Streamlit page, logins with roles, append-only saving on Supabase (every ad is recorded, and finished ads are kept for 'Earlier ads'),
plain Python modules with no Streamlit inside (adlib.py, store.py, config.py).

## Run it locally
    brew install ffmpeg        # or apt install ffmpeg fonts-dejavu-core
    pip install -r requirements.txt
    streamlit run app.py       # with no secrets set it opens straight in as admin

## Deploy (Streamlit Community Cloud)
1. Push this folder to a private GitHub repo, main file app.py. packages.txt installs ffmpeg and a font.
2. In Supabase (free account, new project) open SQL Editor and run supabase_setup.sql. It makes the records table and a private `ads` bucket.
3. Add secrets (see .streamlit/secrets.toml.example): APP_PASSWORD, SUPABASE_URL, SUPABASE_KEY (the secret key), plus a [logins] table for guests like Simon.
4. Press Admin > Test saving.

Without Supabase keys the app still works, but nothing is kept after a restart and the page says Saving is OFF.

## Sound
The screenshots page can add an original Japanese-style plucked-string music loop (made by the app, nothing to
license) and a dog bark on every new shot, or your own music and bark recording. The built-in bark is a simple
synthetic one, a real recording sounds better. Only upload music you have the rights to.

## AI animation (fal.ai)
Add `FAL_KEY` to the secrets and the screenshots page offers "AI animation": each screenshot is sent to an AI
image-to-video model (Kling by default, set in config.py) with a prompt that says to leave the board, tiles and
text alone and move only what you name (the dogs, leaves, snow). It shows an estimated cost and asks you to
confirm, guests have a daily limit, and clips are cached so repeating a shot is free. This has been tested only
against a fake server, so make the first real test cheap (2 shots) and check the model names and prices on fal.ai.

## Adding a different AI video service
(Older note.)
Screenshot motion is free (ffmpeg). To use an AI video service instead, write one function
`animate(image, motion, seconds, size, out_path)` that returns a finished clip and pass it to
`shotlib.build_montage(..., animate=your_function)`. Keep its API key in the Streamlit secrets.
Keep to real screenshots as the input so the ad shows what the game really looks like.

## Settings
Everything lives in config.py: themes, sizes, clip limits, guest daily allowance, opening line ideas.

## Tests
    python -m pytest tests

## Good to know
- Rendering is CPU work. A 20s clip takes about 30 to 60s on the free Streamlit tier.
- Emoji are removed from burned-in text (the font has none).
- Screenshot ads have no sound. Add music or a voiceover when you post.
- Without ANTHROPIC_API_KEY the script is a plain template (still editable).
- Next ideas: auto-captions from the game's audio, an App Store badge image, a music library, an AI video adapter.
