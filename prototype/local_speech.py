"""Optional offline speech transcription and word alignment.

Models must already be downloaded locally. No implicit model fetch.
"""
from pathlib import Path
import os
import tempfile
import wave
import io

def _validate_wav(data):
    if not isinstance(data,bytes) or len(data)>2_000_000:
        raise ValueError("Audio must be PCM WAV <=2 MB")
    with wave.open(io.BytesIO(data),"rb") as f:
        if f.getcomptype()!="NONE" or f.getsampwidth()!=2 or f.getnchannels() not in (1,2) or f.getnframes()/f.getframerate()>8:
            raise ValueError("Expected 16-bit PCM WAV up to 8 seconds")
    return data

def transcribe(data,language="de",model_dir=None):
    _validate_wav(data)
    if language not in ("de","ru","en"):raise ValueError("Unsupported language")
    model_dir=model_dir or os.getenv("STUDY_WHISPER_MODEL_DIR","")
    if not model_dir or not Path(model_dir).is_dir():
        return {"status":"unavailable","reason":"local_model_not_configured","words":[]}
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"status":"unavailable","reason":"faster_whisper_missing","words":[]}
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"speech.wav"
        p.write_bytes(data)
        try:
            model=WhisperModel(str(Path(model_dir).resolve()),device="cpu",compute_type="int8",local_files_only=True)
            segments,info=model.transcribe(str(p),language=language,word_timestamps=True,beam_size=3)
            parts=list(segments)
        except Exception:
            return {"status":"unavailable","reason":"model_inference_failed","words":[]}
    words=[{"text":w.word.strip(),"start":round(w.start,3),"end":round(w.end,3),
            "probability":round(w.probability,3) if w.probability is not None else None}
           for seg in parts for w in (seg.words or []) if w.start is not None and w.end is not None]
    return {"status":"ok","text":" ".join(seg.text.strip() for seg in parts),
            "language":language,"words":words,"granularity":"word_not_phoneme",
            "provider":"local_faster_whisper"}

def align(data,transcript,language="de",align_model_dir=None):
    _validate_wav(data)
    if not isinstance(transcript,str) or not transcript.strip() or len(transcript)>1000:
        raise ValueError("Transcript required")
    if language not in ("de","ru","en"):raise ValueError("Unsupported language")
    align_model_dir=align_model_dir or os.getenv("STUDY_ALIGN_MODEL_DIR","")
    if not align_model_dir or not Path(align_model_dir).is_dir():
        return {"status":"unavailable","reason":"local_alignment_model_not_configured","segments":[]}
    try:
        import whisperx
        import numpy as np
    except ImportError:
        return {"status":"unavailable","reason":"whisperx_or_numpy_missing","segments":[]}
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"speech.wav"
        p.write_bytes(data)
        try:
            audio=whisperx.load_audio(str(p))
            model,metadata=whisperx.load_align_model(language_code=language,device="cpu",model_name=str(Path(align_model_dir).resolve()))
            result=whisperx.align([{"text":transcript,"start":0.0,"end":len(audio)/16000}],model,metadata,audio,device="cpu",return_char_alignments=True)
            chars=[{"text":c.get("char",""),"start":c["start"],"end":c["end"]}
                   for seg in result.get("segments",[]) for c in seg.get("chars",[])
                   if c.get("start") is not None and c.get("end") is not None]
        except Exception:
            return {"status":"unavailable","reason":"alignment_failed_or_incompatible_model","segments":[]}
    return {"status":"ok","segments":chars,"granularity":"character_alignment_not_verified_phonemes",
            "provider":"local_whisperx"}
