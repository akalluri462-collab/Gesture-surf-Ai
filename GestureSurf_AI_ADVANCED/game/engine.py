import random
import math
import pygame

try:
    from game.sfx import Sfx
except Exception:          # sound is optional
    class Sfx:
        def play(self, *a, **k):
            pass

W, H = 1280, 720

# ------------------------------------------------------------ projection ----
# One tiny "3D" model: depth z runs 1.0 (horizon) -> 0.0 (where the player
# stands) -> negative (behind the camera). Everything on screen is derived
# from t_of(z), so tracks, trains, buildings and tunnels all line up.
HORIZON = 330
PLAYER_Y = 650
SPAN = 390.0
CX = 640
T_P = (PLAYER_Y - HORIZON) / SPAN
Z_NEAR = -0.24
PZ = 0.0


def t_of(z):
    return T_P * (1.0 - z)


def lw_of(t):            # lane width in px at depth-fraction t
    return 40.0 + 233.0 * t


def s_of(t):             # scale relative to the player's depth
    return (40.0 + 233.0 * t) / 231.2


def y_of(t):
    return HORIZON + SPAN * t


def lane_x(lane, t):
    return CX + (lane - 1) * lw_of(t)


def clamp(v, a=0.0, b=1.0):
    return a if v < a else b if v > b else v


def mix(a, b, k):
    k = clamp(k)
    return (int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k), int(a[2] + (b[2] - a[2]) * k))


def shade(c, f):
    return (int(clamp(c[0] * f, 0, 255)), int(clamp(c[1] * f, 0, 255)), int(clamp(c[2] * f, 0, 255)))


def lerp(a, b, t):
    return a + (b - a) * t


def hsh(i, salt=0):
    n = (i * 374761393 + salt * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    n ^= n >> 16
    return (n & 0xFFFF) / 65535.0


COIN_GOLD = (255, 205, 55)
COIN_LIGHT = (255, 236, 150)
RAIL = (96, 88, 78)
TRAIN_COLORS = [(250, 190, 40), (232, 72, 62), (56, 168, 110), (64, 126, 222), (240, 120, 40), (150, 90, 210)]
BUS_COLORS = [(255, 200, 40), (60, 150, 230), (235, 90, 70), (70, 190, 150)]
BUILD_COLORS = [(196, 120, 98), (150, 176, 206), (226, 206, 160), (128, 148, 186), (206, 150, 170), (150, 190, 170)]

SKY_KEYS = [
    ((94, 178, 235), (196, 227, 245), 0.0),     # day
    ((232, 120, 100), (255, 208, 150), 0.18),   # dusk
    ((14, 20, 60), (70, 88, 142), 0.55),        # night
]

# --------------------------------------------------------------- tuning ----
START_SPEED = 0.0028
MAX_SPEED = 0.0070
RAMP_TIME = 150.0
WARMUP_TIME = 8.0
FIRST_SPAWN_DELAY = 2.2
GAP_MIN = 0.55            # clear space AFTER the longest thing in a wave (z units)
GAP_MAX = 0.85
MIN_GAP_SEC = 3.0
LEVEL_SECONDS = 45
DAY_SECONDS = 70.0        # length of each day->dusk->night phase

# gameplay heights, in px at the player's depth
TRAIN_H = 140
BUS_H = 108
BARRIER_LOW = 52
BARRIER_TOP = 94
STAND_H = 90
SLIDE_H = 48
STEP = 26                 # forgiveness when landing on a roof
GRAV = 1.05
JUMP_V = 20.5
DIVE_V = -24.0
HALF = 0.40               # half width of a vehicle, in lane widths
THICK = 0.03
NOSE_PRE = 0.008          # vehicles: fatal zone starts this far before the nose (was 0.03)
HIT_HALF = 0.02           # barrier/sign: hit zone = +-this around where it is DRAWN (was z-0.03..z+0.05)
HIT_W = 0.38              # sideways hitbox in lane widths (was 0.46) - corner clips no longer count

# --- forgiveness (gesture control has latency, so the game is generous) ---
MANTLE = 86               # falling: how far below the roof edge still counts as landing on it
MANTLE_UP = 140           # rising: even more forgiving (you jumped, the train is coming)
MANTLE_SPEED = 15.0       # px/frame the character climbs onto a roof
SIDE_ZONE = 0.05          # beyond this depth into a vehicle = you hit its SIDE, not its nose
LATE_GRACE = 0.12         # a jump pressed up to this long AFTER the nose touches still saves you
JUMP_GRACE = 1.35         # after a jump, a train/bus nose arriving within this time is climbed, not crashed into
BUFFER = 0.20             # seconds a jump/slide press is remembered before landing
COYOTE = 0.12             # seconds you can still jump after leaving a roof/ground
DIVE_DELAY = 0.32         # dive-down is ignored right after a jump (stops accidental dives)
BOOT_K = 1.28             # super sneakers jump multiplier
JET_H = 215

# --- power-ups & chase ---
SHIELD_TIME = 5.0
CHASE_TIME = 8.0
JET_TIME = 6.0
MAG_TIME = 9.0
X2_TIME = 12.0
BOOT_TIME = 10.0
PU_COLORS = {"magnet": (226, 70, 84), "x2": (250, 170, 40), "jet": (70, 160, 255), "boots": (110, 205, 96)}
PU_NAMES = {"magnet": "COIN MAGNET", "x2": "2X SCORE", "jet": "JETPACK", "boots": "SUPER SNEAKERS"}

TUN_H = 400
TUN_HALF = 1.95
TUN_RING = 0.2


class Player:
    def __init__(self):
        self.lane = 1.0
        self.target = 1
        self.prev = 1             # lane we came from (used to bounce back on a side bump)
        self.h = 0.0              # height above the ground (px), up is positive
        self.vy = 0.0
        self.support = 0.0        # height of whatever is under the feet
        self.slide = 0.0
        self.shield = 0.0
        self.stride = 0.0
        self.landed = False
        self.lean = 0.0
        self.jump_buf = 0.0
        self.slide_buf = 0.0
        self.coyote = 0.0
        self.since_jump = 9.0
        self.boots = 0.0
        self.flying = False
        self.stumble = 0.0
        self.bump = 0.0
        self.inv = 0.0            # blink invulnerability after a stumble
        self.ghost = 0.0          # full invulnerability (after jetpack)

    @property
    def jump(self):           # old API: negative while airborne
        return -self.h

    @property
    def x(self):
        return int(lane_x(self.lane, T_P))

    def grounded(self):
        return self.h <= self.support + 0.6 and self.vy <= 0

    def left(self):
        if self.target > 0:
            self.prev = self.target
            self.target -= 1

    def right(self):
        if self.target < 2:
            self.prev = self.target
            self.target += 1

    def do_jump(self):
        """True if the jump started now. Otherwise it is buffered for a moment."""
        if self.flying:
            return False
        if self.grounded() or self.coyote > 0:
            self.vy = JUMP_V * (BOOT_K if self.boots > 0 else 1.0)
            self.slide = 0.0
            self.coyote = 0.0
            self.jump_buf = 0.0
            self.since_jump = 0.0
            return True
        self.jump_buf = BUFFER
        return False

    def do_slide(self):
        if self.flying:
            return
        if self.grounded():
            self.slide = 1.0
        elif self.vy < 3 and self.since_jump > DIVE_DELAY:
            self.vy = min(self.vy, DIVE_V)         # dive back down fast
        else:
            self.slide_buf = BUFFER                # too early to dive: remember it

    def update(self, k, support, ceil=None, fly=None):
        dt = k / 60.0
        old = self.lane
        self.lane += (self.target - self.lane) * min(1.0, 0.11 * k)
        self.lean = clamp((self.lane - old) * 14 / max(k, .1), -1, 1)
        self.slide = max(0, self.slide - dt)
        self.shield = max(0, self.shield - dt)
        self.boots = max(0, self.boots - dt)
        self.inv = max(0, self.inv - dt)
        self.ghost = max(0, self.ghost - dt)
        self.stumble = max(0, self.stumble - dt)
        self.bump = max(0, self.bump - dt)
        self.jump_buf = max(0, self.jump_buf - dt)
        self.slide_buf = max(0, self.slide_buf - dt)
        self.since_jump += dt
        self.stride += k * 0.35
        self.landed = False
        self.support = support

        if fly is not None:                       # jetpack
            self.flying = True
            self.h += (fly - self.h) * min(1.0, 0.1 * k)
            self.vy = 0.0
            self.slide = 0.0
            return
        self.flying = False

        if self.vy > 0 or self.h > support + 0.01:
            self.h += self.vy * k
            self.vy -= GRAV * k
            if ceil is not None and self.h > ceil:
                self.h = ceil
                self.vy = min(self.vy, 0)
            if self.h <= support and self.vy <= 0:
                self.h = support
                self.vy = 0
                self.landed = True
        else:
            if self.h < support - 0.01:           # mantle: climb smoothly onto the roof
                self.h = min(support, self.h + MANTLE_SPEED * k)
            else:
                self.h = support
            self.vy = 0

        if self.grounded():
            self.coyote = COYOTE
            if self.jump_buf > 0:                 # buffered jump: bunny-hop on landing
                self.do_jump()
            elif self.slide_buf > 0 and self.slide <= 0:
                self.slide = 1.0
                self.slide_buf = 0.0
        else:
            self.coyote = max(0.0, self.coyote - dt)

    def rect(self):
        bh = SLIDE_H if self.slide > 0 else STAND_H
        return pygame.Rect(int(self.x - 28), int(PLAYER_Y - self.h - bh), 56, bh)


class Obj:
    __slots__ = ("lane", "kind", "z", "length", "h", "hit", "dead", "color", "accent", "var",
                 "ptype", "vel", "ridden")

    def __init__(self, lane, kind, z=1.0, length=0.05, h=0.0, ptype=None, vel=0.0):
        self.lane = lane
        self.kind = kind
        self.z = z
        self.length = length
        self.h = h
        self.hit = False
        self.dead = False
        self.ridden = False
        self.ptype = ptype
        self.vel = vel            # extra forward speed (moving trains), 0 = standing
        self.var = random.random()
        if kind == "bus":
            self.color = random.choice(BUS_COLORS)
        elif vel > 0:
            self.color = random.choice([(58, 88, 170), (40, 58, 112), (176, 52, 60)])
        else:
            self.color = random.choice(TRAIN_COLORS)
        self.accent = random.choice([(255, 255, 255), (30, 34, 48), (250, 215, 70)])

    @property
    def roof(self):
        return TRAIN_H if self.kind == "train" else BUS_H if self.kind == "bus" else 0


class Tunnel:
    def __init__(self, zs, length):
        self.zs = zs
        self.length = length
        self.entered = False

    @property
    def ze(self):
        return self.zs + self.length


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "color")

    def __init__(self, x, y, vx, vy, life, color):
        self.x, self.y, self.vx, self.vy, self.life, self.color = x, y, vx, vy, life, color


