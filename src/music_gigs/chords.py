from __future__ import annotations

import re

_CHORD_ROOT_RE = re.compile(
    r"^([A-G])([#b]?)(.*)$",
)

_CHROMATIC_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E"}

_MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]  # semitones from root for I-VII
_NASHVILLE_MAJOR = ["1", "2", "3", "4", "5", "6", "7"]
_NASHVILLE_MINOR = ["1", "2m", "3m", "4", "5", "6m", "7m"]


def _normalize_root(root: str, accidental: str) -> str:
    note = root + accidental
    if note in _FLAT_TO_SHARP:
        return _FLAT_TO_SHARP[note]
    return note


def _note_index(note: str) -> int:
    note = _normalize_root(note[0], note[1:] if len(note) > 1 else "")
    return _CHROMATIC_SHARP.index(note)


def _index_to_note(index: int) -> str:
    return _CHROMATIC_SHARP[index % 12]


def parse_chord_name(chord: str) -> tuple[str, str]:
    """Return (root_note, suffix) e.g. ('F#', 'm') from 'F#m' or 'A/C#'."""
    chord = chord.strip()
    if "/" in chord:
        chord = chord.split("/", 1)[0]
    match = _CHORD_ROOT_RE.match(chord)
    if not match:
        return chord, ""
    root = _normalize_root(match.group(1), match.group(2))
    return root, match.group(3)


def semitones_between_keys(source_key: str, target_key: str) -> int:
    source_root, _ = parse_chord_name(source_key)
    target_root, _ = parse_chord_name(target_key)
    return (_note_index(target_root) - _note_index(source_root)) % 12


def transpose_chord(chord: str, semitones: int) -> str:
    if not chord or semitones == 0:
        return chord
    bass = ""
    main = chord
    if "/" in chord:
        main, bass = chord.split("/", 1)
        bass = "/" + transpose_chord(bass, semitones)

    match = _CHORD_ROOT_RE.match(main)
    if not match:
        return chord

    root = _normalize_root(match.group(1), match.group(2))
    suffix = match.group(3)
    new_root = _index_to_note(_note_index(root) + semitones)
    return new_root + suffix + bass


def chord_to_nashville(chord: str, key: str) -> str:
    """Map a chord to Nashville number relative to major key (lowercase m = minor)."""
    key_root, _ = parse_chord_name(key)
    chord_root, suffix = parse_chord_name(chord)
    key_idx = _note_index(key_root)
    chord_idx = _note_index(chord_root)
    semitone = (chord_idx - key_idx) % 12

    is_minor = suffix.startswith("m") and not suffix.startswith("maj")
    is_dim = "dim" in suffix or suffix == "m7b5"

    for degree, interval in enumerate(_MAJOR_SCALE, start=1):
        if semitone == interval:
            numeral = str(degree)
            if is_minor or is_dim:
                if degree in {2, 3, 6}:
                    return numeral + "m"
                if degree == 7 and is_dim:
                    return "7dim"
                if is_minor:
                    return numeral + "m"
            return numeral

    # fallback for chords outside diatonic major
    return ""


def format_chord_display(chord: str, key: str, show_nashville: bool) -> str:
    if not show_nashville:
        return chord
    numeral = chord_to_nashville(chord, key)
    if numeral:
        return f"{chord} ({numeral})"
    return chord
