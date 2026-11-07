"""Optional phase-vocoder pitch shift: pitch changes without changing duration."""
import io
import wave
import math

def shift_wav(data,semitones):
    if isinstance(semitones,bool) or not isinstance(semitones,(int,float)) or not math.isfinite(semitones) or not -12<=semitones<=12:
        raise ValueError("Semitones must be between -12 and 12")
    try:
        import numpy as np
        import librosa
    except ImportError:
        return None
    from phonovision import analyze_wav
    analyze_wav(data)
    with wave.open(io.BytesIO(data),"rb") as w:
        rate=w.getframerate()
        channels=w.getnchannels()
        raw=w.readframes(w.getnframes())
    x=np.frombuffer(raw,dtype="<i2").astype(np.float32).reshape(-1,channels).mean(axis=1)/32768
    y=librosa.effects.pitch_shift(x,sr=rate,n_steps=float(semitones))
    y=np.clip(y,-1,1)
    buf=io.BytesIO()
    with wave.open(buf,"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        w.writeframes((y*32767).astype("<i2").tobytes())
    return buf.getvalue()
