#!/usr/bin/env -S uv run --script

# Usage:
#   ./text_to_yaml.py <text file> <optional output file>

import sys

input_file = sys.argv[1]

print("songs:")

with open(input_file, "r") as f:
    for line in f.readlines():
        key, title = line.split(" ", maxsplit=1)
        print(f"""- title: {title.rstrip()}
  original_artist: 
  key: {key}
  duration_seconds: 
  active: true
  reference_artists: []
  writers: []
  verse_hints: []
  structure: 
  progressions:
  - verse: 
  - chorus: 
  - bridge: 
  notes: 
  intro:
  - 
  - 
  outro:
  - 
  - """)
