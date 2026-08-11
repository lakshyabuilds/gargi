#!/bin/bash
# GARGI launcher

echo ""
echo "  Launching GARGI..."
echo ""

if ! command -v python3 &> /dev/null; then
    echo "  Python 3 required"
    exit 1
fi

python3 -c "import textual" 2>/dev/null || pip3 install textual rich openai

python3 gargi.py "$@"
