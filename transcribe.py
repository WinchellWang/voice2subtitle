#!/usr/bin/env python3
import argparse, os, re, sys, tempfile, unicodedata
from faster_whisper import WhisperModel
MEDIA_EXTENSIONS={".mp3",".wav",".m4a",".flac",".aac",".ogg",".mp4",".mkv"}
def srt_time(s):
 m=max(0,round(s*1000)); h,m=divmod(m,3600000); n,m=divmod(m,60000); s,m=divmod(m,1000); return f"{h:02d}:{n:02d}:{s:02d},{m:03d}"
def norm(t): return "".join(c for c in t.casefold() if unicodedata.category(c)[0] not in {"P","Z","C"})
def repeat_loop(t):
 v=norm(t)
 for n in range(2,min(24,len(v)//3)+1):
  x=re.search(rf"(.{{{n}}})(?:\1){{2,}}",v)
  if x and len(x.group(0))/max(len(v),1)>=.7:return True
 return False
def merge_segments(items, max_duration=12.0, max_gap=1.2, max_chars=70):
 merged=[]
 for start,end,text in items:
  if merged:
   old_start,old_end,old_text=merged[-1]
   gap=start-old_end
   combined_text=f"{old_text} {text}"
   if gap <= max_gap and end-old_start <= max_duration and len(norm(combined_text)) <= max_chars:
    merged[-1]=(old_start,end,combined_text)
    continue
  merged.append((start,end,text))
 return merged

def transcribe(model,src,dst,lang,beam):
 requested_language=None if lang in {"auto",""} else lang
 print(f"[TRANSCRIBE] {os.path.basename(src)}",flush=True)
 segs,info=model.transcribe(src,language=requested_language,task="transcribe",beam_size=beam,temperature=0.0,
  vad_filter=True,vad_parameters={"threshold":.55,"min_speech_duration_ms":250,"min_silence_duration_ms":700,"speech_pad_ms":300},
  condition_on_previous_text=False,compression_ratio_threshold=2.2,log_prob_threshold=-.8,no_speech_threshold=.5,
  word_timestamps=True,hallucination_silence_threshold=2.0,repetition_penalty=1.15,no_repeat_ngram_size=3)
 out=[]; previous=None; same=0; dropped=0; milestone=-5
 for s in segs:
  percent=min(100,int(s.end/max(info.duration,.001)*100))
  if percent>=milestone+5:
   milestone=percent-percent%5
   print(f"[PROGRESS] {milestone:3d}% {srt_time(s.end)} / {srt_time(info.duration)} segments={len(out)} dropped={dropped}",flush=True)
  text=s.text.strip()
  if not text:continue
  key=norm(text); same=same+1 if key==previous else 1; previous=key
  if repeat_loop(text) or same>=3:
   dropped+=1; print(f"[DROP hallucination] {s.start:.2f}-{s.end:.2f}: {text[:100]}",file=sys.stderr); continue
  out.append((s.start,s.end,text))
 out=merge_segments(out)
 print(f"[MERGE] Combined into {len(out)} subtitle cue(s).",flush=True)
 print(f"[PROGRESS] 100% {srt_time(info.duration)} / {srt_time(info.duration)} segments={len(out)} dropped={dropped}",flush=True)
 directory=os.path.dirname(os.path.abspath(dst)); fd,tmp=tempfile.mkstemp(prefix=".subtitle-",suffix=".srt",dir=directory,text=True)
 try:
  with os.fdopen(fd,"w",encoding="utf-8") as f:
   for i,(a,b,t) in enumerate(out,1):f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n")
  os.replace(tmp,dst)
  host_uid=int(os.getenv("HOST_UID","-1")); host_gid=int(os.getenv("HOST_GID","-1"))
  os.chmod(dst,0o664)
  if host_uid >= 0 and host_gid >= 0:
   try: os.chown(dst,host_uid,host_gid)
   except OSError as error:
    os.chmod(dst,0o666)
    print(f"[WARNING] Could not set subtitle owner: {error}; using mode 0666",file=sys.stderr,flush=True)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 print(f"[OK] {src} -> {dst}; language={info.language}; audio={info.duration:.1f}s; after_vad={info.duration_after_vad:.1f}s; segments={len(out)}; dropped={dropped}")
def main():
 p=argparse.ArgumentParser();p.add_argument("paths",nargs="*",default=["/work"]);p.add_argument("--model",default=os.getenv("WHISPER_MODEL","large-v3"));p.add_argument("--device",default=os.getenv("WHISPER_DEVICE","cuda"));p.add_argument("--compute-type",default=os.getenv("WHISPER_COMPUTE_TYPE","int8_float32"));p.add_argument("--language",default=os.getenv("WHISPER_LANGUAGE","auto"));p.add_argument("--beam-size",type=int,default=int(os.getenv("WHISPER_BEAM","5")));p.add_argument("--force",action="store_true");a=p.parse_args()
 print("[SCAN] Searching: " + ", ".join(a.paths),flush=True)
 sources=[]
 for path in a.paths:
  if os.path.isdir(path):
   for root,dirs,files in os.walk(path):
    dirs[:]=[d for d in dirs if d not in {".git","__pycache__"} and not d.startswith("temp_chunks_")]
    sources += [os.path.join(root,n) for n in sorted(files) if os.path.splitext(n)[1].lower() in MEDIA_EXTENSIONS]
  elif os.path.splitext(path)[1].lower() in MEDIA_EXTENSIONS:sources.append(path)
 print(f"[SCAN] Found {len(sources)} supported media file(s).",flush=True)
 pending=[]
 for src in sources:
  dst=os.path.splitext(src)[0]+".srt"
  if os.path.exists(dst) and not a.force:print(f"[SKIP] {dst} already exists (use --force to replace it)")
  else:pending.append((src,dst))
 print(f"[QUEUE] pending={len(pending)} skipped={len(sources)-len(pending)}",flush=True)
 if not pending:return 0
 print(f"[LOAD] model={a.model}, device={a.device}, compute_type={a.compute_type}")
 model=WhisperModel(a.model,device=a.device,compute_type=a.compute_type,download_root="/var/lib/whisper")
 for src,dst in pending:transcribe(model,src,dst,a.language,a.beam_size)
 return 0
if __name__=="__main__":raise SystemExit(main())
