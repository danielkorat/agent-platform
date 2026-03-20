#!/usr/bin/env bash
# Build demo indexes and start the Agent Platform
set -e

cd "$(dirname "$0")/.."

echo "Building demo indexes..."
python -m connectors.build_demo_index

echo ""
echo "Starting Agent Platform on port 8081..."
python main.py
