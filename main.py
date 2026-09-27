#!/usr/bin/env python3
"""paws entrypoint. yeah this is just a wrapper around paws.cli."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paws.cli import entrypoint  # noqa: E402

if __name__ == "__main__":
    entrypoint()
