import re
import sys

def merge_srt(input_file, output_file=None, max_duration=12.0, max_gap=0.8):
    """
    input_file: Path to the input SRT file
    output_file: Path to the output file. If None, adds a "_merged" suffix
                 to the original filename
    max_duration: Maximum duration (in seconds) of a merged subtitle,
                  to prevent subtitles from becoming too long
    max_gap: Maximum allowed gap (in seconds) between two subtitles.
             If the gap exceeds this value, it is considered a natural pause
             and the subtitles will not be forcibly merged.
    """
    if not output_file:
        output_file = input_file.replace('.srt', '_merged.srt')

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

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse the SRT using a regular expression
    pattern = re.compile(
        r'\d+\n'
        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*'
        r'(\d{2}:\d{2}:\d{2},\d{3})\n'
        r'([\s\S]*?)(?=\n\n|\Z)'
    )
    matches = pattern.findall(content)

    if not matches:
        print(f"[Skipped] {input_file}: No valid SRT format found")
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

        # Check whether the previous subtitle ends with sentence-ending
        # punctuation (. ? !)
        has_ending_punctuation = bool(
            re.search(r'[.?!]$', prev_text.strip())
        )

        # Try to merge if either of the following conditions is met:
        # 1. The previous subtitle does not end with sentence-ending
        #    punctuation, the gap is very short (< max_gap), and the
        #    combined duration does not exceed max_duration.
        # 2. The two subtitles are almost seamlessly connected in time
        #    (gap <= 0.1s), and the combined duration does not exceed
        #    max_duration.
        should_merge = (
            (not has_ending_punctuation
             and gap <= max_gap
             and combined_duration <= max_duration)
            or
            (gap <= 0.1 and combined_duration <= max_duration)
        )

        if should_merge:
            curr_end = end_sec
            curr_text_list.append(text)
        else:
            merged_items.append(
                (curr_start, curr_end, " ".join(curr_text_list))
            )
            curr_start = start_sec
            curr_end = end_sec
            curr_text_list = [text]

    if curr_start is not None:
        merged_items.append(
            (curr_start, curr_end, " ".join(curr_text_list))
        )

    # Write the new SRT file
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, (s_sec, e_sec, txt) in enumerate(merged_items, 1):
            f.write(
                f"{i}\n"
                f"{sec_to_time(s_sec)} --> {sec_to_time(e_sec)}\n"
                f"{txt}\n\n"
            )

    print(f"[Merged] -> {output_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        merge_srt(sys.argv[1])
    else:
        print("Usage: python3 merge_srt.py <your_file.srt>")
