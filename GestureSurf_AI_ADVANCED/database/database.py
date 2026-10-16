import sqlite3
from contextlib import closing
from pathlib import Path


class ScoreDB:
    """SQLite high-score store. Never raises into the game loop."""

    def __init__(self, path="gesturesurf.db"):
        self.path = Path(path)
        try:
            with closing(sqlite3.connect(self.path)) as c, c:
                c.execute("""CREATE TABLE IF NOT EXISTS scores(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    coins INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        except sqlite3.Error:
            pass

    def add(self, name, score, coins):
        try:
            with closing(sqlite3.connect(self.path)) as c, c:
                c.execute("INSERT INTO scores(name,score,coins) VALUES(?,?,?)",
                          (name, int(score), int(coins)))
        except sqlite3.Error:
            pass

    def top(self, n=8):
        try:
            with closing(sqlite3.connect(self.path)) as c:
                c.row_factory = sqlite3.Row
                rows = c.execute("SELECT name,score,coins,created_at FROM scores "
                                 "ORDER BY score DESC LIMIT ?", (n,)).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def stats(self):
        """Games played, best score, total coins."""
        try:
            with closing(sqlite3.connect(self.path)) as c:
                g, b, t = c.execute("SELECT COUNT(*), COALESCE(MAX(score),0), "
                                    "COALESCE(SUM(coins),0) FROM scores").fetchone()
                return {"games": g, "best": b, "coins": t}
        except sqlite3.Error:
            return {"games": 0, "best": 0, "coins": 0}
