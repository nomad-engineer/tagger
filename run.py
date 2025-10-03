#!/usr/bin/env python3
"""
Launch script for Image Tagger application
"""
import sys
import os

# Add the image_tagger directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from image_tagger.main import main

if __name__ == "__main__":
    main()