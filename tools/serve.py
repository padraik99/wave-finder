"""Serve the app locally the way GitHub Pages will: app/ at the root, data at /data/.

    python tools/serve.py --data path/to/data     (default: ./data)

Get data with:  git fetch origin data && git worktree add data origin/data
or run the pipeline:  python -m pipeline.run --out data
Then open http://localhost:8000 (service workers work on localhost).
"""

import argparse
import functools
import http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Handler(http.server.SimpleHTTPRequestHandler):
    data_dir: Path

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/data/"):
            target = (self.data_dir / clean[len("/data/"):]).resolve()
            return str(target if target.is_relative_to(self.data_dir) else self.data_dir)
        return super().translate_path(path)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    Handler.data_dir = args.data.resolve()
    handler = functools.partial(Handler, directory=str(ROOT / "app"))
    print(f"Serving app/ with data from {Handler.data_dir} on http://localhost:{args.port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
