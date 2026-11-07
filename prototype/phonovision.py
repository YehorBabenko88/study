"""PhonoVision: acoustic analysis of short PCM WAV speech, not letter-to-note pseudoscience."""
import io, wave, math, cmath, struct, html

def analyze_wav(data):
    if not isinstance(data,bytes) or len(data)>2_000_000:
        raise ValueError("WAV must be under 2 MB")
    try:
        with wave.open(io.BytesIO(data),"rb") as w:
            rate=w.getframerate(); channels=w.getnchannels(); width=w.getsampwidth()
            frames=w.getnframes()
            if w.getcomptype()!="NONE" or width!=2 or channels not in (1,2) or not 8000<=rate<=48000 or not 1<=frames<=rate*8:
                raise ValueError("Use 16-bit PCM WAV, 8–48 kHz, <=8 seconds")
            raw=w.readframes(frames)
    except (wave.Error,EOFError,struct.error) as exc:
        raise ValueError("Invalid PCM WAV") from exc
    samples=struct.unpack("<"+"h"*(len(raw)//2),raw)
    if channels==2:samples=[(samples[i]+samples[i+1])/2 for i in range(0,len(samples),2)]
    hop=max(1,rate//35)
    size=256
    window=[.5-.5*math.cos(2*math.pi*i/(size-1)) for i in range(size)]
    spectrum=[];energies=[]
    for start in range(0,max(1,len(samples)-size+1),hop):
        chunk=samples[start:start+size]
        if len(chunk)<size:break
        energies.append(math.sqrt(sum(v*v for v in chunk)/size)/32768)
        x=[v/32768*window[i] for i,v in enumerate(chunk)]
        bins=[]
        for k in range(0,129,4):
            z=sum(x[n]*cmath.exp(-2j*math.pi*k*n/size) for n in range(size))
            bins.append(abs(z))
        spectrum.append(bins)
        if len(spectrum)>=280:break
    if not spectrum:raise ValueError("Audio too short")
    peak=max((v for row in spectrum for v in row),default=1) or 1
    return {"rate":rate,"duration_seconds":round(frames/rate,3),
            "rms":round(sum(energies)/len(energies),5),
            "spectrogram":[[round(min(1,v/peak),3) for v in row] for row in spectrum],
            "method":"windowed_dft_256_16bit","interpretation":"acoustic texture only; no phoneme alignment"}

def svg(result):
    data=result["spectrogram"]
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 320" role="img">',
           '<rect width="900" height="320" rx="18" fill="#12233e"/>']
    w=860/len(data)
    for i,row in enumerate(data):
        for j,v in enumerate(row):
            if v<.025:continue
            opacity=round(.15+.85*math.sqrt(v),3)
            parts.append(f'<rect x="{20+i*w:.2f}" y="{290-(j+1)*7.5:.2f}" width="{max(.8,w):.2f}" height="7.4" fill="#6bc9e9" opacity="{opacity}"/>')
    parts.append('<text x="20" y="310" font-size="12" fill="white">Time → · frequency ↑ · normalized energy</text></svg>')
    return "".join(parts)

def metaphor(sound):
    """Editable *suggestions* based on sound spelling, not measured phonemes."""
    if not isinstance(sound,str) or not 1<=len(sound)<=80:raise ValueError("sound fragment required")
    s=sound.lower()
    if any(x in s for x in ("sch","sh","s","z","ß")):
        shape,description="spark-cloud","Шумное облако искр"
    elif any(x in s for x in ("t","p","k")):
        shape,description="flash","Короткая вспышка или удар"
    elif any(x in s for x in ("a","e","i","o","u","ä","ö","ü")):
        shape,description="ribbon","Плавная цветная лента"
    else:
        shape,description="texture","Абстрактная текстура"
    return {"fragment":sound,"shape":shape,"suggestion":description,
            "evidence":"creative_heuristic_not_phonetic_analysis"}
