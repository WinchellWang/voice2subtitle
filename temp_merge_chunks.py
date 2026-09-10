import sys
import datetime
import os

def parse_time(t_str):
    '''Parse an SRT timestamp and return a timedelta object'''
    h, m, s_ms = t_str.strip().split(':')
    s, ms = s_ms.replace('.', ',').split(',')
    return datetime.timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))

def format_time(td):
    '''Format a timedelta object as a standard SRT timestamp'''
    ts = int(td.total_seconds())
    ms = int(td.microseconds / 1000)
    return f"{ts//3600:02d}:{(ts%3600)//60:02d}:{ts%60:02d},{ms:03d}"

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python temp_merge_chunks.py <output.srt> <chunk_seconds> <overlap_seconds> <chunk1.srt> [<chunk2.srt> ...]")
        sys.exit(1)

    out_srt = sys.argv[1]
    seg_sec = int(sys.argv[2])
    overlap_sec = int(sys.argv[3])
    chunk_srts = sys.argv[4:]

    if overlap_sec < 0 or overlap_sec >= seg_sec:
        print("Error: overlap duration must be at least 0 and shorter than chunk duration")
        sys.exit(1)

    chunk_step = seg_sec - overlap_sec
    
    sub_idx = 1
    
    with open(out_srt, 'w', encoding='utf-8') as out:
        for i, srt in enumerate(chunk_srts):
            if not os.path.exists(srt):
                print(f"Warning: subtitle chunk file not found: {srt}")
                continue
                
            # Calculate the timestamp offset for the current chunk
            offset = datetime.timedelta(seconds=i * chunk_step)
            
            try:
                with open(srt, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        continue
                        
                    blocks = content.replace('\r\n', '\n').split('\n\n')
                    for block in blocks:
                        if not block.strip(): 
                            continue
                            
                        parts = block.split('\n')
                        if len(parts) >= 3 and ' --> ' in parts[1]:
                            st, et = parts[1].split(' --> ')
                            
                            local_st = parse_time(st)
                            local_et = parse_time(et)
                            # The previous chunk owns the overlap. When it is available,
                            # remove the overlapping prefix from the current chunk.
                            previous_chunk_available = (
                                i > 0
                                and os.path.exists(chunk_srts[i - 1])
                                and os.path.getsize(chunk_srts[i - 1]) > 0
                            )
                            if previous_chunk_available:
                                overlap_end = datetime.timedelta(seconds=overlap_sec)
                                if local_et <= overlap_end:
                                    continue
                                if local_st < overlap_end:
                                    local_st = overlap_end

                            # Apply the timestamp offset
                            st_td = local_st + offset
                            et_td = local_et + offset
                            
                            # Write the new index, adjusted timestamps, and subtitle text
                            out.write(f"{sub_idx}\n{format_time(st_td)} --> {format_time(et_td)}\n" + '\n'.join(parts[2:]) + "\n\n")
                            sub_idx += 1
            except Exception as e:
                print(f"Error while reading subtitle file {srt}: {e}")
