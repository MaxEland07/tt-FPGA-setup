#!/usr/bin/env sh
# Linux / macOS entry point: finds Python 3.8+ and runs setup.py.   Usage: sh setup.sh [setup.py options]
cd "$(dirname "$0")" || exit 1
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
    exec "$py" setup.py "$@"
  fi
done
echo "Python 3.8 or newer was not found."
case "$(uname -s)" in
  Darwin) echo "Install it with:  brew install python   (or from https://www.python.org/downloads/)" ;;
  *)      echo "Install it with:  sudo apt install python3 python3-venv   (or your distro's equivalent)" ;;
esac
exit 1
