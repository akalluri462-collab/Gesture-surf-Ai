import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import ScoreDB
from nlp.command_parser import parse_command


class T(unittest.TestCase):
    def test_db(self):
        with tempfile.TemporaryDirectory() as d:
            db = ScoreDB(os.path.join(d, "t.db"))
            db.add("a", 10, 1); db.add("b", 50, 3)
            self.assertEqual(db.top(1)[0]["name"], "b")
            self.assertEqual(db.stats()["games"], 2)

    def test_parser(self):
        for txt, want in [("go left", "LEFT"), ("jump", "JUMP"), ("start game", "START"),
                          ("pause", "PAUSE"), ("blah", "UNKNOWN")]:
            self.assertEqual(parse_command(txt)["intent"], want)


if __name__ == "__main__":
    unittest.main()
