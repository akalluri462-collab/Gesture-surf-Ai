import time
import math
import threading
from collections import deque
import cv2
import mediapipe as mp


class HandTracker:
    """
    Camera + MediaPipe on a background thread, with robust motion gestures.

    Fixes vs the old version:
    1. Motion is measured in HAND-SIZES (wrist->middle knuckle), not raw
       screen fractions. So it feels the same whether you sit close or far.
    2. Motion window is TIME based (last ~0.28s), not "last 8 frames", so
       low/high FPS doesn't change how sensitive it is.
    3. Pixel-space (x*w, y*h) so horizontal and vertical are comparable
       (the old code mixed 640-wide x with 480-tall y).
    4. Return-stroke suppression: after JUMP, your hand coming back down
       no longer fires SLIDE (and LEFT -> RIGHT the same way).
    5. History is cleared after each event + hand loss, so one motion = one
       event and stale samples never trigger anything.
    6. FIST / PALM / TWO_FINGERS fire ONCE when the pose is held, not
       repeatedly every 0.15s.
    """

    # ---- tuning (all in hand-sizes / seconds) ----
    # Two look-back windows: a short one catches fast flicks quickly, a long
    # one catches slower deliberate moves that the short one would miss.
    WINDOWS = ((0.14, 1.30), (0.30, 0.95))   # (seconds, min hand-sizes/sec)
    HIST_KEEP = 0.32       # how much history to store
    MIN_SPAN = 0.04        # need at least this much time of samples
    LOST_GRACE = 0.25      # hand may vanish this long (motion blur) without losing the swipe
    TAU_SLOW = 0.045       # smoothing time-constant when the hand is still (kills jitter)
    TAU_FAST = 0.010       # ...and when it moves fast (no lag on swipes)
    H_DIST = 0.50          # lane change distance
    UP_DIST = 0.36         # jump distance (easier than slide on purpose)
    DOWN_DIST = 0.50       # slide distance
    AXIS_RATIO = 1.15      # dominant axis must beat other axis by this
    LOCKOUT = 0.14         # global cooldown after any motion event
    RETURN_BLOCK = 0.30    # ignore opposite-direction return stroke
    POSE_HOLD = 0.35       # seconds a pose must be held to fire
    FIST_HOLD = 0.70       # pause needs a longer, deliberate fist (no accidental pauses)
    POSE_AFTER_MOVE = 0.40 # ignore poses right after a swipe (hand often curls)

    def __init__(self, index=0, sensitivity=1.25):
        """sensitivity > 1 = easier to trigger, < 1 = harder."""
        self.sensitivity = sensitivity
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        try:                                   # ask for a faster, lower-latency stream
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self.cap.set(cv2.CAP_PROP_FPS, 60)
        except Exception:
            pass
        if not self.cap.isOpened():
            raise RuntimeError(f"could not open camera index {index}")

        self.hands = mp.solutions.hands.Hands(
            static_image_mode=False, max_num_hands=1, model_complexity=0,
            min_detection_confidence=.4, min_tracking_confidence=.4)
        self.drawer = mp.solutions.drawing_utils

        self.hist = deque()            # (t, x_px, y_px, scale_px)
        self.lockout_until = 0.0
        self.last_motion = None        # (event, time)
        self.scale_ema = None
        self.pos_ema = None
        self.lost_at = None            # when the hand disappeared (None = visible)
        self.last_t = None

        self.pose_candidate = "NO_HAND"
        self.pose_since = 0.0
        self.pose_fired = "NO_HAND"

        self._lock = threading.Lock()
        self._frame = None
        self._info = {"gesture": "NO_HAND", "event": None}
        self._events = deque(maxlen=8)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ---------- pose ----------
    def pose(self, lm):
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        fingers = [lm[t].y < lm[p].y for t, p in zip(tips, pips)]
        thumb = abs(lm[4].x - lm[2].x) > .08
        n = sum(fingers) + int(thumb)
        if n >= 4:
            return "OPEN_PALM"
        if n <= 1:
            return "FIST"
        if fingers[0] and fingers[1] and not fingers[2] and not fingers[3]:
            return "TWO_FINGERS"
        if fingers[0] and not fingers[1] and not fingers[2] and not fingers[3]:
            return "POINT"
        return "UNKNOWN"

    # ---------- motion ----------
    def _classify(self, dx, dy):
        k = 1.0 / max(self.sensitivity, .1)
        adx, ady = abs(dx), abs(dy)
        if adx > self.H_DIST * k and adx > ady * self.AXIS_RATIO:
            return "LEFT" if dx < 0 else "RIGHT"
        if dy < -self.UP_DIST * k and ady > adx * self.AXIS_RATIO:
            return "JUMP"
        if dy > self.DOWN_DIST * k and ady > adx * self.AXIS_RATIO:
            return "SLIDE"
        return None

    def _motion(self, now, x, y, scale):
        """Returns (event_or_None, speed_in_hand_sizes_per_sec)."""
        self.hist.append((now, x, y, scale))
        while self.hist and now - self.hist[0][0] > self.HIST_KEEP:
            self.hist.popleft()
        if len(self.hist) < 3:
            return None, 0.0

        t1, x1, y1, s1 = self.hist[-1]
        s = max(s1, 20.0)                     # avoid divide by tiny scale
        ev = None
        best_speed = 0.0
        for window, min_speed in self.WINDOWS:
            # oldest sample that is still inside this window
            base = None
            for smp in self.hist:
                if t1 - smp[0] <= window:
                    base = smp
                    break
            if base is None or base is self.hist[-1]:
                continue
            t0, x0, y0, _ = base
            span = t1 - t0
            if span < self.MIN_SPAN:
                continue
            dx, dy = (x1 - x0) / s, (y1 - y0) / s
            speed = math.hypot(dx, dy) / span
            best_speed = max(best_speed, speed)
            if ev is None and speed >= min_speed:
                ev = self._classify(dx, dy)

        if now < self.lockout_until or ev is None:
            return None, best_speed

        # Return-stroke suppression (hand coming back to centre).
        opposite = {"JUMP": "SLIDE", "SLIDE": "JUMP",
                    "LEFT": "RIGHT", "RIGHT": "LEFT"}
        if self.last_motion:
            le, lt = self.last_motion
            if opposite[ev] == le and now - lt < self.RETURN_BLOCK:
                self.hist.clear()
                self.lockout_until = now + self.LOCKOUT
                return None, best_speed

        self.last_motion = (ev, now)
        self.lockout_until = now + self.LOCKOUT
        self.hist.clear()                     # one motion = one event
        return ev, best_speed

    # ---------- stable pose events ----------
    def _pose_event(self, now, gesture, speed):
        if gesture != self.pose_candidate:
            self.pose_candidate = gesture
            self.pose_since = now
            return None
        held = now - self.pose_since
        # Leaving a pose for a moment re-arms it (old code needed a different
        # pose to FIRE first, so a 2nd shield gesture was silently ignored).
        if self.pose_fired is not None and gesture != self.pose_fired and held >= 0.15:
            self.pose_fired = None
        need = self.FIST_HOLD if gesture == "FIST" else self.POSE_HOLD
        if gesture == self.pose_fired or held < need:
            return None
        if speed > 1.0:                       # hand is mid-swipe, ignore
            return None
        if self.last_motion and now - self.last_motion[1] < self.POSE_AFTER_MOVE:
            return None
        self.pose_fired = gesture
        return {"FIST": "PAUSE", "OPEN_PALM": "RESUME",
                "TWO_FINGERS": "POWER"}.get(gesture)

    # ---------- thread ----------
    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                with self._lock:
                    self._info = {"gesture": "NO_CAMERA", "event": None}
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            now = time.time()
            res = self.hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            gesture = "NO_HAND"
            event = None

            if res.multi_hand_landmarks:
                hand = res.multi_hand_landmarks[0]
                lm = hand.landmark
                gesture = self.pose(lm)

                # palm centre (more stable than a single landmark), in pixels
                ids = (0, 5, 9, 13, 17)
                cx = sum(lm[i].x for i in ids) / len(ids) * w
                cy = sum(lm[i].y for i in ids) / len(ids) * h
                sc = math.hypot((lm[9].x - lm[0].x) * w, (lm[9].y - lm[0].y) * h)

                self.lost_at = None
                # Adaptive, TIME-based smoothing (same feel at 15 or 60 fps):
                # heavy when the hand is still (no jitter), almost none when
                # it moves fast (no lag on a swipe).
                if self.pos_ema is None:
                    self.pos_ema = (cx, cy)
                    self.scale_ema = sc
                else:
                    dt = max(1e-3, min(0.2, now - (self.last_t or now)))
                    raw = math.hypot(cx - self.pos_ema[0], cy - self.pos_ema[1])
                    v = raw / max(self.scale_ema, 20.0) / dt        # hand-sizes/sec
                    beta = min(1.0, v / 3.0)
                    tau = self.TAU_SLOW + (self.TAU_FAST - self.TAU_SLOW) * beta
                    a = 1.0 - math.exp(-dt / tau)
                    self.pos_ema = (self.pos_ema[0] + a * (cx - self.pos_ema[0]),
                                    self.pos_ema[1] + a * (cy - self.pos_ema[1]))
                    self.scale_ema = 0.3 * sc + 0.7 * self.scale_ema
                self.last_t = now

                ev, speed = self._motion(now, self.pos_ema[0], self.pos_ema[1],
                                         self.scale_ema)
                event = ev or self._pose_event(now, gesture, speed)
                self.drawer.draw_landmarks(
                    frame, hand, mp.solutions.hands.HAND_CONNECTIONS)
            else:
                # Fast swipes blur the hand and MediaPipe drops it for a few
                # frames. Do NOT wipe the swipe straight away - give it a
                # short grace so the motion still completes when it returns.
                if self.lost_at is None:
                    self.lost_at = now
                if now - self.lost_at > self.LOST_GRACE:
                    self.hist.clear()
                    self.pos_ema = None
                    self.scale_ema = None
                    self.last_t = None
                    self.pose_candidate = "NO_HAND"
                    self.pose_fired = "NO_HAND"

            with self._lock:
                self._frame = frame
                self._info = {"gesture": gesture, "event": None}
                if event:
                    self._events.append(event)

    def read(self):
        """Non-blocking: latest frame + info; one queued event per call."""
        with self._lock:
            frame = self._frame
            info = dict(self._info)
            info["event"] = self._events.popleft() if self._events else None
        return frame, info

    def release(self):
        self._running = False
        self._thread.join(timeout=1.0)
        self.cap.release()
        self.hands.close()
