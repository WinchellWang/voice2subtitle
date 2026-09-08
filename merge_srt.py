import re
import sys

def merge_srt(input_file, output_file=None, max_duration=12.0, max_gap=0.8):
    """
    input_file: Path to the input SRT file
    output_file: Output path; overwrite the input file when None
    max_duration: Maximum duration of a merged subtitle in seconds
    max_gap: Maximum gap between subtitles in seconds; larger gaps are treated as natural pauses
    """
    # Overwrite the input file when no output path is specified
    if not output_file:
        output_file = input_file

    def time_to_sec(time_str):
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    def sec_to_time(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        if ms >= 1000:
            s += 1
            ms = 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    # Read the entire input file into memory
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse the SRT content with a regular expression
    pattern = re.compile(r'\d+\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\Z)')
    matches = pattern.findall(content)

    if not matches:
        print(f"[SKIP] {input_file} does not contain valid SRT content")
        return

    merged_items = []
    
    curr_start = None
    curr_end = None
    curr_text_list = []

    for start_str, end_str, text in matches:
        text = text.strip()
        start_sec = time_to_sec(start_str)
        end_sec = time_to_sec(end_str)

        if curr_start is None:
            curr_start = start_sec
            curr_end = end_sec
            curr_text_list.append(text)
            continue

        prev_text = curr_text_list[-1]
        gap = start_sec - curr_end
        combined_duration = end_sec - curr_start

        # Check whether the previous subtitle ends with terminal punctuation (. ? !)
        has_ending_punctuation = bool(re.search(r'[.?!]$', prev_text.strip()))

        # Merge when either of the following conditions is met:
        # 1. The previous subtitle lacks terminal punctuation, the gap is short, and total duration stays within the limit
        # 2. The subtitles are effectively contiguous (gap <= 0.1s) and total duration stays within the limit
        should_merge = (not has_ending_punctuation and gap <= max_gap and combined_duration <= max_duration) or \
                       (gap <= 0.1 and combined_duration <= max_duration)

        if should_merge:
            curr_end = end_sec
            curr_text_list.append(text)
        else:
            merged_items.append((curr_start, curr_end, " ".join(curr_text_list)))
            curr_start = start_sec
            curr_end = end_sec
            curr_text_list = [text]

    if curr_start is not None:
        merged_items.append((curr_start, curr_end, " ".join(curr_text_list)))

    # Write the result, overwriting the original SRT file
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, (s_sec, e_sec, txt) in enumerate(merged_items, 1):
            f.write(f"{i}\n{sec_to_time(s_sec)} --> {sec_to_time(e_sec)}\n{txt}\n\n")

    print(f"[MERGED AND OVERWRITTEN] -> {output_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        merge_srt(sys.argv[1])
    else:
        print("Usage: python3 merge_srt.py <your_file.srt>")
