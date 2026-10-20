"""Every setting for the Ad Maker in one place. No Streamlit in here."""

APP_TITLE = "Hookreel"
ADMIN_NAME = "Ben"            # the admin login is this name + APP_PASSWORD
GUEST_DAILY_RENDERS = 5       # ads a guest can make per day (admin is unlimited)

MAX_UPLOAD_MB = 500
MAX_CLIP_SECONDS = 60
MIN_CLIP_SECONDS = 5
DEFAULT_CLIP_SECONDS = 20
END_CARD_SECONDS = 3.0
HOOK_SECONDS = 3.0

# Output sizes (width, height)
ASPECTS = {
    "Vertical 9:16 (TikTok, Reels, Shorts)": (1080, 1920),
    "Portrait 4:5 (Instagram, Facebook feed)": (1080, 1350),
    "Square 1:1": (1080, 1080),
    "Landscape 16:9 (YouTube, X)": (1920, 1080),
}

# Colours are RRGGBB. hook_bg/hook_fg style the big opening line, cap_* the captions,
# bg/fg/accent the end card.
THEMES = {
    "Cosy autumn": dict(bg="2B1A10", fg="FFF4E0", accent="FFB02E", hook_bg="FFB02E", hook_fg="2B1A10", cap_bg="000000", cap_fg="FFFFFF"),
    "Night neon": dict(bg="0B0B1E", fg="FFFFFF", accent="19F2C4", hook_bg="19F2C4", hook_fg="0B0B1E", cap_bg="000000", cap_fg="FFFFFF"),
    "Clean light": dict(bg="F5F5F7", fg="111111", accent="0A84FF", hook_bg="FFFFFF", hook_fg="111111", cap_bg="111111", cap_fg="FFFFFF"),
    "Bold red": dict(bg="1A0505", fg="FFFFFF", accent="FF3B30", hook_bg="FF3B30", hook_fg="FFFFFF", cap_bg="000000", cap_fg="FFFFFF"),
}

# Opening-line ideas. {app} is replaced with the app name.
HOOK_TEMPLATES = [
    "Pop the tiles. The dogs do the rest.",
    "Wait for it...",
    "Why is {app} so addictive?",
    "Your new favourite way to unwind",
    "I can't stop playing {app}",
    "POV: you found the perfect cosy game",
    "This took me 3 tries",
    "{app} is out now",
]

DEFAULT_CTA = "Download now"
DEFAULT_BADGE = "Out now on the App Store"

# Fonts tried in order. packages.txt installs fonts-dejavu-core on Streamlit Cloud.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
