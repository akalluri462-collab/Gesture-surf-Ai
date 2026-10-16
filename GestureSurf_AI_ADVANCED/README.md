# GestureSurf AI

Subway-Surfers-style endless runner controlled with your **hand** (MediaPipe + OpenCV) or keyboard. Built with Python and Pygame.

## Run
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Allow Camera permission for your Terminal / VS Code. Use Python 3.9-3.11 (mediapipe 0.10.14 requirement).
If the camera fails, the game still runs with keyboard.

## Controls
Hand: move left/right = lane, quick up = jump, quick down = slide, open palm = start/resume, fist = pause, two fingers = shield.
Keyboard: A/D or arrows = lane, W/Up/Space = jump, S/Down = slide, E/Q = shield, P = pause, Enter = confirm, M = camera, F = fullscreen, Esc = back.

## Gameplay
- Jump onto trains/buses to surf on the roof (coins + surf bonus).
- Barrier/sign or side of a train = stumble; inspector + dog chase for 8s. Trip again = caught. Train nose = instant crash.
- Pickups: coin magnet, 2x score, jetpack, super sneakers.
- Shield: +1 per 40 coins (max 3).
- Express trains, tunnels, day/dusk/night cycle, procedural sound effects.

## Architecture
| Folder | Purpose |
|---|---|
| `app/` | Screens, UI, main loop (`application.py`) |
| `game/` | Game engine (`engine.py`), synthesized sound (`sfx.py`) |
| `vision/` | Threaded hand tracker: time-window, hand-size-normalised gesture detection |
| `database/` | SQLite leaderboard (`ScoreDB`: add, top, stats) |
| `nlp/` | Voice-command intent parser (ready, not yet wired in) |
| `tests/` | Unit tests: `python -m unittest discover -s tests` |

## Tuning hand control
`HandTracker(sensitivity=1.25)` in `vision/hand_tracker.py`: raise for easier gestures, lower for fewer false triggers.

## Fixes in this version
Package layout matches imports; mediapipe pinned (new versions removed `mp.solutions`); camera preview colours (BGR to RGB); DB connections closed and errors contained; parser START/RESUME ordering; leaderboard uses OS username.
