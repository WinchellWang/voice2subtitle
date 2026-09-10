#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import unicodedata
import zlib
from dataclasses import asdict, dataclass


SRT_PATTERN = re.compile(
    r"\d+\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\Z)"
)


@dataclass
class Quality:
    suspicious: bool
    suspicious_cues: int
    repeat_count: int
    repeat_coverage: float
    compression_ratio: float
    long_low_information_cues: int
    score: float


def timestamp_seconds(value):
    hours, minutes, seconds_milliseconds = value.split(":")
    seconds, milliseconds = seconds_milliseconds.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def normalized_text(value):
    return "".join(
        character
        for character in value.casefold()
        if unicodedata.category(character)[0] not in {"P", "Z", "C"}
    )


def strongest_repeat(value, max_unit_length=16):
    text = normalized_text(value)
    best_count = 1
    best_coverage = 0.0

    for unit_length in range(1, min(max_unit_length, len(text) // 4) + 1):
        pattern = re.compile(rf"(.{{{unit_length}}})(?:\1){{3,}}")
        for match in pattern.finditer(text):
            count = len(match.group(0)) // unit_length
            coverage = len(match.group(0)) / max(len(text), 1)
            if (count, coverage) > (best_count, best_coverage):
                best_count = count
                best_coverage = coverage

    return best_count, best_coverage


def compression_ratio(value):
    payload = normalized_text(value).encode("utf-8")
    if len(payload) < 20:
        return 1.0
    return len(payload) / max(len(zlib.compress(payload, level=9)), 1)


def analyze(path):
    content = open(path, "r", encoding="utf-8").read().replace("\r\n", "\n")
    matches = SRT_PATTERN.findall(content)

    suspicious_cues = 0
    maximum_repeat_count = 1
    maximum_repeat_coverage = 0.0
    maximum_compression_ratio = 1.0
    long_low_information_cues = 0

    for start, end, text in matches:
        clean_text = normalized_text(text)
        duration = max(0.0, timestamp_seconds(end) - timestamp_seconds(start))
        repeat_count, repeat_coverage = strongest_repeat(text)
        ratio = compression_ratio(text)

        repetitive = (
            repeat_count >= 5
            and repeat_coverage >= 0.55
            and len(clean_text) >= 10
        )
        highly_compressed = ratio >= 2.6 and len(clean_text) >= 40
        long_low_information = duration >= 20 and len(clean_text) <= 12

        if repetitive or highly_compressed or long_low_information:
            suspicious_cues += 1
        if long_low_information:
            long_low_information_cues += 1

        maximum_repeat_count = max(maximum_repeat_count, repeat_count)
        maximum_repeat_coverage = max(maximum_repeat_coverage, repeat_coverage)
        maximum_compression_ratio = max(maximum_compression_ratio, ratio)

    no_subtitles = not matches
    suspicious = no_subtitles or suspicious_cues > 0
    score = (
        (1000 if no_subtitles else 0)
        + suspicious_cues * 100
        + long_low_information_cues * 40
        + min(maximum_repeat_count, 100) * maximum_repeat_coverage
        + maximum_compression_ratio
    )

    return Quality(
        suspicious=suspicious,
        suspicious_cues=suspicious_cues,
        repeat_count=maximum_repeat_count,
        repeat_coverage=round(maximum_repeat_coverage, 4),
        compression_ratio=round(maximum_compression_ratio, 4),
        long_low_information_cues=long_low_information_cues,
        score=round(score, 4),
    )


def ranking(quality):
    return (
        quality.suspicious,
        quality.suspicious_cues,
        quality.long_low_information_cues,
        quality.score,
    )


def command_detect(path):
    quality = analyze(path)
    print(json.dumps(asdict(quality), ensure_ascii=False))
    return 0 if quality.suspicious else 1


def command_choose(output, candidates):
    available = [candidate for candidate in candidates if os.path.isfile(candidate) and os.path.getsize(candidate) > 0]
    if not available:
        print("No valid SRT candidates were provided.")
        return 2

    results = [(candidate, analyze(candidate)) for candidate in available]
    best_path, best_quality = min(results, key=lambda item: ranking(item[1]))

    if os.path.abspath(best_path) != os.path.abspath(output):
        temporary_output = output + ".selected"
        shutil.copyfile(best_path, temporary_output)
        os.replace(temporary_output, output)

    print(
        json.dumps(
            {
                "selected": best_path,
                "quality": asdict(best_quality),
                "candidates": [
                    {"path": path, "quality": asdict(quality)}
                    for path, quality in results
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="Detect repetitive Whisper hallucinations and select the best SRT retry.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect")
    detect_parser.add_argument("srt")

    choose_parser = subparsers.add_parser("choose")
    choose_parser.add_argument("output")
    choose_parser.add_argument("candidates", nargs="+")

    args = parser.parse_args()
    if args.command == "detect":
        return command_detect(args.srt)
    return command_choose(args.output, args.candidates)


if __name__ == "__main__":
    raise SystemExit(main())
