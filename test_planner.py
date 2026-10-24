import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from planner import Board, render_svg, solve

ROOT = Path(__file__).parent


def board(grid):
    return Board.parse({"grid": grid})


class PlannerTests(unittest.TestCase):
    def test_key_requires_revisiting_position(self):
        b = Board.parse(json.loads((ROOT / "maps/key-door.json").read_text()))
        r = solve(b)
        self.assertEqual((r["status"], r["cost"]), ("solved", 9))
        self.assertIn("a", r["keys"])
        self.assertGreater(r["path"].count([1, 1]), 1)

    def test_high_hazard_cost_prefers_longer_route(self):
        b = Board.parse(json.loads((ROOT / "maps/hazards.json").read_text()))
        r = solve(b, hazard_cost=5)
        self.assertEqual(r["cost"], 7)
        self.assertFalse(any(b.grid[y][x] == "!" for x, y in r["path"]))

    def test_low_hazard_cost_takes_shortcut(self):
        b = Board.parse(json.loads((ROOT / "maps/hazards.json").read_text()))
        r = solve(b, hazard_cost=1)
        self.assertEqual((r["cost"], len(r["actions"])), (5, 5))

    def test_unreachable(self):
        self.assertEqual(solve(board(["SAG"]))["status"], "unreachable")

    def test_budget_is_not_unreachable(self):
        r = solve(board(["S...G"]), max_states=1)
        self.assertEqual((r["status"], r["expanded"]), ("budget_exceeded", 1))

    def test_bounds_without_border_walls(self):
        r = solve(board(["S.", ".G"]))
        self.assertEqual(r["cost"], 2)

    def test_multiple_keys_and_doors(self):
        r = solve(board(["SaAbBG"]))
        self.assertEqual((r["cost"], r["keys"]), (5, ["a", "b"]))

    def test_actions_replay_legally(self):
        b = Board.parse(json.loads((ROOT / "maps/key-door.json").read_text()))
        r = solve(b)
        x, y = b.start
        keys, total = set(), 0
        for action in r["actions"]:
            nx, ny = action["to"]
            self.assertEqual(abs(nx-x) + abs(ny-y), 1)
            tile = b.grid[ny][nx]
            self.assertNotEqual(tile, "#")
            if tile in "ABCDEF":
                self.assertIn(tile.lower(), keys)
            if tile in "abcdef":
                keys.add(tile)
            total += action["cost"]
            x, y = nx, ny
        self.assertEqual((x, y), b.goal)
        self.assertEqual(total, r["cost"])

    def test_invalid_maps(self):
        for grid in [[], ["SSG"], ["S"], ["SXG"], ["S..", "..G."], ["S", 3]]:
            with self.assertRaises(ValueError):
                board(grid)

    def test_invalid_parameters(self):
        for cost, limit in [(0, 10), (True, 10), (1, 0), (1, 200001)]:
            with self.assertRaises(ValueError):
                solve(board(["SG"]), cost, limit)

    def test_svg_is_valid_and_escapes_title(self):
        b = Board.parse({"name": "<script>alert(1)</script>", "grid": ["SG"]})
        svg = render_svg(b, solve(b))
        ET.fromstring(svg)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_cli_exports_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            svg = Path(directory) / "route.svg"
            run = subprocess.run([sys.executable, str(ROOT / "planner.py"), "--svg", str(svg)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["cost"], 9)
            ET.parse(svg)
            blocked = subprocess.run([sys.executable, str(ROOT / "planner.py"),
                                      str(ROOT / "maps/unreachable.json")], capture_output=True)
            self.assertEqual(blocked.returncode, 1)
            budget = subprocess.run([sys.executable, str(ROOT / "planner.py"),
                                     "--max-states", "1"], capture_output=True)
            self.assertEqual(budget.returncode, 3)

    def test_cli_protects_input(self):
        source = ROOT / "maps/key-door.json"
        before = source.read_bytes()
        run = subprocess.run([sys.executable, str(ROOT / "planner.py"), str(source),
                              "--json", str(source)], capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
