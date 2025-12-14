#!/bin/bash
echo "Starting Tagger2 with debug output capture..."
cd "$(dirname "$0")"
python run.py 2>&1 | tee deletion_test.log
