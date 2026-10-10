"""Container test entry point: opt into temporary PostgreSQL integration databases."""

import os
import subprocess
import sys


def main():
    environment = os.environ.copy()
    if "DATABASE_URL" in environment:
        environment["TEST_DATABASE_URL"] = environment["DATABASE_URL"]
    for command in (
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "."],
    ):
        result = subprocess.run(command, env=environment, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
