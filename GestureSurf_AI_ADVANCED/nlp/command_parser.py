import re

# Order matters: more specific intents first.
PATTERNS = {
    "START": [r"\bstart game\b", r"\bnew run\b"],
    "RESTART": [r"\brestart\b", r"\breset\b", r"\bnew game\b"],
    "PAUSE": [r"\bpause\b", r"\bhold on\b", r"\bwait\b"],
    "RESUME": [r"\bresume\b", r"\bcontinue\b", r"\bstart\b", r"\bplay\b"],
    "LEFT": [r"\bleft\b"],
    "RIGHT": [r"\bright\b"],
    "JUMP": [r"\bjump\b", r"\bup\b"],
    "SLIDE": [r"\bslide\b", r"\bdown\b", r"\bduck\b"],
    "POWER": [r"\bshield\b", r"\bpower\b", r"\bboost\b"],
    "HOW": [r"\bhow to play\b", r"\binstructions\b"],
    "SETTINGS": [r"\bsettings\b", r"\boptions\b"],
    "LEADERBOARD": [r"\bleaderboard\b", r"\bhigh score\b"],
    "QUIT": [r"\bquit\b", r"\bexit\b", r"\bstop game\b"],
}


def parse_command(text):
    text = (text or "").lower().strip()
    for intent, patterns in PATTERNS.items():
        for p in patterns:
            if re.search(p, text):
                return {"intent": intent, "text": text, "confidence": .94}
    return {"intent": "UNKNOWN", "text": text, "confidence": .05}
