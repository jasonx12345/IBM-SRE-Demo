"""Run the complete local demo without Docker, Kubernetes, or PostgreSQL."""

import argparse

from api.app import create_app
from api.demo_repository import DemoRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    app = create_app(repository=DemoRepository())
    app.config["DEMO_MODE"] = True
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
