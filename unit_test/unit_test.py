from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
	result = subprocess.run(
		[sys.executable, "-m", "pytest", str(PROJECT_ROOT / "unit_test"), "-v"],
		cwd=PROJECT_ROOT,
		check=False,
	)
	return result.returncode


if __name__ == "__main__":
	raise SystemExit(main())
