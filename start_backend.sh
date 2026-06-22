#!/bin/bash
# DataMoA Python backend starter
# Run from project root: ./start_backend.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting DataMoA backend..."
echo "Python: $(python3 --version)"
echo "Working dir: $SCRIPT_DIR"

# Check dependencies
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip3 install -r requirements.txt --break-system-packages
fi

export PYTHONPATH="$SCRIPT_DIR"
python3 core/main.py --port "${DATAMOA_PORT:-7532}"