class GameEngine:
    def __init__(self):
        self._fonts = {}
        self._haze = pygame.Surface((W, 40), pygame.SRCALPHA)
        self._fogs = pygame.Surface((W, 90), pygame.SRCALPHA)
        self._ov = pygame.Surface((W, H), pygame.SRCALPHA)
        self._vig = self._make_vignette()
        rnd = random.Random(1234)
        self._gravel = [(rnd.randint(0, W), rnd.randint(0, 380)) for _ in range(160)]
        self._stars = [(rnd.randint(0, W), rnd.randint(0, 260), rnd.random()) for _ in range(70)]
        self.pause_button_rect = pygame.Rect(W - 66, 18, 48, 48)
        self.sfx = Sfx()
        self._cloud_cache, self._dot_cache, self._glass_cache, self._text_cache = {}, {}, {}, {}
        self._bar_grad = None
        self._cam_src = None
        self._cam_surf = None
        self._skyg = pygame.Surface((W, 330))
        self._warn = self._make_warn()
        self._glow_sun = self._make_glow((255, 214, 150), 150, 95)
        self.reset()

    # ---------------------------------------------------------------- state --
    def reset(self):
        self.nose_timer = 0.0
        self.player = Player()
        self.objects = []
        self.tunnels = []
        self.particles = []
        self.score = 0
        self.coins = 0
        self.distance = 0
        self.elapsed = 0.0
        self.scroll = 0.0
        self.travel = 0.0           # total depth travelled; drives scenery
        self.progress = 0.0
        self.level = 1
        self.speed = START_SPEED * 0.75
        self.spawn_dist = FIRST_SPAWN_DELAY * START_SPEED * 0.75 * 60
        self.game_over = False
        self.started = True
        self.shake = 0.0
        self.popups = []
        self.banner = None
        self.tunnel_next = 20.0
        self.in_tunnel = False
        self.tun_dark = 0.0
        self.on_roof = False
        self.surf_time = 0.0
        self.dark = 0.0
        self.env_top = SKY_KEYS[0][0]
        self.env_bot = SKY_KEYS[0][1]
        self.mult = 1
        self.mult_t = 0.0
        self.mag = 0.0
        self.jet = 0.0
        self.chase = 0.0
        self.chase_k = 0.0
        self.charges = 1
        self.next_pu = 14.0

    def action(self, a):
        p = self.player
        if a == "LEFT" or a == "RIGHT":
            before = p.target
            if a == "LEFT":
                p.left()
            else:
                p.right()
            if p.target != before:
                self.sfx.play("lane")
        elif a == "JUMP":
            if p.do_jump():
                self.sfx.play("jump")
                self._puff(p.x, PLAYER_Y - p.support, (220, 210, 190), 6)
        elif a == "SLIDE":
            was = p.grounded()
            p.do_slide()
            if was:
                self.sfx.play("slide")
        elif a == "POWER":
            if self.charges > 0 and p.shield <= 0:
                self.charges -= 1
                p.shield = SHIELD_TIME
                self.sfx.play("power")
                self._popup("SHIELD ON", p.x, p.rect().top - 20)

    # --------------------------------------------------------------- update --
    def update(self, dt=1 / 60):
        # Split a long (laggy) frame into <=1/60s steps so collisions, jumps and
        # landings behave exactly the same at 20fps as at 60fps.
        dt = max(1 / 240, min(0.05, dt))
        n = max(1, int(math.ceil(dt * 60 - 0.05)))
        for _ in range(n):
            if self.game_over:
                return
            self._update_step(dt / n)

    def _update_step(self, dt):
        if self.game_over:
            return
        k = max(0.1, min(3.0, dt * 60))
        self.elapsed += dt
        t = self.elapsed
        self.progress = 1 - math.exp(-t / RAMP_TIME)
        warm = 0.75 + 0.25 * min(1.0, t / WARMUP_TIME)
        self.speed = lerp(START_SPEED, MAX_SPEED, self.progress) * warm
        if self.jet > 0:
            self.speed *= 1.4                      # jetpack = fast forward
        speed_k = self.speed * k

        self.mult = 2 if self.mult_t > 0 else 1
        self.distance += speed_k * 46
        self.scroll += speed_k * 320
        self.travel += speed_k
        self.score += k * (0.6 + self.progress) * self.mult
        self.shake = max(0.0, self.shake - dt * 4)

        # timers
        self.mag = max(0.0, self.mag - dt)
        self.mult_t = max(0.0, self.mult_t - dt)
        if self.jet > 0:
            self.jet -= dt
            if self.jet <= 0:
                self.jet = 0.0
                self.player.ghost = 1.3
                self.banner = ("JETPACK OVER", 1.0)
        if self.chase > 0:
            self.chase -= dt
            if self.chase <= 0:
                self.chase = 0.0
                self._popup("ESCAPED!", self.player.x, self.player.rect().top - 40)
        self.chase_k += ((1.0 if self.chase > 0 else 0.0) - self.chase_k) * min(1.0, dt * 3.5)

        new_level = 1 + int(t // LEVEL_SECONDS)
        if new_level > self.level:
            self.level = new_level
            self.banner = (f"SPEED UP!  LEVEL {self.level}", 1.8)
        if self.banner:
            txt, life = self.banner
            life -= dt
            self.banner = (txt, life) if life > 0 else None

        # tunnels: one at a time, every ~half a minute
        if not self.tunnels and self.elapsed >= self.tunnel_next:
            self.tunnels.append(Tunnel(1.25, random.uniform(2.4, 3.4)))
        for tn in self.tunnels:
            tn.zs -= speed_k
        if self.tunnels and self.tunnels[0].ze < Z_NEAR - 0.1:
            self.tunnels.pop(0)
            self.tunnel_next = self.elapsed + random.uniform(24, 36)

        self.spawn_dist -= speed_k
        if self.spawn_dist <= 0:
            self._spawn_wave()
        for o in self.objects:
            o.z -= speed_k * (1.0 + o.vel)

        if self.mag > 0:                           # coin magnet
            p = self.player
            f = min(1.0, 0.16 * k)
            for o in self.objects:
                if o.kind == "coin" and not o.hit and -0.08 < o.z < 0.45:
                    o.lane += (p.lane - o.lane) * f
                    o.h += ((p.h + 30) - o.h) * f
                    o.z -= speed_k * 0.8

        self._step_player(k, dt)

        self.objects = [o for o in self.objects
                        if not o.dead and o.z + o.length > Z_NEAR - 0.1
                        and not (o.kind in ("coin", "pu") and o.hit)]

        was = self.in_tunnel
        self.in_tunnel = any(tn.zs <= PZ + 0.02 <= tn.ze for tn in self.tunnels)
        if self.in_tunnel and not was:
            self.banner = ("TUNNEL!", 1.4)
        self.tun_dark += ((1.0 if self.in_tunnel else 0.0) - self.tun_dark) * min(1.0, dt * 4)

        for q in self.particles:
            q.x += q.vx * k
            q.y += q.vy * k
            q.vy += 0.4 * k
            q.life -= dt
        self.particles = [q for q in self.particles if q.life > 0]
        self.popups = [(tx, x, y - k * 0.6, life - dt) for (tx, x, y, life) in self.popups if life - dt > 0]

    def _step_player(self, k, dt):
        p = self.player
        flying = self.jet > 0
        support = 0.0
        rider = None
        fatal = soft = bump = None
        bh_now = SLIDE_H if p.slide > 0 else STAND_H
        for o in self.objects:
            if o.dead:
                continue
            o.ridden = False
            zf, zr = o.z, o.z + o.length
            if o.kind in ("coin", "pu"):
                if (not o.hit and abs(o.z - PZ) < 0.06 and abs(p.lane - o.lane) < 0.62):
                    ch = o.h + 18
                    if ch + 18 >= p.h and ch - 18 <= p.h + bh_now:
                        o.hit = True
                        if o.kind == "coin":
                            self._pick_coin(o)
                        else:
                            self._pick_power(o)
                continue
            if flying:
                continue
            if o.kind in ("barrier", "sign"):          # thin objects: hit only while they are really at the player
                if abs(zf - PZ) > HIT_HALF:
                    continue
            elif not (zf - NOSE_PRE <= PZ <= zr):
                continue
            dl = abs(p.lane - o.lane)
            roof = o.roof
            if roof:
                recent_jump = p.since_jump < JUMP_GRACE
                reach = MANTLE_UP if (p.vy > 0 or recent_jump) else MANTLE
                if dl < 0.58 and p.h >= roof - reach:
                    if roof >= support:
                        support = roof                 # standing on the roof
                        rider = o
                elif dl < HIT_W:
                    lateral = abs(p.target - p.lane) > 0.08
                    if lateral or PZ > zf + SIDE_ZONE:
                        bump = o                       # you steered into its side
                    else:
                        fatal = o                      # ran into the nose
            elif o.kind == "barrier":
                if dl < HIT_W:
                    ducking = p.slide > 0 and p.h <= p.support + 2
                    if not (ducking or p.h >= BARRIER_TOP - 16):
                        soft = o
            elif o.kind == "sign":
                if dl < HIT_W:
                    soft = o
        if rider is not None:
            rider.ridden = True

        if fatal is not None or soft is not None or bump is not None:
            support = self._collide(fatal, soft, bump, support)
        if self.game_over:
            return

        ceil = (TUN_H - STAND_H - 16) if self.in_tunnel else None
        fly = (JET_H + 8 * math.sin(self.elapsed * 6)) if flying else None
        p.update(k, support, ceil, fly)

        riding = support > 0 and p.h >= support - 0.5 and not flying
        floor_y = PLAYER_Y - p.support
        if p.landed and support > 0:
            self._popup("TRAIN SURF!", p.x, p.rect().top - 30)
            self._burst((p.x, PLAYER_Y - p.h), (255, 230, 150), 8)
            self.sfx.play("land")
        elif p.landed:
            self._burst((p.x, PLAYER_Y - p.h), (210, 200, 180), 6)
            self.sfx.play("land")
        if flying:
            rc = p.rect()
            for sx in (-11, 11):
                self._puff(p.x + sx, rc.bottom - 24, random.choice([(255, 170, 50), (255, 224, 110), (255, 120, 40)]), 1, up=-3)
        elif p.grounded():
            if p.slide > 0:
                if random.random() < .5 * k:
                    self._puff(p.x + random.randint(-16, 16), floor_y, (255, 214, 110), 1, up=3)
            elif random.random() < .16 * k:
                self._puff(p.x + random.randint(-14, 14), floor_y, (214, 204, 184), 1)
        if riding:
            self.surf_time += dt
            self.score += k * 1.2 * self.mult
        elif self.on_roof and self.surf_time > 1.2:
            bonus = int(self.surf_time * 40) * self.mult
            self.score += bonus
            self._popup(f"SURF BONUS +{bonus}", p.x, p.rect().top - 10)
            self.surf_time = 0.0
        elif not riding:
            self.surf_time = 0.0
        self.on_roof = riding

    # ------------------------------------------------------- hits & pickups --
    def _collide(self, fatal, soft, bump, support):
        p = self.player
        if p.ghost > 0:
            return support
        if fatal is not None:
            if p.shield > 0:
                self._shield_block(fatal)
                support = 0.0
            else:
                self.nose_timer += 1 / 60.0
                if self.nose_timer < LATE_GRACE:
                    return support                 # wait a moment: a late jump can still save you
                self._die()
                return support
        else:
            self.nose_timer = 0.0
        if bump is not None and p.bump <= 0:
            self._bounce(bump)
            if p.shield <= 0:
                self._stumble()
        if soft is not None and p.inv <= 0 and p.stumble <= 0:
            if p.shield > 0:
                self._shield_block(soft)
            else:
                soft.dead = True
                self._stumble()
        return support

    def _bounce(self, o):
        p = self.player
        if p.target != p.prev:
            p.target = p.prev
        else:
            d = -1 if o.lane > p.lane else 1
            p.target = int(clamp(round(p.target) + d, 0, 2))
            p.prev = p.target
        p.bump = 0.4

    def _stumble(self):
        p = self.player
        if p.inv > 0:
            return
        if self.chase > 0:
            self._die()                            # second trip while chased = caught
            return
        self.chase = CHASE_TIME
        p.stumble = 0.7
        p.inv = 1.5
        self.shake = 0.5
        self.banner = ("STUMBLE!  RUN!", 1.5)
        self._burst(p.rect().center, (255, 190, 90), 14)
        self.sfx.play("stumble")

    def _die(self):
        self.game_over = True
        self._burst(self.player.rect().center, (235, 88, 60), 26)
        self.shake = 0.6
        self.sfx.play("crash")

    def _shield_block(self, crash):
        p = self.player
        p.shield = 0
        crash.dead = True
        self.score += 100 * self.mult
        self._popup("SHIELD BLOCK", p.x, p.rect().top)
        sx, sy = self._screen_pos(crash.lane, max(crash.z, PZ), 40)
        self._burst((sx, sy), crash.color if crash.roof else (235, 235, 245), 30)
        self._burst(p.rect().center, (90, 210, 255), 18)
        self.shake = 0.4
        self.sfx.play("crash")

    def _pick_coin(self, o):
        self.coins += 1
        pts = 50 * self.mult
        self.score += pts
        x, y = self._screen_pos(o.lane, o.z, o.h + 18)
        self._popup(f"+{pts}", x, y)
        self._burst((x, y), COIN_GOLD, 8)
        self.sfx.play("coin")
        if self.coins % 40 == 0 and self.charges < 3:
            self.charges += 1
            self._popup("SHIELD CHARGE +1", self.player.x, self.player.rect().top - 50)

    def _pick_power(self, o):
        t = o.ptype
        p = self.player
        if t == "magnet":
            self.mag = MAG_TIME
        elif t == "x2":
            self.mult_t = X2_TIME
        elif t == "jet":
            self.jet = JET_TIME
            self._jet_coins()
        elif t == "boots":
            p.boots = BOOT_TIME
        x, y = self._screen_pos(o.lane, o.z, o.h + 26)
        self._popup(PU_NAMES.get(t, "POWER UP"), x, y - 10)
        self._burst((x, y), PU_COLORS.get(t, (255, 255, 255)), 20)
        self.sfx.play("power")

    def _jet_coins(self):
        for i in range(22):
            lane = 1.0 + 0.95 * math.sin(i * 0.55)
            self.objects.append(Obj(lane, "coin", 0.5 + i * 0.05, 0.0, JET_H - 24))

    # ---------------------------------------------------------------- spawn --
    def _lane_clear(self, lane):
        for q in self.objects:
            if q.lane == lane and q.kind not in ("coin", "pu") and q.z + q.length > 0.4:
                return False
        return True

    def _spawn_wave(self):
        early = self.elapsed < 12
        lanes = [0, 1, 2]
        n = 1 if (early or random.random() < .38) else 2
        picks = random.sample(lanes, n)
        free = [l for l in lanes if l not in picks]
        kinds = ["train", "bus", "barrier"] if early else \
            random.choices(["train", "bus", "barrier", "sign"], [38, 22, 25, 15], k=n)
        if early:
            kinds = [random.choice(kinds)]
        max_len = 0.05
        made = []
        for lane, kind in zip(picks, kinds):
            vel = 0.0
            if kind == "train":
                ln = random.uniform(.45, .95)
                if self.elapsed > 25 and random.random() < .28 and self._lane_clear(lane):
                    vel = 0.6                                  # fast express train
            elif kind == "bus":
                ln = random.uniform(.22, .32)
            else:
                ln = .05
            o = Obj(lane, kind, 1.0, ln, vel=vel)
            self.objects.append(o)
            made.append(o)
            max_len = max(max_len, ln)
            if kind in ("train", "bus"):
                if random.random() < .75:                      # coins riding on the roof
                    cnt = int(clamp(ln / .07, 3, 9))
                    for i in range(cnt):
                        self.objects.append(Obj(lane, "coin", 1.0 + .05 + i * .07, 0.0, o.roof + 6, vel=vel))
            elif kind == "barrier" and random.random() < .6:   # coin arc to jump through
                for i, hh in enumerate((26, 90, 140, 90, 26)):
                    self.objects.append(Obj(lane, "coin", 1.0 - .07 + i * .07, 0.0, hh))
        if free and random.random() < .7:                      # coin trail in a free lane
            cl = random.choice(free)
            for i in range(random.randint(4, 6)):
                self.objects.append(Obj(cl, "coin", 1.0 + i * .07, 0.0, 0))
        if self.elapsed >= self.next_pu:                       # power-up crate
            self.next_pu = self.elapsed + random.uniform(14, 24)
            pt = random.choices(["magnet", "x2", "jet", "boots"], [30, 30, 16, 24])[0]
            roofs = [m for m in made if m.roof]
            if roofs and random.random() < .45:
                host = random.choice(roofs)
                self.objects.append(Obj(host.lane, "pu", host.z + host.length * .5, 0.0,
                                        host.roof + 12, ptype=pt, vel=host.vel))
            elif free:
                self.objects.append(Obj(random.choice(free), "pu", 1.12, 0.0, 30, ptype=pt))
        gap = random.uniform(GAP_MIN, GAP_MAX)
        self.spawn_dist = max(max_len + gap, MIN_GAP_SEC * self.speed * 60)

    # ---------------------------------------------------------------- fx ----
    def _screen_pos(self, lane, z, h):
        t = t_of(clamp(z, Z_NEAR, 1.0))
        return int(lane_x(lane, t)), int(y_of(t) - h * s_of(t))

    def _popup(self, text, x, y):
        self.popups.append((text, x, y, 0.9))

    def _burst(self, center, color, n):
        cx, cy = center
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(2, 7)
            self.particles.append(Particle(cx, cy, math.cos(ang) * spd, math.sin(ang) * spd - 2,
                                           random.uniform(.3, .7), color))

    # ----------------------------------------------------------- environment --
    def _puff(self, x, y, color, n=4, up=1.5):
        for _ in range(n):
            self.particles.append(Particle(x + random.uniform(-6, 6), y, random.uniform(-1.8, 1.8),
                                           -random.uniform(.2, abs(up)) * (1 if up >= 0 else -1),
                                           random.uniform(.25, .5), color))

    def _make_warn(self):
        small = pygame.Surface((64, 36), pygame.SRCALPHA)
        for y in range(36):
            for x in range(64):
                dx, dy = (x - 31.5) / 32, (y - 17.5) / 18
                d = math.sqrt(dx * dx + dy * dy) / 1.25
                a = clamp((d - .5) / .5) ** 1.5
                small.set_at((x, y), (230, 30, 30, int(255 * a)))
        return pygame.transform.smoothscale(small, (W, H))

    def _make_glow(self, color, radius, peak):
        g = pygame.Surface((radius * 2, radius * 2))
        g.fill((0, 0, 0))
        for rr in range(radius, 1, -3):
            f = (1 - rr / radius) ** 1.7 * peak / 255.0
            pygame.draw.circle(g, (int(color[0] * f), int(color[1] * f), int(color[2] * f)), (radius, radius), rr)
        return g

    def _env(self):
        ph = (self.elapsed / DAY_SECONDS) % 3.0
        i = int(ph)
        f = ph - i
        f = f * f * (3 - 2 * f)
        a, b = SKY_KEYS[i], SKY_KEYS[(i + 1) % 3]
        self.env_top = mix(a[0], b[0], f)
        self.env_bot = mix(a[1], b[1], f)
        self.dark = a[2] + (b[2] - a[2]) * f

    def _tone(self, c):
        return mix(c, (10, 14, 34), self.dark * 0.9)

    def _fog(self, c, z):
        return mix(self._tone(c), self.env_bot, 0.38 * clamp(z))

    def _font(self, size, bold=True):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("arial", size, bold=bold)
        return self._fonts[key]

    def _make_vignette(self):
        levels = []
        for strength in (.35, .6, .85):
            small = pygame.Surface((64, 36))
            for y in range(36):
                for x in range(64):
                    dx, dy = (x - 31.5) / 32, (y - 17.5) / 18
                    d = math.sqrt(dx * dx + dy * dy) / 1.25
                    a = clamp((d - .45) / .55) ** 1.6 * strength
                    small.set_at((x, y), (int(255 - 245 * a), int(255 - 242 * a), int(255 - 225 * a)))
            levels.append(pygame.transform.smoothscale(small, (W, H)))
        return levels

    # ------------------------------------------------------------- drawing ---
    def draw(self, screen, camera=None, gesture="NO_HAND", event="READY", voice=""):
        shake_off = (0, 0)
        if self.shake > 0:
            m = int(self.shake * 14)
            shake_off = (random.randint(-m, m), random.randint(-m, m))
        base = getattr(self, "_base", None)
        if base is None:
            base = self._base = pygame.Surface((W, H))
        self._draw_world(base, camera, gesture, event, voice)
        screen.blit(base, shake_off)

    def _draw_world(self, screen, camera, gesture, event, voice):
        self._env()
        self._sky(screen)
        self._skyline(screen)
        self._ground(screen)
        for tn in self.tunnels:
            self._tunnel_shell(screen, tn)
        self._track(screen)
        for tn in self.tunnels:
            self._tunnel_floor(screen, tn)

        items = []
        for o in self.objects:
            if o.z > 1.0 or o.z + o.length < Z_NEAR or o.dead or (o.kind in ("coin", "pu") and o.hit):
                continue
            if o.roof:
                # split long vehicles at tunnel entrance/exit so each piece is clipped/occluded correctly
                cuts = sorted({c for tn in self.tunnels for c in (tn.zs, tn.ze)
                               if o.z < c < o.z + o.length})
                bounds = [o.z] + cuts + [o.z + o.length]
                for lo, hi in zip(bounds[:-1], bounds[1:]):
                    items.append((lo + (hi - lo) * .999, 0, (o, lo, hi)))
            else:
                items.append((o.z, 0, (o, None, None)))
        self._scenery_items(items)
        for tn in self.tunnels:
            if Z_NEAR <= tn.zs <= 1.0:
                items.append((tn.zs, 1, tn))
            if Z_NEAR <= tn.ze <= 1.0:
                items.append((tn.ze, 2, tn))
        items.sort(key=lambda it: -it[0])

        # while we're inside a tunnel, anything beyond the exit may only show through the exit window
        hole, hole_z = None, 9.0
        for tn in self.tunnels:
            if tn.zs <= PZ and Z_NEAR < tn.ze <= 1.0:
                lwe, se, ye = self._geom(tn.ze)
                hole = pygame.Rect(int(CX - TUN_HALF * lwe), int(ye - TUN_H * se), int(2 * TUN_HALF * lwe) + 1,
                                   int(TUN_H * se) + 1).clip(screen.get_rect())
                hole_z = tn.ze
        player_done = False
        fog_done = False
        for key, kind, payload in items:
            if hole is not None and kind in (0, 3, 4, 5):
                screen.set_clip(hole if key > hole_z else None)
            if not fog_done and key < 0.5:
                self._far_fog(screen)
                fog_done = True
            if not player_done and key <= PZ:
                self._draw_player(screen)
                player_done = True
            if kind == 0:
                self._draw_object(screen, *payload)
            elif kind == 1:
                self._draw_facade(screen, payload)
            elif kind == 2:
                self._draw_exit_rim(screen, payload)
            elif kind == 3:
                self._draw_building(screen, payload)
            elif kind == 4:
                self._draw_lamp(screen, *payload)
            elif kind == 5:
                self._draw_gantry(screen, *payload)
        screen.set_clip(None)
        if not player_done:
            self._draw_player(screen)

        if not fog_done:
            self._far_fog(screen)

        self._speed_lines(screen)
        self._draw_chaser(screen)

        for p in self.particles:
            a = max(0, min(255, int(255 * (p.life / .6)))) >> 4 << 4
            pk = (p.color, a)
            surf = self._dot_cache.get(pk)
            if surf is None:
                surf = pygame.Surface((6, 6), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*p.color, a), (3, 3), 3)
                self._dot_cache[pk] = surf = surf.convert_alpha()
            screen.blit(surf, (p.x - 3, p.y - 3))

        f = self._font(22)
        for (text, x, y, life) in self.popups:
            a = max(0, min(255, int(255 * (life / .9))))
            sh = f.render(text, True, (0, 0, 0))
            surf = f.render(text, True, (255, 235, 150))
            sh.set_alpha(a // 2)
            surf.set_alpha(a)
            screen.blit(sh, (x - surf.get_width() // 2 + 2, y + 2))
            screen.blit(surf, (x - surf.get_width() // 2, y))

        va = max(self.progress * 0.9, self.tun_dark * 0.95)
        if va > 0.12:
            lvl = 0 if va < .4 else 1 if va < .7 else 2
            screen.blit(self._vig[lvl], (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        if self.chase_k > 0.02:
            self._warn.set_alpha(int(150 * self.chase_k * (0.65 + 0.35 * math.sin(self.elapsed * 8))))
            screen.blit(self._warn, (0, 0))

        self._hud(screen, gesture, event, voice, camera)

    # -------- background layers
    def _sky(self, screen):
        key = (self.env_top[0] >> 1, self.env_top[1] >> 1, self.env_top[2] >> 1,
               self.env_bot[0] >> 1, self.env_bot[1] >> 1, self.env_bot[2] >> 1)
        if key != getattr(self, "_sky_key", None):          # smooth gradient, rebuilt only when colours change
            self._sky_key = key
            for y in range(330):
                pygame.draw.line(self._skyg, mix(self.env_top, self.env_bot, (y / 329.0) ** 1.15), (0, y), (W, y))
        screen.blit(self._skyg, (0, 0))
        d = self.dark
        if d > .3:
            for sx, sy, br in self._stars:
                if br < clamp((d - .3) / .25):
                    c = int(150 + 105 * br)
                    screen.fill((c, c, min(255, c + 20)), (sx, sy, 2, 2))
        sun_y = 95 + 300 * clamp(d / .4)
        if sun_y < 345:
            sc = mix((255, 244, 200), (255, 150, 90), d / .2)
            screen.blit(self._glow_sun, (1080 - 150, int(sun_y) - 150), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(screen, mix(sc, self.env_bot, .35), (1080, int(sun_y)), 78, 3)
            pygame.draw.circle(screen, sc, (1080, int(sun_y)), 55)
        moon_y = 360 - 265 * clamp((d - .2) / .35)
        if moon_y < 330:
            pygame.draw.circle(screen, (232, 236, 255), (960, int(moon_y)), 34)
            pygame.draw.circle(screen, self.env_top, (972, int(moon_y) - 6), 29)
        cc = mix((255, 255, 255), self.env_top, d * 1.2)
        for i, (cx, cy, cw) in enumerate(((200, 80, 120), (620, 130, 160), (900, 60, 100))):
            x = (cx - self.scroll * 0.03 * (1 + i * .3)) % (W + 300) - 150
            for dx, dy, rw in ((0, 0, cw), (cw * .35, -10, cw * .7), (-cw * .35, 6, cw * .6)):
                ck = (int(rw), cc[0] >> 2, cc[1] >> 2, cc[2] >> 2)
                s = self._cloud_cache.get(ck)
                if s is None:
                    s = pygame.Surface((int(rw), 34), pygame.SRCALPHA)
                    pygame.draw.ellipse(s, (*cc, 150), s.get_rect())
                    if len(self._cloud_cache) > 200:
                        self._cloud_cache.clear()
                    self._cloud_cache[ck] = s = s.convert_alpha()
                screen.blit(s, (x + dx - rw / 2, cy + dy))

    def _skyline(self, screen):
        night = clamp(self.dark / .45)
        for layer, (spacing, speed, hmin, hvar, pal) in enumerate((
                (110, 0.05, 90, 140, [(150, 172, 205), (138, 160, 196), (160, 180, 210)]),
                (90, 0.12, 70, 150, [(120, 150, 190), (100, 130, 175), (140, 165, 200)]))):
            total = int(self.scroll * speed)
            base, off = divmod(total, spacing)
            for k in range(-1, W // spacing + 2):
                gi = base + k
                xx = k * spacing - off
                h = hmin + (gi * 53 + layer * 17) % hvar
                col = self._fog(pal[gi % 3], .35 if layer == 0 else .1)
                pygame.draw.rect(screen, col, (xx, 330 - h, spacing - 20, h))
                pygame.draw.rect(screen, shade(col, .86), (xx, 328, spacing - 20, 4))
                if layer == 1:
                    wl = (255, 232, 150)
                    wo = mix(col, (255, 255, 255), .25)
                    thr = int((.25 + .6 * night) * 97)
                    for wy in range(int(330 - h) + 10, 322, 28):
                        for wx in range(xx + 8, xx + spacing - 28, 24):
                            lit = (gi * 31 + (wy >> 3) * 7 + k * 13) % 97 < thr
                            screen.fill(wl if lit else wo, (wx, wy, 9, 11))
                    if gi % 3 == 0:
                        pygame.draw.rect(screen, col, (xx + 24, 330 - h - 18, 8, 18))
                        pygame.draw.circle(screen, shade(col, .9), (xx + 28, 330 - h - 22), 7)
        a = self.env_bot
        key = (a[0] >> 3, a[1] >> 3, a[2] >> 3)
        if key != getattr(self, "_haze_key", None):
            self._haze_key = key
            for i in range(40):
                self._haze.fill((0, 0, 0, 0), (0, i, W, 1))
                pygame.draw.line(self._haze, (*a, int(140 * (1 - i / 40))), (0, i), (W, i))
        screen.blit(self._haze, (0, 310))

    def _ground(self, screen):
        night = clamp(self.dark / .5)
        pygame.draw.rect(screen, self._tone((168, 150, 120)), (0, 330, W, 390))
        gscroll = (self.scroll * 0.9) % 380
        gc = self._tone((140, 122, 96))
        for gx, gy in self._gravel:
            if 250 < gx < 1030:
                continue
            yy = 330 + (gy + gscroll) % 380
            pygame.draw.circle(screen, gc, (gx, int(yy)), 2)
        if self.progress > 0.25:
            n = int(4 + 10 * self.progress)
            ends = (-300, -120, 20, 140, 1140, 1260, 1400, 1580)
            for i in range(n):
                xe = ends[i % len(ends)]
                ph = (self.scroll * 0.004 + i * 0.173) % 1.0
                t0, t1 = ph, min(1.0, ph + 0.10)
                p0 = (640 + (xe - 640) * t0, 330 + 390 * t0)
                p1 = (640 + (xe - 640) * t1, 330 + 390 * t1)
                pygame.draw.line(screen, self._tone((196, 180, 150)), p0, p1, max(1, int(1 + t0 * 3)))
        for side in (-1, 1):
            if side < 0:
                poly = [(0, 330), (580, 330), (230, 720), (0, 720)]
            else:
                poly = [(W, 330), (700, 330), (1050, 720), (W, 720)]
            pygame.draw.polygon(screen, self._tone((158, 160, 172)), poly)
            tile = (self.scroll * 1.1) % 60
            for y in range(330, 780, 60):
                yy = y + tile - 60
                if yy < 332 or yy > 720:
                    continue
                tt = (yy - 330) / 390
                edge = 580 - tt * 350 if side < 0 else 700 + tt * 350
                pygame.draw.line(screen, self._tone((132, 134, 148)), (0 if side < 0 else W, yy), (edge, yy),
                                 max(1, int(1 + tt * 3)))
            e0 = (580, 330) if side < 0 else (700, 330)
            e1 = (230, 720) if side < 0 else (1050, 720)
            pygame.draw.line(screen, (255, 214, 40), e0, e1, 5)

    def _track(self, screen):
        pygame.draw.polygon(screen, self._tone((108, 96, 78)), [(230, 720), (1050, 720), (700, 330), (580, 330)])
        tl = self.player.target
        fx0, fx1 = 580 + tl * 40, 580 + (tl + 1) * 40
        tx0, tx1 = 230 + tl * 273, 230 + (tl + 1) * 273
        self._ov.fill((0, 0, 0, 0))
        pygame.draw.polygon(self._ov, (255, 255, 255, 26), [(fx0, 330), (fx1, 330), (tx1, 720), (tx0, 720)])
        screen.blit(self._ov, (0, 330), area=(0, 330, W, 390))
        for lane_edge in (1, 2):
            fx = 580 + lane_edge * 40
            tx = 230 + lane_edge * 273
            for s in range(10):
                t0, t1 = s / 10, (s + .55) / 10
                p0 = (fx + (tx - fx) * t0, 330 + 390 * t0)
                p1 = (fx + (tx - fx) * t1, 330 + 390 * t1)
                pygame.draw.line(screen, self._tone((200, 195, 180)), p0, p1, max(1, int(1 + t0 * 3)))
        tie_scroll = self.scroll % 46
        for y in range(380, 760, 46):
            yy = y - tie_scroll
            if yy < 330:
                continue
            t = (yy - 330) / 390
            pygame.draw.line(screen, self._tone((74, 58, 42)), (580 - t * 330, yy), (700 + t * 330, yy),
                             max(3, int(4 + t * 8)))
        for lane_edge in range(4):
            fx = 580 + lane_edge * 40
            tx = 230 + lane_edge * 273
            pygame.draw.line(screen, RAIL, (fx, 330), (tx, 720), 3)
            pygame.draw.line(screen, (170, 160, 150), (fx, 330), (tx, 720), 1)

    def _far_fog(self, screen):
        a = mix(self.env_bot, (18, 20, 30), self.tun_dark)
        key = (a[0] >> 3, a[1] >> 3, a[2] >> 3)
        if key != getattr(self, "_fog_key", None):
            self._fog_key = key
            for i in range(90):
                al = int(110 * (i / 60)) if i < 60 else int(110 * max(0, 1 - (i - 60) / 30))
                self._fogs.fill((0, 0, 0, 0), (0, i, W, 1))
                pygame.draw.line(self._fogs, (*a, al), (0, i), (W, i))
        screen.blit(self._fogs, (0, 270))

    # -------- tunnels
    def _geom(self, z):
        t = t_of(z)
        return lw_of(t), s_of(t), y_of(t)

    def _tunnel_shell(self, screen, tn):
        zs, ze = tn.zs, tn.ze
        a, b = max(zs, Z_NEAR), min(ze, 1.0)
        if a >= b:
            return
        full = screen.get_rect()
        if zs > Z_NEAR:
            lw, s, yg = self._geom(zs)
            clip = pygame.Rect(int(CX - TUN_HALF * lw), int(yg - TUN_H * s), int(2 * TUN_HALF * lw) + 1, int(TUN_H * s) + 1)
        else:
            clip = full
        clip = clip.clip(full)
        if clip.w <= 0 or clip.h <= 0:
            return
        hole = None
        saved = None
        if ze <= 1.0:
            lwe, se, ye = self._geom(ze)
            hole = pygame.Rect(int(CX - TUN_HALF * lwe), int(ye - TUN_H * se), int(2 * TUN_HALF * lwe) + 1,
                               int(TUN_H * se) + 1).clip(clip)
            if hole.w > 0 and hole.h > 0:
                saved = screen.subsurface(hole).copy()
        screen.set_clip(clip)
        screen.fill(self._tone((64, 68, 84)), clip)

        lwa, sa, ya = self._geom(a)
        lwb, sb, yb = self._geom(b)
        pygame.draw.polygon(screen, self._tone((36, 38, 48)),
                            [(CX - TUN_HALF * lwb, yb), (CX + TUN_HALF * lwb, yb),
                             (CX + TUN_HALF * lwa, ya), (CX - TUN_HALF * lwa, ya)])
        k0 = int(math.floor((a - zs) / TUN_RING))
        k1 = int(math.ceil((b - zs) / TUN_RING))
        for k in range(k1, k0 - 1, -1):
            zk0 = zs + k * TUN_RING
            za, zb = max(zk0, a), min(zk0 + TUN_RING, b)
            if za >= zb:
                continue
            lA, sA, yA = self._geom(za)
            lB, sB, yB = self._geom(zb)
            xlA, xrA = CX - TUN_HALF * lA, CX + TUN_HALF * lA
            xlB, xrB = CX - TUN_HALF * lB, CX + TUN_HALF * lB
            tA, tB = yA - TUN_H * sA, yB - TUN_H * sB
            fogf = 1.0 - 0.55 * clamp(zb)
            wall = shade((74, 78, 96) if k % 2 == 0 else (62, 66, 82), fogf)
            ceil = shade((90, 94, 116), fogf)
            pygame.draw.polygon(screen, wall, [(xlA, yA), (xlA, tA), (xlB, tB), (xlB, yB)])
            pygame.draw.polygon(screen, wall, [(xrA, yA), (xrA, tA), (xrB, tB), (xrB, yB)])
            pygame.draw.polygon(screen, ceil, [(xlA, tA), (xrA, tA), (xrB, tB), (xlB, tB)])
            for xa, xb in ((xlA, xlB), (xrA, xrB)):
                pygame.draw.line(screen, shade((255, 200, 60), fogf), (xa, yA - 70 * sA), (xb, yB - 70 * sB),
                                 max(1, int(4 * sA)))
            c0, c1 = zk0 + .38 * TUN_RING, zk0 + .62 * TUN_RING
            if c0 >= a and c1 <= b:
                l0, s0, y0 = self._geom(c0)
                l1, s1, y1 = self._geom(c1)
                q0, q1 = y0 - TUN_H * s0 + 2, y1 - TUN_H * s1 + 2
                pygame.draw.polygon(screen, shade((255, 244, 200), .6 + .4 * fogf),
                                    [(CX - .32 * l0, q0), (CX + .32 * l0, q0), (CX + .32 * l1, q1), (CX - .32 * l1, q1)])
            if zk0 >= a:
                pygame.draw.lines(screen, shade((40, 42, 56), fogf), False,
                                  [(xlA, yA), (xlA, tA), (xrA, tA), (xrA, yA)], max(2, int(7 * sA)))
        if ze > 1.0:
            lw, s, yg = self._geom(1.0)
            pygame.draw.rect(screen, (6, 8, 14), (CX - TUN_HALF * lw, yg - TUN_H * s, 2 * TUN_HALF * lw, TUN_H * s))
        screen.set_clip(None)
        if saved is not None:
            screen.blit(saved, hole.topleft)

    def _tunnel_floor(self, screen, tn):
        a, b = max(tn.zs, Z_NEAR), min(tn.ze, 1.0)
        if a >= b:
            return
        lwa, sa, ya = self._geom(a)
        lwb, sb, yb = self._geom(b)
        self._ov.fill((0, 0, 0, 0))
        pygame.draw.polygon(self._ov, (0, 0, 10, 120),
                            [(CX - TUN_HALF * lwb, yb), (CX + TUN_HALF * lwb, yb),
                             (CX + TUN_HALF * lwa, ya), (CX - TUN_HALF * lwa, ya)])
        r = pygame.Rect(0, int(yb) - 1, W, int(ya - yb) + 3).clip(screen.get_rect())
        screen.blit(self._ov, r.topleft, area=r)

    def _draw_facade(self, screen, tn):
        lw, s, yg = self._geom(tn.zs)
        z = clamp(tn.zs)
        fw, fh = 3.7 * lw, 650 * s
        ow, oh = TUN_HALF * lw, TUN_H * s
        col = self._fog((132, 136, 152), z)
        dark = shade(col, .78)
        top_y = yg - fh
        pygame.draw.rect(screen, col, (CX - fw, top_y, fw - ow, fh))
        pygame.draw.rect(screen, col, (CX + ow, top_y, fw - ow, fh))
        pygame.draw.rect(screen, col, (CX - ow, top_y, 2 * ow, fh - oh))
        step = max(8, int(70 * s))
        for yy in range(int(top_y), int(yg), step):
            pygame.draw.line(screen, dark, (CX - fw, yy), (CX - ow, yy), 1)
            pygame.draw.line(screen, dark, (CX + ow, yy), (CX + fw, yy), 1)
            pygame.draw.line(screen, dark, (CX - ow, yy), (CX + ow, yy), 1) if yy < yg - oh else None
        pygame.draw.rect(screen, dark, (CX - fw, top_y, 2 * fw, fh), max(2, int(5 * s)))
        # hazard band above the opening
        bh = max(6, int(30 * s))
        sw = max(10, int(46 * s))
        for i, x in enumerate(range(int(CX - ow), int(CX + ow), sw)):
            c = (250, 200, 40) if i % 2 == 0 else (30, 32, 40)
            pygame.draw.rect(screen, self._fog(c, z), (x, yg - oh - bh, min(sw, CX + ow - x), bh))
        pygame.draw.rect(screen, self._fog((205, 210, 222), z), (CX - ow, yg - oh, 2 * ow, oh), max(2, int(9 * s)))
        if s > .3:
            f = self._font(int(clamp(46 * s, 12, 60)))
            tx = f.render("METRO TUNNEL", True, (250, 250, 255))
            screen.blit(tx, tx.get_rect(center=(CX, yg - oh - bh - 38 * s - 6)))
        blink = int(self.elapsed * 3) % 2 == 0
        for sx in (-1, 1):
            c = (255, 70, 60) if blink else (110, 30, 30)
            pygame.draw.circle(screen, c, (int(CX + sx * (ow + 0.55 * (fw - ow))), int(yg - oh - 40 * s)), max(3, int(14 * s)))

    def _draw_exit_rim(self, screen, tn):
        lw, s, yg = self._geom(tn.ze)
        ow, oh = TUN_HALF * lw, TUN_H * s
        pygame.draw.rect(screen, (170, 176, 192), (CX - ow, yg - oh, 2 * ow, oh), max(3, int(12 * s)))

    # -------- scenery (procedural: depends only on travel, so it never flickers)
    def _in_tunnel_zone(self, z, margin=0.35):
        for tn in self.tunnels:
            if tn.zs < z < tn.ze + margin:
                return True
        return False

    def _scenery_items(self, items):
        D = 0.19
        for sd in (-1, 1):
            off = 0.0 if sd < 0 else D * .5
            i0 = int(math.floor((self.travel - off - 0.4) / D))
            i1 = int(math.floor((self.travel - off + 1.15) / D)) + 1
            for i in range(i0, i1 + 1):
                zf = i * D + off - self.travel
                if zf > 1.0 or self._in_tunnel_zone(zf):
                    continue
                if hsh(i, sd + 3) < .07:
                    continue
                d = D * (.6 + .32 * hsh(i, sd + 4))
                wd = 1.0 + 2.4 * hsh(i, sd + 5)
                inner = 2.55 + (.5 if hsh(i, sd + 6) < .2 else 0.0)
                hpx = 380 + 1050 * hsh(i, sd + 7) ** 1.3
                style = int(hsh(i, sd + 8) * 3)
                col = BUILD_COLORS[int(hsh(i, sd + 9) * len(BUILD_COLORS)) % len(BUILD_COLORS)]
                items.append((zf, 3, (zf, d, sd, inner, wd, hpx, style, col, i * 2 + (1 if sd > 0 else 0))))
        SP = 0.22
        i0 = int(math.floor((self.travel - 0.3) / SP))
        i1 = int(math.floor((self.travel + 1.0) / SP)) + 1
        for i in range(i0, i1 + 1):
            z = i * SP - self.travel
            if z > 1.0 or z < -0.12 or self._in_tunnel_zone(z, .2):
                continue
            for sd in (-1, 1):
                items.append((z, 4, (z, sd)))
        SPG = 1.6
        i0 = int(math.floor((self.travel - 0.3) / SPG))
        i1 = int(math.floor((self.travel + 1.0) / SPG)) + 1
        for i in range(i0, i1 + 1):
            z = i * SPG + 0.4 - self.travel
            if z > 1.0 or z < -0.04 or self._in_tunnel_zone(z, .3):
                continue
            items.append((z, 5, (z, i)))

    def _draw_building(self, screen, b):
        zf, d, sd, inner, wd, hpx, style, col, idx = b
        zn, zr = max(zf, Z_NEAR), min(zf + d, 1.0)
        if zn >= zr:
            return
        tn, tr = t_of(zn), t_of(zr)
        lwn, lwr = lw_of(tn), lw_of(tr)
        sn, sr = s_of(tn), s_of(tr)
        xin_n, xin_r = CX + sd * inner * lwn, CX + sd * inner * lwr
        ybn, ybr = y_of(tn), y_of(tr)
        ytn, ytr = ybn - hpx * sn, ybr - hpx * sr
        side_c = self._fog(shade(col, .80), zn)
        front_c = self._fog(col, zn)
        pygame.draw.polygon(screen, side_c, [(xin_n, ytn), (xin_n, ybn), (xin_r, ybr), (xin_r, ytr)])
        night = clamp(self.dark / .5)
        glass = style == 1
        pitch = 84 if not glass else 56
        rows = int(hpx // pitch)
        lit_p = .12 + .75 * night
        lit_c = self._fog((255, 232, 150), zn)
        off_c = self._fog(mix(col, (60, 90, 140) if glass else (255, 255, 255), .45 if glass else .25), zn)

        def row_range(yb, sc):
            # only rows that can actually be on screen
            lo = max(0, int(((yb - H - 30) / sc - 110) // pitch))
            hi = min(rows, int(((yb + 30) / sc - 110) // pitch) + 1)
            return lo, hi

        # windows on the track-facing wall
        if sn > .25:
            ncol = max(2, int(d / 0.035))
            lo, hi = row_range(ybn, sn)
            for c in range(ncol):
                z0, z1 = zf + (c + .18) / ncol * d, zf + (c + .78) / ncol * d
                if z0 < Z_NEAR or z1 > 1.0:
                    continue
                t0, t1 = t_of(z0), t_of(z1)
                x0, x1 = CX + sd * inner * lw_of(t0), CX + sd * inner * lw_of(t1)
                if max(x0, x1) < -10 or min(x0, x1) > W + 10:
                    continue
                s0, s1 = s_of(t0), s_of(t1)
                y0, y1 = y_of(t0), y_of(t1)
                for r in range(lo, hi):
                    v0 = 110 + r * pitch
                    v1 = v0 + pitch * .55
                    if v1 > hpx - 20:
                        break
                    wc = lit_c if hsh(idx * 131 + c * 17 + r, 7) < lit_p else off_c
                    pygame.draw.polygon(screen, wc, [(x0, y0 - v1 * s0), (x0, y0 - v0 * s0),
                                                     (x1, y1 - v0 * s1), (x1, y1 - v1 * s1)])
        # near end (front face)
        if zf >= Z_NEAR:
            xout = CX + sd * (inner + wd) * lwn
            xl, xr = min(xin_n, xout), max(xin_n, xout)
            pygame.draw.rect(screen, front_c, (xl, ytn, xr - xl, ybn - ytn))
            pygame.draw.rect(screen, shade(front_c, .7), (xl, ytn, xr - xl, ybn - ytn), 2)
            nc = max(2, int(wd * 1.5))
            gap = (xr - xl) / nc
            lo, hi = row_range(ybn, sn)
            for r in (range(lo, hi) if sn > .25 else ()):
                v0 = 110 + r * pitch
                v1 = v0 + pitch * .55
                if v1 > hpx - 20:
                    break
                ya, yb2 = ybn - v0 * sn, ybn - v1 * sn
                for c in range(nc):
                    wx = xl + gap * (c + .2)
                    if wx > W or wx + gap * .6 < 0:
                        continue
                    wc = lit_c if hsh(idx * 53 + c * 11 + r, 9) < lit_p else off_c
                    pygame.draw.rect(screen, wc, (wx, yb2, gap * .6, ya - yb2))
            # shopfront with awning at street level
            sh_h = 100 * sn
            awn = self._fog(BUILD_COLORS[(idx * 5) % len(BUILD_COLORS)], zn)
            pygame.draw.rect(screen, shade(front_c, .55), (xl, ybn - sh_h, xr - xl, sh_h))
            pygame.draw.rect(screen, lit_c if night > .2 else self._fog((170, 205, 230), zn),
                             (xl + gap * .2, ybn - sh_h * .85, (xr - xl) - gap * .4, sh_h * .55))
            sw = max(6, int(22 * sn))
            x0 = max(int(xl), 0)
            x1 = min(int(xr), W)
            start = int(xl) + ((x0 - int(xl)) // sw) * sw
            for j, xx in enumerate(range(start, x1, sw)):
                pygame.draw.rect(screen, awn if ((xx - int(xl)) // sw) % 2 == 0 else (245, 245, 245),
                                 (xx, ybn - sh_h - 14 * sn, min(sw, xr - xx), 14 * sn))

    def _draw_lamp(self, screen, z, sd):
        t = t_of(z)
        lw, s, yg = lw_of(t), s_of(t), y_of(t)
        x = CX + sd * 1.78 * lw
        top = yg - 250 * s
        w = max(2, int(7 * s))
        c = self._fog((70, 74, 88), z)
        pygame.draw.line(screen, c, (x, yg), (x, top), w)
        hx = x - sd * 0.42 * lw
        pygame.draw.line(screen, c, (x, top), (hx, top - 6 * s), w)
        pygame.draw.ellipse(screen, self._fog((255, 244, 200), z), (hx - 14 * s, top - 10 * s, 28 * s, 11 * s))
        night = clamp(self.dark / .4)
        if night > .05 and s > .22:
            r = int(46 * s)
            g = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            for rr in range(r, 0, -4):
                pygame.draw.circle(g, (255, 230, 150, int(55 * night * (1 - rr / r) + 8 * night)), (r, r), rr)
            screen.blit(g, (hx - r, top - r))

    def _draw_gantry(self, screen, z, idx):
        t = t_of(z)
        lw, s, yg = lw_of(t), s_of(t), y_of(t)
        px = 2.05 * lw
        top = yg - 430 * s
        c = self._fog((86, 92, 108), z)
        w = max(3, int(16 * s))
        for sd in (-1, 1):
            pygame.draw.rect(screen, c, (CX + sd * px - w // 2, top, w, yg - top))
        pygame.draw.rect(screen, c, (CX - px - w // 2, top, 2 * px + w, max(4, int(26 * s))))
        pygame.draw.rect(screen, shade(c, .7), (CX - px - w // 2, top + 22 * s, 2 * px + w, max(2, int(6 * s))))
        for lane in range(3):
            lx = CX + (lane - 1) * lw
            bw, bh = .28 * lw, 54 * s
            pygame.draw.rect(screen, self._fog((30, 32, 40), z), (lx - bw / 2, top + 26 * s, bw, bh), border_radius=3)
            on = hsh(idx, lane) < .55
            col = (70, 230, 110) if on else (255, 70, 60)
            pygame.draw.circle(screen, self._fog(col, z), (int(lx), int(top + 26 * s + bh * .5)), max(2, int(14 * s)))

    # -------- vehicles & obstacles
    def _draw_object(self, screen, o, lo=None, hi=None):
        if o.kind == "coin":
            self._draw_coin(screen, o)
        elif o.kind == "pu":
            self._draw_pu(screen, o)
        elif o.roof:
            self._draw_vehicle(screen, o, lo, hi)
        elif o.kind == "sign":
            self._draw_sign(screen, o)
        else:
            self._draw_barrier(screen, o)

    def _draw_coin(self, screen, o):
        if o.z > 1.0 or o.z < Z_NEAR:
            return
        x, y = self._screen_pos(o.lane, o.z, o.h + 18)
        t = t_of(o.z)
        r = max(4, int((8 + 14 * s_of(t))))
        gy = y_of(t)
        if o.h > 0:
            sh = max(3, r)
            pygame.draw.ellipse(screen, (0, 0, 0, 0) if False else shade(self._tone((168, 150, 120)), .7),
                                (x - sh, gy - 3, sh * 2, 6)) if o.h < 40 else None
        spin = abs(math.sin(self.elapsed * 6 + o.lane + o.z * 8))
        ew = max(3, int(r * 2 * spin))
        pygame.draw.ellipse(screen, self._fog(COIN_GOLD, o.z), (x - ew // 2, y - r, ew, 2 * r))
        pygame.draw.ellipse(screen, COIN_LIGHT, (x - max(1, ew // 4), y - r // 2, max(2, ew // 2), r), 2)

    def _draw_vehicle(self, screen, o, lo=None, hi=None):
        zf, zr = o.z, o.z + o.length
        if zf > 1.0:
            return
        zn, zz = max(zf, Z_NEAR), min(zr, 1.0)
        if lo is not None:
            zn = max(zn, lo)
        if hi is not None:
            zz = min(zz, hi)
        if zn >= zz:
            return
        tn, tf = t_of(zn), t_of(zz)
        hh = o.roof
        bus = o.kind == "bus"
        night = clamp(self.dark / .45)
        span, full = zz - zn, zr - zf

        def P(t):
            lw = lw_of(t)
            cx = lane_x(o.lane, t)
            hw = HALF * lw
            yb = y_of(t)
            return cx - hw, cx + hw, yb - hh * s_of(t), yb

        def a_of(u):             # position along the WHOLE vehicle -> visible 0..1 (details stay glued on)
            return clamp((zf + u * full - zn) / span)

        xl_n, xr_n, yt_n, yb_n = P(tn)
        xl_f, xr_f, yt_f, yb_f = P(tf)
        sn = s_of(tn)
        col = o.color
        body = self._fog(col, zn)
        side_c = self._fog(shade(col, .62), zn)
        roof_c = self._fog(tuple(min(255, int(c * 1.18) + 12) for c in col), zn)
        outline = self._fog((36, 38, 46), zn)
        dark = self._fog((26, 28, 36), zn)
        ncar = 1 if bus else max(2, int(round(o.length / .16)))

        # ---- roof
        roof = [(xl_n, yt_n), (xr_n, yt_n), (xr_f, yt_f), (xl_f, yt_f)]
        pygame.draw.polygon(screen, roof_c, roof)
        xc_n, xc_f = (xl_n + xr_n) / 2, (xl_f + xr_f) / 2
        hw_n, hw_f = (xr_n - xl_n) / 2, (xr_f - xl_f) / 2

        def R(a, b):
            return (lerp(xc_n + b * hw_n, xc_f + b * hw_f, a), lerp(yt_n, yt_f, a))

        pygame.draw.line(screen, shade(roof_c, .8), R(0, 0), R(1, 0), max(1, int(3 * sn)))
        if sn > .22:
            for i in range(1, ncar):
                a = a_of(i / ncar)
                if 0 < a < 1:
                    pygame.draw.line(screen, shade(roof_c, .55), R(a, -1), R(a, 1), max(1, int(2 * sn)))

            def box(u0, u1, w, hb, c):
                a0, a1 = a_of(u0), a_of(u1)
                if a1 - a0 < .003:
                    return
                s0 = s_of(lerp(tn, tf, a0))
                s1 = s_of(lerp(tn, tf, a1))

                def Q(a, b, up, sc):
                    x, y = R(a, b)
                    return (x, y - up * sc)

                if zf + u0 * full >= zn:
                    pygame.draw.polygon(screen, shade(c, .66),
                                        [Q(a0, -w, 0, s0), Q(a0, w, 0, s0), Q(a0, w, hb, s0), Q(a0, -w, hb, s0)])
                top = [Q(a0, -w, hb, s0), Q(a0, w, hb, s0), Q(a1, w, hb, s1), Q(a1, -w, hb, s1)]
                pygame.draw.polygon(screen, c, top)
                pygame.draw.polygon(screen, shade(c, .5), top, 1)

            if bus:
                box(.30, .62, .5, 10, shade(roof_c, 1.1))
                box(.72, .86, .35, 6, shade(roof_c, .85))
            else:
                for i in range(ncar):
                    box((i + .2) / ncar, (i + .5) / ncar, .55, 11, shade(roof_c, 1.08))
                    box((i + .62) / ncar, (i + .78) / ncar, .32, 6, shade(roof_c, .82))
        pygame.draw.polygon(screen, outline, roof, 1)
        if o.ridden:                                   # glowing edge while you surf it
            pygame.draw.polygon(screen, (255, 236, 150), roof, 3)

        # ---- side wall facing the centre line
        if o.lane != 1:
            sx_n, sx_f = (xr_n, xr_f) if o.lane == 0 else (xl_n, xl_f)
            wall = [(sx_n, yt_n), (sx_n, yb_n), (sx_f, yb_f), (sx_f, yt_f)]
            pygame.draw.polygon(screen, side_c, wall)

            def S(a, v):
                yb = lerp(yb_n, yb_f, a)
                yt = lerp(yt_n, yt_f, a)
                return (lerp(sx_n, sx_f, a), yb + (yt - yb) * v)

            def band(u0, u1, v0, v1, c, edge=None):
                a0, a1 = a_of(u0), a_of(u1)
                if a1 - a0 < .003:
                    return
                pts = [S(a0, v0), S(a0, v1), S(a1, v1), S(a1, v0)]
                pygame.draw.polygon(screen, c, pts)
                if edge is not None:
                    pygame.draw.polygon(screen, edge, pts, 1)

            band(0, 1, .24, .33, self._fog(o.accent, zn))
            win = self._fog(mix((190, 228, 250), (255, 224, 140), night * .85), zn)
            if bus:
                nw = max(3, int(o.length / .06))
                for w in range(nw):
                    band((w + .12) / nw, (w + .88) / nw, .46, .84, win, outline)
                for u in (.18, .82):
                    band(u - .05, u + .05, 0, .2, dark)
            else:
                door_c = shade(side_c, .78)
                for i in range(ncar):
                    for w0, w1 in ((.06, .2), (.24, .38), (.62, .76), (.8, .94)):
                        band((i + w0) / ncar, (i + w1) / ncar, .5, .84, win, outline)
                    band((i + .43) / ncar, (i + .57) / ncar, .08, .84, door_c, outline)
                    for bx in (.13, .87):
                        u = (i + bx) / ncar
                        band(u - .02, u + .02, 0, .15, dark)
                for i in range(1, ncar):
                    a = a_of(i / ncar)
                    if 0 < a < 1:
                        pygame.draw.line(screen, outline, S(a, 0), S(a, 1), max(1, int(2 * sn)))
                if o.var > .45 and sn > .28:           # graffiti tag
                    ci = int(o.var * 97) % ncar
                    gc = self._fog([(255, 90, 170), (90, 230, 255), (170, 255, 90), (255, 230, 80)][int(o.var * 40) % 4], zn)
                    tag = [(.1, .30), (.22, .46), (.34, .28), (.46, .45), (.58, .30)]
                    pts = [S(a_of((ci + uu) / ncar), vv) for uu, vv in tag]
                    pygame.draw.lines(screen, gc, False, pts, max(2, int(5 * sn)))
            pygame.draw.polygon(screen, outline, wall, 1)

        # ---- nose (only while it is still in front of the camera)
        if zf >= Z_NEAR and (lo is None or zf >= lo - 1e-9):
            fw, fh = xr_n - xl_n, yb_n - yt_n
            r = pygame.Rect(int(xl_n), int(yt_n), int(fw), int(fh))
            pygame.draw.rect(screen, body, r, border_radius=6)
            pygame.draw.rect(screen, shade(body, .66), (r.x, r.bottom - max(6, r.h // 4), r.w, max(6, r.h // 4)),
                             border_bottom_left_radius=6, border_bottom_right_radius=6)
            glass = self._fog(mix((190, 228, 250), (255, 224, 140), night * .5), zn)
            if bus:
                pygame.draw.rect(screen, (24, 26, 34), (r.x + r.w // 8, r.y + r.h // 14, r.w * 3 // 4, max(4, r.h // 9)))
                pygame.draw.rect(screen, (255, 190, 60), (r.x + r.w // 4, r.y + r.h // 14 + 2, r.w // 2, max(2, r.h // 9 - 4)))
                pygame.draw.rect(screen, glass, (r.x + r.w // 12, r.y + r.h // 4, r.w * 5 // 6, r.h * 2 // 5), border_radius=5)
            else:
                pygame.draw.rect(screen, (22, 24, 30), (r.x + r.w // 4, r.y + max(2, r.h // 40), r.w // 2, max(3, r.h // 11)),
                                 border_radius=2)
                pygame.draw.rect(screen, (255, 176, 40), (r.x + r.w // 4 + 2, r.y + max(2, r.h // 40) + 1,
                                                          r.w // 2 - 4, max(1, r.h // 11 - 2)))
                pygame.draw.rect(screen, glass, (r.x + r.w // 8, r.y + r.h // 8, r.w * 3 // 4, r.h * 3 // 8), border_radius=5)
                pygame.draw.line(screen, (120, 160, 190), (r.centerx, r.y + r.h // 8), (r.centerx, r.y + r.h // 2), 2)
            pygame.draw.rect(screen, self._fog(o.accent, zn), (r.x, r.y + r.h * 5 // 8, r.w, max(2, r.h // 14)))
            hr = max(2, r.w // 14)
            lit = night > .25 or o.vel > 0
            for hx in (r.x + r.w // 6, r.right - r.w // 6):
                hy = r.bottom - r.h // 6
                if lit:
                    pygame.draw.circle(screen, mix(body, (255, 244, 190), .30), (hx, hy), hr * 3)
                    pygame.draw.circle(screen, mix(body, (255, 244, 190), .65), (hx, hy), hr * 2)
                pygame.draw.circle(screen, (255, 245, 180), (hx, hy), hr)
            if o.vel > 0:                              # express train: hazard chevron band
                bw = max(4, r.w // 10)
                for xx in range(r.x, r.right, bw * 2):
                    pygame.draw.rect(screen, (250, 200, 40), (xx, r.bottom - max(5, r.h // 12), min(bw, r.right - xx), max(5, r.h // 12)))
            pygame.draw.rect(screen, outline, r, 2, border_radius=6)

    def _draw_barrier(self, screen, o):
        if o.z > 1.0 or o.z < Z_NEAR:
            return
        t = t_of(o.z)
        lw, s, yg = lw_of(t), s_of(t), y_of(t)
        cx = lane_x(o.lane, t)
        hw = .39 * lw
        leg = max(3, int(hw * 2 / 14))
        for lx in (cx - hw * .8, cx + hw * .8):
            pygame.draw.rect(screen, self._fog((90, 90, 100), o.z), (lx - leg // 2, yg - BARRIER_LOW * s, leg, BARRIER_LOW * s))
        board = pygame.Rect(int(cx - hw), int(yg - BARRIER_TOP * s), int(hw * 2), max(8, int((BARRIER_TOP - BARRIER_LOW) * s)))
        pygame.draw.rect(screen, self._fog((255, 255, 255), o.z), board, border_radius=4)
        sw = max(6, board.w // 8)
        for sx in range(board.x, board.right, sw * 2):
            pygame.draw.rect(screen, self._fog((232, 62, 58), o.z), (sx, board.y, min(sw, board.right - sx), board.h))
        pygame.draw.rect(screen, (50, 50, 60), board, 2, border_radius=4)

    def _draw_sign(self, screen, o):
        if o.z > 1.0 or o.z < Z_NEAR:
            return
        t = t_of(o.z)
        lw, s, yg = lw_of(t), s_of(t), y_of(t)
        cx = lane_x(o.lane, t)
        hw = .39 * lw
        base_h = 56 * s
        pygame.draw.rect(screen, self._fog((150, 152, 160), o.z), (cx - hw, yg - base_h, hw * 2, base_h), border_radius=4)
        for k in range(4):
            pygame.draw.line(screen, self._fog((250, 200, 40), o.z), (cx - hw + k * hw / 2, yg),
                             (cx - hw + k * hw / 2 + hw / 3, yg - base_h), max(2, int(6 * s)))
        for lx in (cx - hw * .7, cx + hw * .7):
            pygame.draw.rect(screen, self._fog((70, 70, 80), o.z), (lx - 3 * s, yg - 170 * s, 6 * s, 120 * s))
        board = pygame.Rect(int(cx - hw), int(yg - 175 * s), int(hw * 2), int(80 * s))
        pygame.draw.rect(screen, self._fog((236, 62, 58), o.z), board, border_radius=5)
        pygame.draw.rect(screen, (255, 255, 255), board.inflate(-8, -8), 3, border_radius=4)
        pygame.draw.line(screen, (255, 255, 255), (board.x + board.w // 5, board.centery),
                         (board.right - board.w // 5, board.centery), max(3, int(10 * s)))

    # -------- player
    def _draw_player(self, screen):
        p = self.player
        r = p.rect()
        x = r.centerx
        grounded = p.grounded()
        flying = p.flying
        sliding = p.slide > 0 and grounded
        floor_y = PLAYER_Y - p.support
        air = min(1.0, max(0.0, p.h - p.support) / 160)
        shadow_w = int(64 * (1 - air * .55))
        sh = pygame.Surface((shadow_w, 16), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, int(140 * (1 - air * .7))), (0, 0, shadow_w, 16))
        screen.blit(sh, (x - shadow_w // 2, floor_y - 3))
        if self.on_roof:
            pygame.draw.ellipse(screen, (255, 236, 150), (x - 34, floor_y - 7, 68, 14), 2)
        if (p.inv > 0 or p.ghost > 0) and int(self.elapsed * 16) % 2 == 0:
            return

        OL = (30, 26, 40)
        HOOD, HOOD_D = (236, 98, 52), (186, 66, 34)
        PANTS, SKIN, CAP, PACK = (52, 62, 108), (240, 190, 140), (58, 92, 214), (60, 190, 170)
        sway = int(p.lean * 7)
        if p.stumble > 0:
            sway += int(9 * math.sin(self.elapsed * 40) * min(1.0, p.stumble / .35))
        top, bottom = r.top, r.bottom
        ph = p.stride
        hx = x + sway
        if sliding:
            head_y, torso_top, torso_h, hip_y = top + 13, top + 22, 24, top + 42
        else:
            head_y, torso_top, torso_h, hip_y = top + 16, top + 31, 42, top + 70

        # legs
        for side in (-1, 1):
            phs = ph + (0 if side < 0 else math.pi)
            if sliding:
                foot, knee = (x + side * 14, bottom + 2), (x + side * 17, hip_y + 4)
            elif flying:
                foot = (x + side * 7, bottom + 6 + side * 3 * math.sin(self.elapsed * 9))
                knee = (x + side * 8, (hip_y + foot[1]) / 2)
            elif not grounded:
                foot, knee = (x + side * 10, bottom - 8 + side * 4), (x + side * 15, hip_y + 8)
            else:
                lift = max(0.0, math.sin(phs)) * 15
                foot = (x + side * 8, bottom + 4 - lift)
                knee = (x + side * (10 + lift * .25), (hip_y + foot[1]) / 2 - lift * .3)
            hip = (x + side * 8, hip_y)
            pygame.draw.line(screen, OL, hip, knee, 11)
            pygame.draw.line(screen, OL, knee, foot, 11)
            pygame.draw.line(screen, PANTS, hip, knee, 8)
            pygame.draw.line(screen, PANTS, knee, foot, 8)
            fx, fy = int(foot[0]), int(foot[1])
            if p.boots > 0:
                pygame.draw.circle(screen, (255, 225, 100), (fx, fy), 12, 2)
            pygame.draw.ellipse(screen, OL, (fx - 10, fy - 6, 20, 12))
            pygame.draw.ellipse(screen, (245, 245, 250), (fx - 8, fy - 5, 16, 9))
            pygame.draw.rect(screen, (230, 70, 60), (fx - 8, fy + 1, 16, 3), border_radius=1)

        # jetpack (behind body)
        if flying:
            for sx in (-12, 12):
                cx = hx + sx
                pygame.draw.rect(screen, OL, (cx - 7, torso_top + 2, 14, 32), border_radius=5)
                pygame.draw.rect(screen, (150, 156, 172), (cx - 5, torso_top + 4, 10, 28), border_radius=4)
                pygame.draw.rect(screen, (230, 70, 60), (cx - 5, torso_top + 10, 10, 5))
                fl = 16 + random.randint(0, 12)
                pygame.draw.polygon(screen, (255, 130, 40), [(cx - 5, torso_top + 34), (cx + 5, torso_top + 34), (cx, torso_top + 34 + fl)])
                pygame.draw.polygon(screen, (255, 226, 120), [(cx - 3, torso_top + 34), (cx + 3, torso_top + 34), (cx, torso_top + 34 + fl * .6)])

        # torso
        tr = pygame.Rect(x - 19 + sway // 2, torso_top, 38, torso_h)
        pygame.draw.rect(screen, OL, tr.inflate(4, 4), border_radius=12)
        pygame.draw.rect(screen, HOOD, tr, border_radius=11)
        pygame.draw.rect(screen, HOOD_D, (tr.x, tr.y, tr.w, 9), border_radius=8)
        pygame.draw.line(screen, HOOD_D, (tr.centerx, tr.y + 9), (tr.centerx, tr.bottom - 4), 2)

        # arms
        for side in (-1, 1):
            phs = ph + (math.pi if side < 0 else 0)
            sh_pt = (tr.centerx + side * 20, torso_top + 8)
            if flying:
                hand = (sh_pt[0] + side * 20, sh_pt[1] + 14)
            elif not grounded:
                hand = (sh_pt[0] + side * 8, sh_pt[1] - 26) if side > 0 else (sh_pt[0] + side * 14, sh_pt[1] + 12)
            elif sliding:
                hand = (sh_pt[0] + side * 12, sh_pt[1] + 14)
            else:
                sw = math.sin(phs)
                hand = (sh_pt[0] + side * (14 + 4 * abs(sw)), sh_pt[1] + 22 - sw * 7)
            elbow = ((sh_pt[0] + hand[0]) / 2 + side * 5, (sh_pt[1] + hand[1]) / 2)
            pygame.draw.line(screen, OL, sh_pt, elbow, 10)
            pygame.draw.line(screen, OL, elbow, hand, 10)
            pygame.draw.line(screen, HOOD, sh_pt, elbow, 7)
            pygame.draw.line(screen, HOOD, elbow, hand, 7)
            pygame.draw.circle(screen, SKIN, (int(hand[0]), int(hand[1])), 5)

        # backpack
        if not flying:
            pk = pygame.Rect(tr.centerx - 14, torso_top + 4, 28, max(14, torso_h - 14))
            pygame.draw.rect(screen, OL, pk.inflate(4, 4), border_radius=7)
            pygame.draw.rect(screen, PACK, pk, border_radius=6)
            pygame.draw.rect(screen, shade(PACK, .72), (pk.x + 4, pk.y + pk.h // 2, pk.w - 8, 4), border_radius=2)
            pygame.draw.line(screen, OL, (pk.x + 5, pk.y), (pk.x + 5, pk.y - 5), 3)
            pygame.draw.line(screen, OL, (pk.right - 5, pk.y), (pk.right - 5, pk.y - 5), 3)

        # head (seen from behind: cap + hair)
        pygame.draw.circle(screen, OL, (hx, head_y), 18)
        pygame.draw.circle(screen, SKIN, (hx, head_y), 16)
        pygame.draw.circle(screen, SKIN, (hx - 16, head_y + 3), 4)
        pygame.draw.circle(screen, SKIN, (hx + 16, head_y + 3), 4)
        pygame.draw.ellipse(screen, (70, 48, 34), (hx - 14, head_y - 4, 28, 20))
        pygame.draw.ellipse(screen, OL, (hx - 19, head_y - 22, 38, 28))
        pygame.draw.ellipse(screen, CAP, (hx - 17, head_y - 20, 34, 24))
        pygame.draw.rect(screen, (40, 62, 160), (hx - 6, head_y - 8, 12, 5), border_radius=2)
        pygame.draw.circle(screen, (235, 200, 60), (hx, head_y - 20), 3)

        # effects
        cy = r.top + 44
        if self.mag > 0:
            pygame.draw.circle(screen, (150, 190, 255), (x, cy), int(70 + 6 * math.sin(self.elapsed * 7)), 1)
        if p.shield > 0:
            pulse = 58 + int(5 * math.sin(self.elapsed * 10))
            pygame.draw.circle(screen, (90, 210, 255), (x, cy), pulse, 3)
            pygame.draw.circle(screen, (170, 235, 255), (x, cy), pulse - 9, 1)

    def _draw_chaser(self, screen):
        k = self.chase_k
        if k < 0.03:
            return
        p = self.player
        sc = 1.4
        by = int(PLAYER_Y + 70 + (1 - k) * 170)
        x = int(p.x + 4 * math.sin(self.elapsed * 3))
        ph = self.elapsed * 13
        OL = (24, 22, 34)
        NAVY, NAVY_D = (44, 70, 138), (30, 48, 98)
        self._draw_dog(screen, x - 96, by - 4, ph)
        for side in (-1, 1):
            phs = ph + (0 if side < 0 else math.pi)
            lift = max(0.0, math.sin(phs)) * 14 * sc
            hip = (x + side * int(9 * sc), by - int(40 * sc))
            foot = (x + side * int(10 * sc), by + 4 - int(lift))
            pygame.draw.line(screen, OL, hip, foot, int(15 * sc))
            pygame.draw.line(screen, NAVY_D, hip, foot, int(11 * sc))
            pygame.draw.ellipse(screen, OL, (foot[0] - int(13 * sc), foot[1] - 6, int(26 * sc), 14))
        tr = pygame.Rect(x - int(23 * sc), by - int(100 * sc), int(46 * sc), int(64 * sc))
        pygame.draw.rect(screen, OL, tr.inflate(6, 6), border_radius=14)
        pygame.draw.rect(screen, NAVY, tr, border_radius=13)
        pygame.draw.rect(screen, (250, 210, 60), (tr.x, tr.y + int(26 * sc), tr.w, int(6 * sc)))
        pygame.draw.rect(screen, (60, 60, 70), (tr.x, tr.bottom - int(12 * sc), tr.w, int(8 * sc)))
        for side in (-1, 1):
            phs = ph + (math.pi if side < 0 else 0)
            sh_pt = (tr.centerx + side * int(25 * sc), tr.y + int(10 * sc))
            hand = (sh_pt[0] + side * int(8 * sc), sh_pt[1] + int(30 * sc) - int(math.sin(phs) * 9))
            pygame.draw.line(screen, OL, sh_pt, hand, int(13 * sc))
            pygame.draw.line(screen, NAVY, sh_pt, hand, int(9 * sc))
            pygame.draw.circle(screen, (240, 190, 140), hand, int(6 * sc))
        hy = tr.y - int(12 * sc)
        pygame.draw.circle(screen, OL, (x, hy), int(18 * sc))
        pygame.draw.circle(screen, (240, 190, 140), (x, hy), int(16 * sc))
        pygame.draw.ellipse(screen, OL, (x - int(20 * sc), hy - int(22 * sc), int(40 * sc), int(28 * sc)))
        pygame.draw.ellipse(screen, NAVY, (x - int(18 * sc), hy - int(20 * sc), int(36 * sc), int(24 * sc)))
        pygame.draw.circle(screen, (250, 210, 60), (x, hy - int(18 * sc)), 4)

    def _draw_dog(self, screen, x, y, ph):
        OL = (24, 22, 34)
        FUR, FUR_D = (170, 116, 66), (122, 80, 46)
        bob = int(3 * math.sin(ph * 2))
        for side in (-1, 1):
            phs = ph + (0 if side < 0 else math.pi)
            lift = max(0.0, math.sin(phs)) * 13
            a, b = (x + side * 15, y - 28 + bob), (x + side * 17, int(y + 2 - lift))
            pygame.draw.line(screen, OL, a, b, 12)
            pygame.draw.line(screen, FUR_D, a, b, 8)
        pygame.draw.ellipse(screen, OL, (x - 31, y - 58 + bob, 62, 42))
        pygame.draw.ellipse(screen, FUR, (x - 29, y - 56 + bob, 58, 38))
        pygame.draw.ellipse(screen, FUR_D, (x - 20, y - 56 + bob, 40, 14))
        pygame.draw.circle(screen, (220, 60, 60), (x, y - 52 + bob), 5)
        tw = int(11 * math.sin(ph * 2.3))
        pygame.draw.line(screen, OL, (x, y - 36 + bob), (x + tw, y - 20 + bob), 10)
        pygame.draw.line(screen, FUR, (x, y - 36 + bob), (x + tw, y - 20 + bob), 6)
        for ex in (-12, 12):
            pygame.draw.polygon(screen, FUR_D, [(x + ex - 6, y - 60 + bob), (x + ex + 6, y - 60 + bob), (x + ex, y - 74 + bob)])

    # -------- pickups / effects
    def _pu_icon(self, screen, kind, cx, cy, r):
        W_ = (255, 255, 255)
        w = max(2, r // 4)
        if kind == "magnet":
            rr = max(3, int(r * .42))
            pygame.draw.arc(screen, W_, (cx - rr, cy - rr + int(r * .1), 2 * rr, 2 * rr), math.pi, math.tau, w)
            for sx in (-1, 1):
                x0 = cx + sx * rr
                y0 = cy + int(r * .1)
                pygame.draw.line(screen, W_, (x0, y0), (x0, y0 - int(r * .35)), w)
                pygame.draw.line(screen, (230, 50, 50), (x0, y0 - int(r * .35)), (x0, y0 - int(r * .6)), w)
        elif kind == "x2":
            f = self._font(max(10, int(r * 1.15)))
            t = f.render("2x", True, W_)
            screen.blit(t, t.get_rect(center=(cx, cy)))
        elif kind == "jet":
            body = [(cx, cy - r * .62), (cx + r * .26, cy - r * .1), (cx + r * .26, cy + r * .3),
                    (cx - r * .26, cy + r * .3), (cx - r * .26, cy - r * .1)]
            pygame.draw.polygon(screen, W_, body)
            pygame.draw.polygon(screen, (255, 150, 40), [(cx - r * .16, cy + r * .3), (cx + r * .16, cy + r * .3), (cx, cy + r * .72)])
            pygame.draw.circle(screen, (70, 160, 255), (int(cx), int(cy - r * .12)), max(2, int(r * .12)))
        elif kind == "boots":
            shoe = [(cx - r * .5, cy + r * .38), (cx - r * .5, cy - r * .5), (cx - r * .1, cy - r * .5),
                    (cx - r * .05, cy - r * .05), (cx + r * .55, cy + r * .12), (cx + r * .55, cy + r * .38)]
            pygame.draw.polygon(screen, W_, shoe)
            pygame.draw.line(screen, (255, 200, 60), (cx - r * .5, cy + r * .24), (cx + r * .55, cy + r * .24), max(2, r // 6))

    def _draw_pu(self, screen, o):
        if o.z > 1.0 or o.z < Z_NEAR or o.hit:
            return
        bob = 7 * math.sin(self.elapsed * 4 + o.var * 6)
        x, y = self._screen_pos(o.lane, o.z, o.h + 26 + bob)
        t = t_of(o.z)
        r = max(8, int(10 + 22 * s_of(t)))
        col = PU_COLORS.get(o.ptype, (255, 255, 255))
        gy = y_of(t)
        if o.h < 60:
            pygame.draw.ellipse(screen, shade(self._tone((168, 150, 120)), .7), (x - r, int(gy) - 4, r * 2, 8))
        pulse = 4 + int(3 * math.sin(self.elapsed * 6))
        pygame.draw.circle(screen, self._fog(shade(col, .5), o.z), (x, y), r + pulse, 2)
        pygame.draw.circle(screen, self._fog(shade(col, .55), o.z), (x, y), r + 4)
        pygame.draw.circle(screen, self._fog(col, o.z), (x, y), r)
        pygame.draw.circle(screen, (255, 255, 255), (x, y), r, max(2, r // 7))
        self._pu_icon(screen, o.ptype, x, y, r)

    def _speed_lines(self, screen):
        sp = clamp((self.speed - START_SPEED) / (MAX_SPEED * 1.4 - START_SPEED))
        if sp < .12 and self.jet <= 0:
            return
        n = int(4 + 14 * sp) + (8 if self.jet > 0 else 0)
        ph0 = self.elapsed * (1.4 + 1.6 * sp)
        for i in range(n):
            ph = (ph0 + hsh(i, 11)) % 1.0
            if i % 2 == 0:
                tx, ty = -150 + hsh(i, 3) * 320, 330 + hsh(i, 4) * 420
            else:
                tx, ty = W + 150 - hsh(i, 3) * 320, 330 + hsh(i, 4) * 420
            a, b = ph ** 1.6, min(1.25, ph ** 1.6 + .10 + .10 * sp)
            p0 = (CX + (tx - CX) * a, HORIZON + (ty - HORIZON) * a)
            p1 = (CX + (tx - CX) * b, HORIZON + (ty - HORIZON) * b)
            c = mix(self.env_bot, (255, 255, 255), .25 + .45 * ph)
            pygame.draw.line(screen, c, p0, p1, 1 + int(ph * 2))

    def _hud_powerups(self, screen):
        f_xs = self._font(12, False)
        p = self.player
        y = 180
        for kind, left, total in (("jet", self.jet, JET_TIME), ("magnet", self.mag, MAG_TIME),
                                  ("x2", self.mult_t, X2_TIME), ("boots", p.boots, BOOT_TIME)):
            if left <= 0:
                continue
            c = PU_COLORS[kind]
            self._glass(screen, (16, y, 176, 34), radius=17, border=(c[0], c[1], c[2], 150))
            pygame.draw.circle(screen, c, (34, y + 17), 13)
            self._pu_icon(screen, kind, 34, y + 17, 13)
            self._text(screen, f_xs, PU_NAMES[kind], 54, y + 3, (230, 238, 250))
            pygame.draw.rect(screen, (30, 40, 60), (54, y + 20, 128, 7), border_radius=3)
            pygame.draw.rect(screen, c, (54, y + 20, max(2, int(128 * clamp(left / total))), 7), border_radius=3)
            y += 40
        # shield charges (two fingers / E)
        self._glass(screen, (16, H - 92, 176, 38), radius=16)
        self._text(screen, f_xs, "SHIELD  (2 fingers / E)", 28, H - 90, (150, 225, 255))
        for i in range(3):
            c = (90, 210, 255) if i < self.charges else (60, 72, 100)
            cx = 36 + i * 26
            pygame.draw.polygon(screen, c, [(cx, H - 76), (cx + 9, H - 72), (cx + 7, H - 62), (cx, H - 58), (cx - 7, H - 62), (cx - 9, H - 72)])
        if self.chase > 0:
            cx = W // 2
            self._glass(screen, (cx - 130, 88, 260, 30), radius=14, border=(255, 90, 80, 170))
            pulse = .5 + .5 * math.sin(self.elapsed * 9)
            self._text(screen, f_xs, "CHASED!  TRIP AGAIN AND YOU'RE CAUGHT", cx, 91, (255, int(130 + 90 * pulse), 100), center=True)
            pygame.draw.rect(screen, (60, 30, 36), (cx - 118, 109, 236, 5), border_radius=2)
            pygame.draw.rect(screen, (255, 90, 80), (cx - 118, 109, max(2, int(236 * self.chase / CHASE_TIME)), 5), border_radius=2)

    # ----------------------------------------------------------------- HUD ---
    def _glass(self, screen, rect, radius=14, color=(10, 16, 34, 170), border=(255, 255, 255, 38)):
        rect = pygame.Rect(rect)
        gk = (rect.size, radius, tuple(color), tuple(border) if border else None)
        s = self._glass_cache.get(gk)
        if s is None:
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(s, color, s.get_rect(), border_radius=radius)
            if border:
                pygame.draw.rect(s, border, s.get_rect(), 2, border_radius=radius)
            if len(self._glass_cache) > 120:
                self._glass_cache.clear()
            self._glass_cache[gk] = s = s.convert_alpha()
        screen.blit(s, rect.topleft)

    _panel = _glass

    def _text(self, screen, font, text, x, y, color=(255, 255, 255), center=False, alpha=255, right=False):
        tk = (id(font), text, tuple(color))
        pair = self._text_cache.get(tk)
        if pair is None:
            if len(self._text_cache) > 300:
                self._text_cache.clear()
            pair = self._text_cache[tk] = (font.render(text, True, (0, 0, 0)).convert_alpha(),
                                           font.render(text, True, color).convert_alpha())
        sh, fg = pair
        sh.set_alpha(int(alpha * 0.45))
        fg.set_alpha(alpha)
        if center:
            x -= fg.get_width() // 2
        elif right:
            x -= fg.get_width()
        screen.blit(sh, (x + 2, y + 2))
        screen.blit(fg, (x, y))

    def _coin_icon(self, screen, cx, cy, r):
        pygame.draw.circle(screen, (150, 110, 20), (cx, cy + 1), r + 2)
        pygame.draw.circle(screen, COIN_GOLD, (cx, cy), r)
        pygame.draw.circle(screen, COIN_LIGHT, (cx, cy), r, 2)
        pygame.draw.rect(screen, (190, 140, 20), (cx - 2, cy - r // 2, 4, r), border_radius=2)

    def _hud(self, screen, gesture, event, voice, camera):
        f_big, f_med = self._font(30), self._font(18)
        f_sm, f_xs = self._font(13), self._font(12, False)
        label = (160, 182, 216)

        # coins
        self._glass(screen, (16, 14, 176, 48), radius=24)
        self._coin_icon(screen, 42, 38, 15)
        self._text(screen, f_big, str(self.coins), 68, 22)
        # score
        self._glass(screen, (16, 70, 176, 62))
        self._text(screen, f_xs, "SCORE", 30, 78, label)
        self._text(screen, self._font(32), f"{int(self.score)}", 30, 92, (255, 226, 130))
        # distance
        self._glass(screen, (16, 140, 176, 30), radius=12)
        self._text(screen, f_xs, "DISTANCE", 28, 147, label)
        self._text(screen, f_med, f"{int(self.distance)} m", 180, 144, (255, 255, 255), right=True)

        # level + speed
        cx = W // 2
        self._glass(screen, (cx - 160, 14, 320, 66), radius=18)
        self._text(screen, f_med, f"LEVEL {self.level}", cx - 140, 22)
        kmh = int(60 + self.progress * 140)
        self._text(screen, f_med, f"{kmh} km/h", cx + 140, 22, (110, 220, 255), right=True)
        bar = pygame.Rect(cx - 140, 52, 280, 12)
        pygame.draw.rect(screen, (34, 44, 70), bar, border_radius=6)
        fill = int(bar.width * max(0.04, min(1.0, self.progress)))
        if self._bar_grad is None:
            g = pygame.Surface((bar.width, bar.height - 3))
            for i in range(bar.width):
                pygame.draw.line(g, mix((90, 225, 140), (255, 90, 80), i / bar.width), (i, 0), (i, g.get_height()))
            self._bar_grad = g
        screen.blit(self._bar_grad, (bar.x, bar.y + 1), area=(0, 0, fill, bar.height - 3))
        pygame.draw.rect(screen, (255, 255, 255, 60), bar, 1, border_radius=6)

        # pause button (application.py hit-tests pause_button_rect)
        self.pause_button_rect = pygame.Rect(W - 66, 18, 48, 48)
        pr = self.pause_button_rect
        self._glass(screen, pr, radius=24)
        pygame.draw.circle(screen, (255, 255, 255), pr.center, 24, 3)
        pygame.draw.rect(screen, (255, 255, 255), (pr.centerx - 9, pr.centery - 10, 6, 20), border_radius=2)
        pygame.draw.rect(screen, (255, 255, 255), (pr.centerx + 3, pr.centery - 10, 6, 20), border_radius=2)

        ry = 78
        if self.player.shield > 0:
            self._glass(screen, (W - 216, ry, 200, 36), radius=14)
            self._text(screen, f_xs, "SHIELD", W - 204, ry + 4, (150, 225, 255))
            pygame.draw.rect(screen, (30, 40, 60), (W - 204, ry + 22, 176, 8), border_radius=4)
            pygame.draw.rect(screen, (90, 210, 255), (W - 204, ry + 22, int(176 * min(1, self.player.shield / 5)), 8), border_radius=4)
            ry += 44
        if self.on_roof:
            self._glass(screen, (W - 216, ry, 200, 36), radius=14, border=(255, 214, 90, 120))
            self._text(screen, f_xs, "TRAIN SURF", W - 204, ry + 4, (255, 214, 90))
            self._text(screen, f_med, f"+{int(self.surf_time * 40)}", W - 28, ry + 8, (255, 255, 255), right=True)

        self._hud_powerups(screen)

        # lane indicator (handy for gesture control)
        for i in range(3):
            r = pygame.Rect(cx - 66 + i * 46, H - 38, 40, 10)
            on = self.player.target == i
            pygame.draw.rect(screen, (255, 214, 90) if on else (255, 255, 255, 60), r, border_radius=5)
            if not on:
                pygame.draw.rect(screen, (20, 28, 50), r, 1, border_radius=5)

        t = self.elapsed
        if t < 3.4:
            a = 255 if t < 2.4 else int(255 * max(0.0, 1 - (t - 2.4)))
            self._text(screen, self._font(64), "GET READY", W // 2, 250, (255, 235, 150), center=True, alpha=a)
            self._text(screen, f_med, "starts slow - speed builds up as you run", W // 2, 326, (255, 255, 255), center=True, alpha=a)
            self._text(screen, f_med, "jump onto trains and buses to surf on the roof", W // 2, 354, (150, 225, 255), center=True, alpha=a)
        if t < 10:
            a = 255 if t < 8 else int(255 * max(0.0, (10 - t) / 2))
            self._glass(screen, (W // 2 - 300, 92, 600, 36), radius=18, color=(12, 18, 34, int(150 * a / 255)))
            self._text(screen, f_sm, "LEFT / RIGHT = move     UP = jump     DOWN = slide / dive     P = pause",
                       W // 2, 101, (230, 238, 250), center=True, alpha=a)
        if self.banner:
            txt, life = self.banner
            a = int(255 * min(1.0, life / 0.5))
            self._text(screen, self._font(44), txt, W // 2, 130, (255, 210, 90), center=True, alpha=a)

        # gesture chip
        has = gesture not in ("NO_HAND", "NO_CAMERA", None)
        self._glass(screen, (14, H - 44, 330, 30), radius=15)
        pygame.draw.circle(screen, (90, 230, 140) if has else (200, 90, 90), (32, H - 29), 6)
        screen.blit(f_sm.render(f"hand: {gesture}   event: {event}", True, (225, 230, 240)), (46, H - 36))

        if camera is not None:
            try:
                if camera is not self._cam_src:
                    self._cam_src = camera
                    small = camera[::4, ::4, ::-1]
                    self._cam_surf = pygame.surfarray.make_surface(small.swapaxes(0, 1)).convert()
                surf = self._cam_surf
                fr = pygame.Rect(W - 180, H - 144, 160, 120)
                self._glass(screen, fr.inflate(10, 10), radius=10)
                screen.blit(surf, fr.topleft)
                pygame.draw.rect(screen, (90, 200, 255), fr, 2)
            except Exception:
                pass
