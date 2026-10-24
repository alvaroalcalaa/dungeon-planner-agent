"""Inventory-aware A* planner for small deterministic dungeon maps."""
import argparse
import heapq
import html
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

SYMBOLS = set("#.SG!abcdefABCDEF")
MOVES = (("right", 1, 0), ("down", 0, 1), ("left", -1, 0), ("up", 0, -1))


@dataclass(frozen=True)
class Board:
    name: str
    grid: tuple[str, ...]
    start: tuple[int, int]
    goal: tuple[int, int]

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict):
            raise ValueError("El mapa debe ser un objeto JSON")
        grid, name = data.get("grid"), data.get("name", "Dungeon")
        if not isinstance(name, str) or len(name) > 120:
            raise ValueError("name debe ser texto de hasta 120 caracteres")
        if (not isinstance(grid, list) or not 1 <= len(grid) <= 100
                or any(not isinstance(row, str) or not 1 <= len(row) <= 100 for row in grid)):
            raise ValueError("grid debe tener entre 1 y 100 filas de 1 a 100 casillas")
        if len({len(row) for row in grid}) != 1:
            raise ValueError("Las filas deben tener la misma longitud")
        if any(set(row) - SYMBOLS for row in grid):
            raise ValueError("Símbolo no reconocido")
        locations = {c: [(x, y) for y, row in enumerate(grid)
                         for x, tile in enumerate(row) if tile == c] for c in "SG"}
        if any(len(locations[c]) != 1 for c in "SG"):
            raise ValueError("Debe haber exactamente un S y un G")
        return cls(name, tuple(grid), locations["S"][0], locations["G"][0])


def solve(board, hazard_cost=5, max_states=200000):
    if type(hazard_cost) is not int or not 1 <= hazard_cost <= 1000:
        raise ValueError("hazard_cost debe ser un entero entre 1 y 1000")
    if type(max_states) is not int or not 1 <= max_states <= 200000:
        raise ValueError("max_states debe estar entre 1 y 200000")
    start = (*board.start, 0)
    goal_x, goal_y = board.goal
    def heuristic(state):
        return abs(state[0] - goal_x) + abs(state[1] - goal_y)
    counter = itertools.count()
    frontier = [(heuristic(start), 0, next(counter), start)]
    best, parent = {start: 0}, {}
    expanded = 0
    while frontier:
        _, cost, _, state = heapq.heappop(frontier)
        if cost != best[state]:
            continue
        if expanded >= max_states:
            return {"status": "budget_exceeded", "expanded": expanded,
                    "cost": None, "path": [], "actions": [], "keys": []}
        expanded += 1
        x, y, keys = state
        if (x, y) == board.goal:
            states, actions = [state], []
            while states[-1] != start:
                previous, action = parent[states[-1]]
                states.append(previous)
                actions.append(action)
            states.reverse()
            actions.reverse()
            return {"status": "solved", "expanded": expanded, "cost": cost,
                    "path": [[s[0], s[1]] for s in states], "actions": actions,
                    "keys": [c for i, c in enumerate("abcdef") if keys & (1 << i)]}
        for direction, dx, dy in MOVES:
            nx, ny = x + dx, y + dy
            if not (0 <= ny < len(board.grid) and 0 <= nx < len(board.grid[0])):
                continue
            tile = board.grid[ny][nx]
            if tile == "#":
                continue
            if tile in "ABCDEF" and not keys & (1 << (ord(tile) - ord("A"))):
                continue
            next_keys = keys
            if tile in "abcdef":
                next_keys |= 1 << (ord(tile) - ord("a"))
            step_cost = hazard_cost if tile == "!" else 1
            next_state = (nx, ny, next_keys)
            new_cost = cost + step_cost
            if new_cost < best.get(next_state, float("inf")):
                best[next_state] = new_cost
                action = {"move": direction, "to": [nx, ny], "cost": step_cost,
                          "picked_key": tile if next_keys != keys else None}
                parent[next_state] = (state, action)
                heapq.heappush(frontier, (new_cost + heuristic(next_state), new_cost,
                                         next(counter), next_state))
    return {"status": "unreachable", "expanded": expanded, "cost": None,
            "path": [], "actions": [], "keys": []}


def render_svg(board, result):
    size, offset, top = 48, 16, 76
    width, height = max(500, len(board.grid[0]) * size + 32), len(board.grid) * size + 148
    shapes = []
    for y, row in enumerate(board.grid):
        for x, tile in enumerate(row):
            color = ("#111827" if tile == "#" else "#82442f" if tile == "!" else
                     "#215e55" if tile in "SG" else "#574577" if tile in "ABCDEF" else "#24354d")
            px, py = offset + x * size, top + y * size
            shapes.append(f'<rect x="{px}" y="{py}" width="46" height="46" rx="5" fill="{color}"/>')
            if tile not in ".#":
                shapes.append(f'<text x="{px+8}" y="{py+17}" fill="#f5d78a" font-size="15">{tile}</text>')
    if result["path"]:
        points = " ".join(f"{offset+x*size+23},{top+y*size+23}" for x, y in result["path"])
        shapes.append(f'<polyline points="{points}" fill="none" stroke="#72e2cd" stroke-width="5" '
                      'stroke-linejoin="round" stroke-linecap="round" opacity=".85"/>')
    title = html.escape(board.name)
    status = html.escape(result["status"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">'
            f'<title>{title}: {status}</title><rect width="100%" height="100%" fill="#0b1220"/>'
            f'<g font-family="system-ui,sans-serif"><text x="16" y="29" fill="#eef5ff" font-size="23">'
            f'{title}</text><text x="16" y="54" fill="#afc0da" font-size="14">'
            f'{status} · coste {result["cost"]} · {len(result["actions"])} movimientos</text>'
            + "".join(shapes) +
            f'<text x="16" y="{height-40}" fill="#afc0da" font-size="12">'
            'S inicio · G meta · a–f llaves · A–F puertas · ! peligro</text>'
            f'<text x="16" y="{height-19}" fill="#afc0da" font-size="12">'
            'Ruta verde; puede volver sobre sus pasos para recoger una llave.</text></g></svg>\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", nargs="?", type=Path,
                        default=Path(__file__).parent / "maps/key-door.json")
    parser.add_argument("--hazard-cost", type=int, default=5)
    parser.add_argument("--max-states", type=int, default=200000)
    parser.add_argument("--json", type=Path, dest="json_path")
    parser.add_argument("--svg", type=Path, dest="svg_path")
    args = parser.parse_args()
    outputs = [p.resolve() for p in (args.json_path, args.svg_path) if p]
    if args.map.resolve() in outputs or len(outputs) != len(set(outputs)):
        parser.error("Las salidas deben ser distintas entre sí y del mapa")
    try:
        with args.map.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Archivo demasiado grande: máximo 1 MiB")
        board = Board.parse(json.loads(raw.decode("utf-8")))
        report = solve(board, args.hazard_cost, args.max_states)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.json_path:
            args.json_path.write_text(payload, encoding="utf-8")
        if args.svg_path:
            args.svg_path.write_text(render_svg(board, report), encoding="utf-8")
        print(payload, end="")
    except (OSError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")
    parser.exit({"solved": 0, "unreachable": 1, "budget_exceeded": 3}[report["status"]])


if __name__ == "__main__":
    main()
