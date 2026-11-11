"""Optional narrator regeneration; the finished clips are committed. No Terry voice."""
from pathlib import Path
import argparse,json,wave,numpy as np,onnxruntime as ort
from kokoro_onnx import Kokoro
p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,required=True);a=p.parse_args();r=Path(__file__).resolve().parents[1]
o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1;session=ort.InferenceSession(str(a.model_dir/'kokoro-v1.0.onnx'),sess_options=o,providers=['CPUExecutionProvider']);model=Kokoro.from_session(session,str(a.model_dir/'voices-v1.0.bin'));voice=model.get_voice_style('af_heart');cues=json.loads((r/'narration.json').read_text());out=r/'assets/audio/voice';out.mkdir(parents=True,exist_ok=True)
for i,c in enumerate(cues):
 samples,sr=model.create(c['text'],voice=voice,speed=1.0,lang='en-us');active=np.flatnonzero(np.abs(samples)>.002)
 if len(active):samples=samples[max(0,active[0]-240):min(len(samples),active[-1]+1200)]
 end=c['start']+len(samples)/sr;assert end<c['deadline'],(i,end,c['deadline']);name=f'{i:02}.wav'
 with wave.open(str(out/name),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
 c.update(end=end,file='assets/audio/voice/'+name);c['text']=c['text'].replace('Holy C','HolyC').replace('World Sim','WorldSim').replace('H B B S one','HBBS/1').replace('COM two','COM2').replace('Temple O S','TempleOS');print(i,round(end-c['start'],3),flush=True)
(r/'assets/narration-timing.json').write_text(json.dumps(cues,indent=2))
def stamp(t):
 n=round(t*1000);return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'
(r/'captions').mkdir(exist_ok=True);(r/'captions/narration.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i,c in enumerate(cues))+'\n')
