#!/bin/bash
set -e

echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Installing local package 'pipeline'..."
pip install -e .

echo "Build complete!"
