# Hookreel

Upload a screen recording of a game or app (iPhone or Mac), pick the best moment, add an opening line,
captions and an end card, and download a finished MP4 ad in vertical, portrait, square or landscape.

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

## Settings
Everything lives in config.py: themes, sizes, clip limits, guest daily allowance, opening line ideas.

## Tests
    python -m pytest tests

## Good to know
- Rendering is CPU work. A 20s clip takes about 30 to 60s on the free Streamlit tier.
- Emoji are removed from burned-in text (the font has none).
- Next ideas: auto-captions from the game's audio, multiple clips stitched together, an App Store badge image.
