import math
import pygame
from game.engine import GameEngine
from vision.hand_tracker import HandTracker
from database.database import ScoreDB

BG = (10, 14, 28)
ACCENT = (255, 196, 40)
ACCENT2 = (60, 200, 255)
TEXT = (255, 255, 255)
SKY_TOP = (72, 160, 225)
SKY_BOTTOM = (200, 230, 248)
PANEL = (255, 255, 255)
PANEL_TEXT = (35, 45, 70)
GREEN = (90, 230, 140)
GOLD = (255, 210, 60)
SOFT = (170, 185, 215)

RENDER_W, RENDER_H = 1280, 720


def lerp(a, b, t):
    return a + (b - a) * t


class GestureSurfApp:
    def __init__(self):
        pygame.init()

        # SCALED | FULLSCREEN: self.screen stays a plain 1280x720 surface and
        # pygame scales it to the real display and maps the mouse back.
        self.fullscreen = True
        self.screen = pygame.display.set_mode(
            (RENDER_W, RENDER_H), pygame.SCALED | pygame.FULLSCREEN
        )
        pygame.display.set_caption("GestureSurf AI")
        self.clock = pygame.time.Clock()
        self.tiny = pygame.font.SysFont("arial", 14)
        self.small = pygame.font.SysFont("arial", 18)
        self.font = pygame.font.SysFont("arial", 22)
        self.med = pygame.font.SysFont("arial", 26, bold=True)
        self.big = pygame.font.SysFont("arial", 38, bold=True)
        self.h1 = pygame.font.SysFont("arial", 54, bold=True)
        self.title = pygame.font.SysFont("arial", 66, bold=True)

        self.db = ScoreDB()

        # Camera can legitimately be missing/blocked - never let that crash the app.
        self.tracker = None
        self.camera_error = None
        try:
            self.tracker = HandTracker()
        except Exception as ex:
            self.camera_error = str(ex)

        self.game = GameEngine()

        self.screen_name = "HOME"
        self.running = True
        self.camera_on = self.tracker is not None
        self.calibrated = False
        self.last_hand = "NO_HAND"
        self.last_event = "READY"
        self.camera_surface = None
        self.t = 0.0
        self.dt = 1 / 60
        self.clicked = False
        self.buttons = {}

        # UI state
        self.hover = {}                # per-button hover tween 0..1
        self._logo_cache = {}
        self._sky_surf = self._build_sky()
        self._fade = 0.0
        self._last_screen = None
        self._fade_surf = pygame.Surface((RENDER_W, RENDER_H))
        self._fade_surf.fill((6, 10, 22))
        self.best_before = 0
        self.new_best = False

    # ---------------------------------------------------------- display ----
    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        try:
            pygame.display.toggle_fullscreen()
        except pygame.error:
            flags = pygame.SCALED | (pygame.FULLSCREEN if self.fullscreen else 0)
            self.screen = pygame.display.set_mode((RENDER_W, RENDER_H), flags)

    def get_mouse_pos(self):
        return pygame.mouse.get_pos()

    def present(self):
        pygame.display.flip()

    # ---------------------------------------------------------- actions ----
    def toggle_camera(self):
        if self.tracker is not None:
            self.camera_on = not self.camera_on

    def start_run(self):
        self.calibrated = True
        self.game.reset()
        self.screen_name = "GAME"

    def dispatch(self, action):
        self.last_event = action

        if action == "QUIT":
            self.running = False
        elif action == "START":
            self.screen_name = "CALIBRATION"
        elif action == "PAUSE":
            if self.screen_name == "GAME":
                self.screen_name = "PAUSE"
        elif action == "RESUME":
            # OPEN_PALM = universal "confirm / go forward" gesture
            if self.screen_name == "HOME":
                self.screen_name = "CALIBRATION"
            elif self.screen_name == "CALIBRATION":
                self.start_run()
            elif self.screen_name == "PAUSE":
                self.screen_name = "GAME"
            elif self.screen_name == "GAMEOVER":
                self.start_run()
            elif self.screen_name in ("HOW", "SETTINGS", "LEADERBOARD"):
                self.screen_name = "HOME"
        elif action == "RESTART":
            self.game.reset()
            self.screen_name = "GAME"
        elif action in ("LEFT", "RIGHT", "JUMP", "SLIDE", "POWER"):
            if self.screen_name == "GAME":
                self.game.action(action)
        elif action == "HOW":
            self.screen_name = "HOW"
        elif action == "SETTINGS":
            self.screen_name = "SETTINGS"
        elif action == "LEADERBOARD":
            self.screen_name = "LEADERBOARD"
        elif action == "HOME":
            self.screen_name = "HOME"

    def process_camera(self):
        if not self.camera_on or self.tracker is None:
            return
        try:
            frame, info = self.tracker.read()
        except Exception:
            self.camera_on = False
            return
        self.camera_surface = frame
        if info:
            self.last_hand = info.get("gesture", "NO_HAND")
            if info.get("event"):
                self.dispatch(info["event"])

    # ------------------------------------------------------ draw helpers ---
    def draw_text(self, text, x, y, font=None, color=TEXT):
        self.screen.blit((font or self.font).render(text, True, color), (x, y))

    def draw_text_center(self, text, cx, y, font=None, color=TEXT):
        surf = (font or self.font).render(text, True, color)
        self.screen.blit(surf, surf.get_rect(midtop=(cx, y)))

    def draw_text_right(self, text, rx, y, font=None, color=TEXT):
        surf = (font or self.font).render(text, True, color)
        self.screen.blit(surf, surf.get_rect(topright=(rx, y)))

    def text_shadow(self, text, cx, y, font=None, color=(255, 255, 255)):
        f = font or self.big
        shadow = f.render(text, True, (20, 20, 30))
        shadow.set_alpha(150)
        self.screen.blit(shadow, shadow.get_rect(midtop=(cx + 3, y + 3)))
        surf = f.render(text, True, color)
        self.screen.blit(surf, surf.get_rect(midtop=(cx, y)))

    def panel(self, rect, color=(14, 20, 40, 215), radius=20, border=(255, 255, 255, 45), shadow=True):
        rect = pygame.Rect(rect)
        if shadow:
            sh = pygame.Surface((rect.w + 16, rect.h + 16), pygame.SRCALPHA)
            pygame.draw.rect(sh, (0, 0, 0, 60), sh.get_rect(), border_radius=radius + 6)
            self.screen.blit(sh, (rect.x - 8, rect.y - 2))
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), border_radius=radius)
        if border:
            pygame.draw.rect(s, border, s.get_rect(), 2, border_radius=radius)
        self.screen.blit(s, rect.topleft)

    def chip(self, x, y, text, on=True, font=None):
        """Small status pill with a coloured dot. Returns its width."""
        f = font or self.small
        surf = f.render(text, True, (235, 240, 250))
        w = surf.get_width() + 44
        self.panel((x, y, w, 34), (255, 255, 255, 28), 17, (255, 255, 255, 40), shadow=False)
        pygame.draw.circle(self.screen, GREEN if on else (240, 110, 100), (x + 18, y + 17), 6)
        self.screen.blit(surf, (x + 32, y + 17 - surf.get_height() // 2))
        return w

    def logo_surface(self, text, font, fill, outline):
        key = (text, id(font), fill, outline)
        if key not in self._logo_cache:
            base = font.render(text, True, fill)
            ol = font.render(text, True, outline)
            pad = 10
            surf = pygame.Surface((base.get_width() + pad * 2, base.get_height() + pad * 2), pygame.SRCALPHA)
            drop = font.render(text, True, (0, 0, 0))
            drop.set_alpha(80)
            surf.blit(drop, (pad + 5, pad + 6))
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx * dx + dy * dy <= 9:
                        surf.blit(ol, (pad + dx, pad + dy))
            surf.blit(base, (pad, pad))
            self._logo_cache[key] = surf
        return self._logo_cache[key]

    def game_logo(self, text, cx, y, font=None, fill=GOLD, outline=(200, 70, 30)):
        """Layered arcade-logo look (cached, so it costs one blit per frame)."""
        surf = self.logo_surface(text, font or self.title, fill, outline)
        self.screen.blit(surf, surf.get_rect(midtop=(cx, y)))

    def heading(self, text, y=36, sub=None):
        self.game_logo(text, 640, y, self.h1)
        if sub:
            self.text_shadow(sub, 640, y + 78, self.small, (255, 255, 255))

    def button(self, key, label, rect, sub=None, primary=True, hint=None):
        """Chunky pill button with hover lift and press feedback. True the frame it's clicked."""
        mouse = self.get_mouse_pos()
        hovered = rect.collidepoint(mouse)
        self.buttons[key] = rect

        h = self.hover.get(key, 0.0)
        h += ((1.0 if hovered else 0.0) - h) * min(1.0, self.dt * 14)
        self.hover[key] = h
        pressed = hovered and pygame.mouse.get_pressed()[0]

        top_col = (255, 150, 40) if primary else (60, 170, 235)
        bot_col = (215, 100, 15) if primary else (30, 130, 195)
        top_col = tuple(int(min(255, c + 30 * h)) for c in top_col)

        face = rect.move(0, int(-3 * h) + (4 if pressed else 0))
        depth = 4 if pressed else 7
        pygame.draw.rect(self.screen, bot_col, face.move(0, depth), border_radius=18)
        pygame.draw.rect(self.screen, top_col, face, border_radius=18)
        gloss = pygame.Rect(face.x + 6, face.y + 5, face.w - 12, face.h // 2 - 4)
        pygame.draw.rect(self.screen, tuple(min(255, c + 28) for c in top_col), gloss, border_radius=14)
        pygame.draw.rect(self.screen, (255, 255, 255), face, 3, border_radius=18)

        ty = face.centery - (11 if sub else 0)
        surf = self.med.render(label, True, (255, 255, 255))
        shadow_surf = self.med.render(label, True, (0, 0, 0))
        shadow_surf.set_alpha(70)
        self.screen.blit(shadow_surf, shadow_surf.get_rect(center=(face.centerx + 1, ty + 2)))
        self.screen.blit(surf, surf.get_rect(center=(face.centerx, ty)))
        if sub:
            s2 = self.small.render(sub, True, (255, 240, 220))
            self.screen.blit(s2, s2.get_rect(center=(face.centerx, face.centery + 16)))
        if hint:
            hs = self.tiny.render(hint, True, (255, 255, 255))
            hb = pygame.Rect(0, 0, hs.get_width() + 16, 22)
            hb.midright = (face.right - 14, face.centery)
            pygame.draw.rect(self.screen, bot_col, hb, border_radius=8)
            self.screen.blit(hs, hs.get_rect(center=hb.center))

        return hovered and self.clicked

    def toggle_row(self, key, label, sub, state, rect):
        """Settings-style row with an on/off switch. True the frame it's clicked."""
        mouse = self.get_mouse_pos()
        hovered = rect.collidepoint(mouse)
        self.buttons[key] = rect
        self.panel(rect, (14, 20, 40, 225 if hovered else 205), 18,
                   (255, 255, 255, 90 if hovered else 45))
        self.draw_text(label, rect.x + 26, rect.y + 14, self.med, (255, 255, 255))
        self.draw_text(sub, rect.x + 26, rect.y + 48, self.small, SOFT)
        sw = pygame.Rect(0, 0, 76, 38)
        sw.midright = (rect.right - 26, rect.centery)
        pygame.draw.rect(self.screen, GREEN if state else (90, 98, 120), sw, border_radius=19)
        kx = sw.right - 19 if state else sw.left + 19
        pygame.draw.circle(self.screen, (255, 255, 255), (kx, sw.centery), 15)
        return hovered and self.clicked

    def _build_sky(self):
        s = pygame.Surface((RENDER_W, RENDER_H))
        for y in range(RENDER_H):
            t = min(1.0, y / 480)
            col = tuple(int(lerp(SKY_TOP[i], SKY_BOTTOM[i], t)) for i in range(3))
            pygame.draw.line(s, col, (0, y), (RENDER_W, y))
        return s

    def menu_bg(self, horizon=430):
        """Animated backdrop shared by every menu: sky, clouds, parallax city, moving track."""
        self.screen.blit(self._sky_surf, (0, 0))
        pygame.draw.circle(self.screen, (255, 244, 200), (1110, 110), 52)
        pygame.draw.circle(self.screen, (255, 250, 225), (1110, 110), 72, 3)

        for i in range(4):
            cx = (200 + i * 320 + int(self.t * 14)) % 1500 - 110
            cy = 80 + (i % 2) * 46
            for dx, dy, rr in ((0, 0, 26), (24, -6, 20), (-22, -4, 20), (10, 8, 22)):
                pygame.draw.circle(self.screen, (255, 255, 255), (cx + dx, cy + dy), rr)

        # two skyline layers, heights tied to a building's index so they never jitter
        for speed, col, w, hmin, hspan, mult in (
            (10, (150, 176, 208), 110, 70, 90, 41),
            (26, (112, 140, 182), 84, 60, 130, 53),
        ):
            total = int(self.t * speed)
            base = total // w
            off = total % w
            for k in range(-1, RENDER_W // w + 3):
                gi = base + k
                h = hmin + (gi * mult) % hspan
                x = k * w - off
                pygame.draw.rect(self.screen, col, (x, horizon - h, w - 8, h + 4))

        pygame.draw.rect(self.screen, (168, 150, 120), (0, horizon, RENDER_W, RENDER_H - horizon))
        span = RENDER_H - horizon
        # rail bed
        pygame.draw.polygon(self.screen, (108, 96, 78),
                            [(180, RENDER_H), (1100, RENDER_H), (700, horizon), (580, horizon)])
        tie = (self.t * 150) % 46
        for y in range(horizon + 40, RENDER_H + 46, 46):
            yy = y - tie
            if yy < horizon:
                continue
            tt = (yy - horizon) / span
            pygame.draw.line(self.screen, (74, 58, 42), (580 - tt * 400, yy), (700 + tt * 400, yy), max(2, int(3 + tt * 8)))
        for i in range(4):
            fx = 580 + i * 40
            tx = 180 + i * 307
            pygame.draw.line(self.screen, (96, 88, 78), (fx, horizon), (tx, RENDER_H), 3)
        # soft haze at the horizon
        pygame.draw.line(self.screen, (214, 232, 244), (0, horizon), (RENDER_W, horizon), 2)

    def footer(self, text):
        self.draw_text_center(text, 640, 690, self.small, (30, 40, 70))

    # ---------------------------------------------------------- screens ----
    def home(self):
        self.menu_bg()
        bob = int(5 * math.sin(self.t * 2.2))
        self.game_logo("GESTURESURF AI", 640, 50 + bob, self.title)
        tag = "CONTROL THE RUN WITH YOUR HAND"
        tw = self.small.size(tag)[0] + 44
        self.panel((640 - tw // 2, 150, tw, 36), (14, 20, 40, 190), 18, shadow=False)
        self.draw_text_center(tag, 640, 156, self.small, (255, 255, 255))

        if self.button("start", "START RUN", pygame.Rect(450, 222, 380, 74), hint="ENTER"):
            self.dispatch("START")
        if self.button("how", "HOW TO PLAY", pygame.Rect(450, 322, 380, 56), primary=False):
            self.dispatch("HOW")
        if self.button("leaderboard", "LEADERBOARD", pygame.Rect(450, 394, 380, 56), primary=False):
            self.dispatch("LEADERBOARD")
        if self.button("settings", "SETTINGS", pygame.Rect(450, 466, 380, 56), primary=False):
            self.dispatch("SETTINGS")

        # best score badge, top-right
        try:
            top = self.db.top(1)
            best = int(top[0]["score"]) if top else 0
        except Exception:
            best = 0
        if best:
            self.panel((1280 - 232, 20, 212, 44), (14, 20, 40, 200), 22, shadow=False)
            self.draw_text("BEST", 1280 - 216, 31, self.tiny, SOFT)
            self.draw_text_right(f"{best}", 1280 - 36, 27, self.med, GOLD)

        # bottom status bar
        self.panel((0, 628, 1280, 92), (10, 14, 28, 235), 0, None, shadow=False)
        cam_txt = "Camera ON" if self.camera_on else ("Camera OFF" if self.tracker else "Camera unavailable")
        x = 28
        x += self.chip(x, 646, cam_txt, self.camera_on) + 12
        self.draw_text("Open palm / Enter = start     M camera     F fullscreen     Esc quit",
                       x + 12, 653, self.small, (200, 210, 230))
        if self.camera_error:
            self.draw_text(f"camera/mediapipe: {self.camera_error[:90]}", 30, 692, self.tiny, (255, 150, 150))

    def calibration(self):
        self.menu_bg()
        self.heading("CALIBRATION", 30, "Hold your hand up so the camera can see it - or just press Enter")

        ready = self.last_hand != "NO_HAND" and self.camera_on

        # camera card (left)
        card = pygame.Rect(120, 160, 520, 380)
        self.panel(card, (14, 20, 40, 230))
        shown = False
        if self.camera_surface is not None and self.camera_on:
            try:
                arr = self.camera_surface
                sw, sh = arr.shape[1], arr.shape[0]
                sc = min(488 / sw, 348 / sh)
                surf = pygame.surfarray.make_surface(arr.swapaxes(0, 1))
                surf = pygame.transform.scale(surf, (int(sw * sc), int(sh * sc)))
                self.screen.blit(surf, surf.get_rect(center=card.center))
                shown = True
            except Exception:
                pass
        if not shown:
            self.draw_text_center("No camera feed", card.centerx, card.centery - 26, self.big, SOFT)
            self.draw_text_center("Keyboard controls still work", card.centerx, card.centery + 22, self.small, SOFT)
        pygame.draw.rect(self.screen, GREEN if ready else ACCENT2, card, 3, border_radius=20)

        # status card (right)
        st = pygame.Rect(670, 160, 490, 380)
        self.panel(st, (14, 20, 40, 230))
        self.draw_text("HAND DETECTION", st.x + 30, st.y + 26, self.tiny, SOFT)
        self.draw_text(self.last_hand.replace("_", " "), st.x + 30, st.y + 46, self.big, GREEN if ready else ACCENT)
        self.draw_text("TRACKING", st.x + 30, st.y + 110, self.tiny, SOFT)
        self.draw_text("READY" if ready else "WAITING (keyboard OK)", st.x + 30, st.y + 130, self.med,
                       GREEN if ready else (255, 235, 150))
        pygame.draw.line(self.screen, (255, 255, 255), (st.x + 30, st.y + 190), (st.right - 30, st.y + 190), 1)
        tips = ["Keep your hand in the middle of the frame",
                "Good lighting helps tracking a lot",
                "Move hand left/right to change lanes",
                "Show an open palm to start the run"]
        for i, tip in enumerate(tips):
            pygame.draw.circle(self.screen, ACCENT, (st.x + 38, st.y + 224 + i * 34), 5)
            self.draw_text(tip, st.x + 56, st.y + 213 + i * 34, self.small, (225, 232, 245))

        if self.button("continue", "CONTINUE", pygame.Rect(440, 566, 400, 62), hint="ENTER"):
            self.start_run()
        if self.button("skip_home", "BACK", pygame.Rect(440, 640, 400, 46), primary=False, hint="ESC"):
            self.screen_name = "HOME"

    def how(self):
        self.menu_bg()
        self.heading("HOW TO PLAY", 28)
        cols = (150, 480, 820)
        panel = pygame.Rect(120, 140, 1040, 450)
        self.panel(panel, (14, 20, 40, 228))
        for x, name in zip(cols, ("ACTION", "GESTURE", "KEYBOARD")):
            self.draw_text(name, x, 156, self.tiny, SOFT)
        rows = [
            ("Change lane", "Move hand left / right", "A / D   or   Left / Right", (255, 205, 60)),
            ("Jump", "Quick hand UP", "W / Up / Space", (110, 220, 255)),
            ("Slide", "Quick hand DOWN", "S / Down", (120, 230, 150)),
            ("Shield", "Two fingers", "Not on keyboard", (170, 160, 255)),
            ("Pause", "Fist", "P / Esc", (255, 150, 120)),
            ("Start / resume", "Open palm", "Enter", (255, 205, 60)),
            ("Obstacles", "Jump trains + barriers, slide barriers,", "dodge signs - collect coins", (255, 255, 255)),
        ]
        for i, (a, b, c, col) in enumerate(rows):
            y = 184 + i * 56
            if i % 2 == 0:
                s = pygame.Surface((1000, 48), pygame.SRCALPHA)
                pygame.draw.rect(s, (255, 255, 255, 14), s.get_rect(), border_radius=12)
                self.screen.blit(s, (140, y - 6))
            pygame.draw.circle(self.screen, col, (cols[0] - 4, y + 16), 6)
            self.draw_text(a, cols[0] + 12, y + 4, self.font, col)
            self.draw_text(b, cols[1], y + 4, self.font, (255, 255, 255))
            self.draw_text(c, cols[2], y + 4, self.small, (205, 215, 235))
        if self.button("back_how", "BACK", pygame.Rect(440, 618, 400, 56), primary=False, hint="ESC"):
            self.screen_name = "HOME"

    def settings(self):
        self.menu_bg()
        self.heading("SETTINGS", 40)
        cam_sub = "Click or press M" if self.tracker else "Unavailable - check permissions / mediapipe"
        if self.toggle_row("toggle_cam", "Hand camera", cam_sub, self.camera_on, pygame.Rect(360, 180, 560, 86)):
            self.toggle_camera()
        if self.toggle_row("toggle_fs", "Fullscreen", "Click or press F / F11", self.fullscreen,
                           pygame.Rect(360, 286, 560, 86)):
            self.toggle_fullscreen()
        if self.button("back_settings", "BACK", pygame.Rect(440, 410, 400, 56), primary=False, hint="ESC"):
            self.screen_name = "HOME"

    def leaderboard(self):
        self.menu_bg()
        self.heading("LEADERBOARD", 28)
        panel = pygame.Rect(240, 130, 800, 460)
        self.panel(panel, (14, 20, 40, 228))
        try:
            scores = self.db.top(8)
        except Exception:
            scores = []
        if not scores:
            self.draw_text_center("No runs saved yet", 640, 300, self.big, (255, 255, 255))
            self.draw_text_center("Finish a run to set your first score!", 640, 352, self.font, SOFT)
        else:
            for x, name in ((300, "RANK"), (400, "PLAYER"), (680, "SCORE"), (860, "COINS")):
                self.draw_text(name, x, 146, self.tiny, SOFT)
            medals = [(255, 210, 60), (200, 208, 220), (205, 140, 80)]
            for i, row in enumerate(scores):
                y = 172 + i * 50
                top = i == 0
                bg = (255, 210, 60, 235) if top else ((255, 255, 255, 16) if i % 2 == 0 else (255, 255, 255, 6))
                s = pygame.Surface((760, 42), pygame.SRCALPHA)
                pygame.draw.rect(s, bg, s.get_rect(), border_radius=12)
                self.screen.blit(s, (260, y))
                col = (40, 30, 10) if top else (255, 255, 255)
                cy = y + 21
                if i < 3:
                    pygame.draw.circle(self.screen, medals[i], (322, cy), 15)
                    pygame.draw.circle(self.screen, (40, 30, 10) if top else (255, 255, 255), (322, cy), 15, 2)
                    rs = self.small.render(str(i + 1), True, (40, 30, 10))
                    self.screen.blit(rs, rs.get_rect(center=(322, cy)))
                else:
                    self.draw_text(f"{i + 1}", 316, y + 9, self.font, col)
                self.draw_text(str(row["name"]), 400, y + 9, self.font, col)
                self.draw_text(str(int(row["score"])), 680, y + 9, self.font, col)
                self.draw_text(f"{row['coins']}", 860, y + 9, self.font, col)
        if self.button("back_lb", "BACK", pygame.Rect(440, 618, 400, 56), primary=False, hint="ESC"):
            self.screen_name = "HOME"

    def _dim_game(self, alpha):
        self.game.draw(self.screen, self.camera_surface, self.last_hand, self.last_event)
        overlay = pygame.Surface((RENDER_W, RENDER_H), pygame.SRCALPHA)
        overlay.fill((6, 10, 24, alpha))
        self.screen.blit(overlay, (0, 0))

    def _stat_row(self, label, value, y, color, x0=420, x1=860):
        self.draw_text(label, x0, y + 8, self.small, SOFT)
        self.draw_text_right(value, x1, y, self.big, color)

    def pause(self):
        self._dim_game(170)
        card = pygame.Rect(400, 130, 480, 460)
        self.panel(card, (14, 20, 40, 240))
        self.game_logo("PAUSED", 640, 146, self.h1)
        level = getattr(self.game, "level", 1)
        self._stat_row("SCORE", str(int(self.game.score)), 246, GOLD)
        self._stat_row("COINS", str(self.game.coins), 296, (120, 220, 255))
        self._stat_row("LEVEL", str(level), 346, (255, 255, 255))
        if self.button("resume_btn", "RESUME", pygame.Rect(440, 420, 400, 62), hint="ENTER"):
            self.screen_name = "GAME"
        if self.button("quit_to_home", "QUIT TO MENU", pygame.Rect(440, 500, 400, 52), primary=False, hint="ESC"):
            self.screen_name = "HOME"

    def gameover(self):
        self._dim_game(185)
        card = pygame.Rect(370, 70, 540, 590)
        self.panel(card, (14, 20, 40, 242))
        self.game_logo("RUN COMPLETE", 640, 86, self.h1)

        if self.new_best:
            pulse = 1 + 0.04 * math.sin(self.t * 6)
            bw, bh = int(220 * pulse), int(38 * pulse)
            badge = pygame.Rect(0, 0, bw, bh)
            badge.center = (640, 188)
            pygame.draw.rect(self.screen, GOLD, badge, border_radius=19)
            self.draw_text_center("NEW BEST!", 640, badge.y + 6, self.font, (60, 40, 5))
        else:
            self.draw_text_center(f"Best  {self.best_before}", 640, 178, self.font, SOFT)

        level = getattr(self.game, "level", 1)
        self._stat_row("SCORE", str(int(self.game.score)), 238, GOLD, 430, 850)
        self._stat_row("COINS", str(self.game.coins), 292, (120, 220, 255), 430, 850)
        self._stat_row("DISTANCE", f"{int(self.game.distance)} m", 346, (255, 255, 255), 430, 850)
        self._stat_row("LEVEL", str(level), 400, (255, 160, 120), 430, 850)

        if self.button("again", "PLAY AGAIN", pygame.Rect(440, 480, 400, 64), hint="ENTER"):
            self.start_run()
        if self.button("menu", "MAIN MENU", pygame.Rect(440, 562, 400, 54), primary=False, hint="ESC"):
            self.screen_name = "HOME"

    # ------------------------------------------------------------- loop ----
    def run(self):
        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self.dt = dt
            self.t += dt
            self.clicked = False

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.clicked = True
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        # contextual back: only quits from HOME
                        if self.screen_name == "HOME":
                            self.running = False
                        elif self.screen_name in ("HOW", "SETTINGS", "LEADERBOARD", "CALIBRATION", "GAMEOVER", "PAUSE"):
                            self.screen_name = "HOME"
                        elif self.screen_name == "GAME":
                            self.screen_name = "PAUSE"
                    elif e.key == pygame.K_RETURN:
                        if self.screen_name == "HOME":
                            self.screen_name = "CALIBRATION"
                        elif self.screen_name == "CALIBRATION":
                            self.start_run()
                        elif self.screen_name in ("HOW", "SETTINGS", "LEADERBOARD"):
                            self.screen_name = "HOME"
                        elif self.screen_name == "PAUSE":
                            self.screen_name = "GAME"
                        elif self.screen_name == "GAMEOVER":
                            self.start_run()
                    elif e.key in (pygame.K_LEFT, pygame.K_a):
                        self.dispatch("LEFT")
                    elif e.key in (pygame.K_RIGHT, pygame.K_d):
                        self.dispatch("RIGHT")
                    elif e.key in (pygame.K_UP, pygame.K_w, pygame.K_SPACE):
                        self.dispatch("JUMP")
                    elif e.key in (pygame.K_DOWN, pygame.K_s):
                        self.dispatch("SLIDE")
                    elif e.key == pygame.K_p:
                        self.dispatch("PAUSE")
                    elif e.key == pygame.K_m:
                        self.toggle_camera()
                    elif e.key in (pygame.K_f, pygame.K_F11):
                        self.toggle_fullscreen()

            self.process_camera()

            if self.screen_name == "HOME":
                self.home()
            elif self.screen_name == "CALIBRATION":
                self.calibration()
            elif self.screen_name == "HOW":
                self.how()
            elif self.screen_name == "SETTINGS":
                self.settings()
            elif self.screen_name == "LEADERBOARD":
                self.leaderboard()
            elif self.screen_name == "GAME":
                self.game.update(dt)
                self.game.draw(self.screen, self.camera_surface, self.last_hand, self.last_event)
                if self.clicked and getattr(self.game, "pause_button_rect", None):
                    if self.game.pause_button_rect.collidepoint(self.get_mouse_pos()):
                        self.screen_name = "PAUSE"
                if self.game.game_over:
                    try:
                        top = self.db.top(1)
                        self.best_before = int(top[0]["score"]) if top else 0
                    except Exception:
                        self.best_before = 0
                    self.new_best = int(self.game.score) > self.best_before
                    self.db.add("Player", self.game.score, self.game.coins)
                    self.screen_name = "GAMEOVER"
            elif self.screen_name == "PAUSE":
                self.pause()
            elif self.screen_name == "GAMEOVER":
                self.gameover()

            # quick fade-in whenever the screen changes (not for GAME <-> PAUSE)
            if self.screen_name != self._last_screen:
                if {self._last_screen, self.screen_name} != {"GAME", "PAUSE"}:
                    self._fade = 1.0
                self._last_screen = self.screen_name
            if self._fade > 0:
                self._fade_surf.set_alpha(int(255 * self._fade))
                self.screen.blit(self._fade_surf, (0, 0))
                self._fade = max(0.0, self._fade - dt * 5)

            self.present()

        if self.tracker:
            self.tracker.release()
        pygame.quit()
