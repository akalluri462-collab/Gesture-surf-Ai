"""Tiny procedural sound effects (no audio files needed).

Everything is synthesised with numpy at start-up. If the mixer or numpy is
unavailable the class silently turns into a no-op, so the game never crashes
because of audio.
"""
import pygame

try:
    import numpy as np
except Exception:          # numpy missing -> silent game
    np = None


class Sfx:
    def __init__(self, volume=0.5):
        self.sounds = {}
        self.ok = False
        self.volume = volume
        if np is None:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            init = pygame.mixer.get_init()
            if not init:
                return
            self.rate, fmt, self.ch = init
            if fmt != -16:                 # we generate signed 16-bit audio
                return
            self._build()
            self.ok = True
        except Exception:
            self.ok = False
            self.sounds = {}

    # ------------------------------------------------------------ helpers --
    def _t(self, dur):
        return np.linspace(0, dur, max(1, int(self.rate * dur)), endpoint=False)

    def _tone(self, f0, f1, dur, decay=8.0, square=False):
        t = self._t(dur)
        f = f0 + (f1 - f0) * (t / dur)
        w = np.sin(2 * np.pi * np.cumsum(f) / self.rate)
        if square:
            w = np.sign(w) * 0.6
        env = np.minimum(1.0, t / 0.004) * np.exp(-t * decay)
        return w * env

    def _noise(self, dur, smooth=1, decay=10.0):
        t = self._t(dur)
        n = np.random.uniform(-1, 1, len(t))
        if smooth > 1:
            n = np.convolve(n, np.ones(smooth) / smooth, mode="same")
        return n * np.minimum(1.0, t / 0.004) * np.exp(-t * decay)

    def _snd(self, wave):
        data = (np.clip(wave, -1, 1) * 32767 * self.volume).astype(np.int16)
        if self.ch == 2:
            data = np.column_stack((data, data))
        elif self.ch > 2:
            data = np.repeat(data[:, None], self.ch, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(data))

    def _build(self):
        cat = np.concatenate
        self.sounds["coin"] = self._snd(cat([self._tone(988, 988, .05, 6), self._tone(1319, 1319, .18, 9)]))
        self.sounds["jump"] = self._snd(self._tone(300, 760, .20, 7))
        self.sounds["land"] = self._snd(self._tone(130, 55, .12, 22) + 0.4 * self._noise(.12, 6, 30))
        self.sounds["slide"] = self._snd(0.7 * self._noise(.24, 10, 9))
        self.sounds["lane"] = self._snd(0.45 * self._noise(.09, 14, 24))
        self.sounds["stumble"] = self._snd(self._tone(240, 80, .32, 6, square=True))
        crash = self._noise(.55, 5, 5)
        low = self._tone(150, 38, .55, 5)
        self.sounds["crash"] = self._snd(0.8 * crash + 0.8 * low)
        arp = [self._tone(f, f, .07, 10) for f in (523, 659, 784, 1047)]
        self.sounds["power"] = self._snd(cat(arp))

    # ---------------------------------------------------------------- api --
    def play(self, name):
        if not self.ok:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            try:
                snd.play()
            except Exception:
                pass
