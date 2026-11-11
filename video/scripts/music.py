"""Original 120 BPM synth score + typing/power SFX + modern narrator, CC0."""
from pathlib import Path
import numpy as np,wave,json,subprocess
r=Path(__file__).resolve().parents[1];out=r/'assets/audio';out.mkdir(exist_ok=True);SR=48000;N=90*SR;rng=np.random.default_rng(64048016);score=np.zeros((N,2),np.float32);voice=np.zeros(N,np.float32);sfx=np.zeros((N,2),np.float32)
def t(d):return np.arange(round(d*SR),dtype=np.float32)/SR
def add(dest,a,start,gain,pan=0):
 s=round(start*SR);e=min(N,s+len(a));p=(pan+1)*np.pi/4
 if s>=0 and e>s:dest[s:e,0]+=a[:e-s]*gain*np.cos(p);dest[s:e,1]+=a[:e-s]*gain*np.sin(p)
def hz(n):return 440*2**((n-69)/12)
def note(n,d=.4,soft=False):
 x=t(d);f=hz(n);w=np.sin(2*np.pi*f*x)+(.08 if soft else .25)*np.sin(4*np.pi*f*x)+.08*np.sin(6*np.pi*f*x);return w*np.exp(-x*(2 if soft else 7))*np.minimum(1,x/.009)*np.minimum(1,(d-x)/.05)
def kick():
 x=t(.35);return np.sin(2*np.pi*(45*x+2.7*(1-np.exp(-x*30))))*np.exp(-x*14)*np.minimum(1,x/.002)
def snare():
 x=t(.18);return (rng.normal(0,.3,len(x))+np.sin(2*np.pi*175*x)*.25)*np.exp(-x*24)*np.minimum(1,x/.002)
def hat():
 x=t(.055);n=rng.normal(0,.2,len(x));return np.diff(n,prepend=0)*np.exp(-x*85)*np.minimum(1,x/.001)
chords=[[38,45,50,53],[34,41,46,50],[41,48,53,57],[36,43,48,52]]
for bar in range(45):
 start=bar*2;ch=chords[(bar//4)%4];energy=.35 if bar<4 else (.5 if bar<10 else 1)
 if 18<=bar<23:energy=.6
 if bar>=40:energy=.5
 for j in range(8):add(score,note(ch[1+j%3]+12,.4),start+j*.25,.026*energy,(-1)**j*.55)
 for i,n in enumerate(ch[1:]):add(score,note(n,1.8,True),start,.023*energy,(i-1)*.4)
 if 10<=bar<42:
  for b in [0,1,2,3]:add(score,kick(),start+b*.5,.23*energy)
  for b in [1,3]:add(score,snare(),start+b*.5,.15*energy)
  for b in range(8):add(score,hat(),start+b*.25,.08*energy,(-1)**b*.6)
  for b in [0,.75,1.5]:add(score,note(ch[0]-12,.5),start+b,.16*energy)
 if 4<=bar<10:
  for b in range(4):add(score,hat(),start+b*.5,.035+(bar-4)*.006,.4)
for sec in [8,20,28,37,45,51,65,80]:
 x=t(.2);add(sfx,rng.normal(0,.14,len(x))*np.exp(-x*27),sec,.45);add(sfx,note(81,.2),sec,.035,.4)
x=t(1.3);add(sfx,np.sin(2*np.pi*(1800*x+3200*x*x))*np.exp(-x*6)*np.minimum(1,x/.01),0,.07)
x=t(2);rise=rng.normal(0,.035,len(x))*np.linspace(0,1,len(x))*np.minimum(1,(2-x)/.025);add(sfx,rise,18,.7)
for sec in [5.5,5.65,5.8,6,6.2,20.2,20.4,20.6,28.2,28.4,28.6,80.1,80.3,80.5]:
 x=t(.028);add(sfx,(rng.normal(0,.2,len(x))+np.sin(2*np.pi*1350*x)*.16)*np.exp(-x*160),sec,.11,-.2)
for i,n in enumerate([38,45,50,53,62]):add(score,note(n,4,True),85,.055,(i-2)*.2)
base=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-threads','2','-filter_threads','2'];cues=json.loads((r/'assets/narration-timing.json').read_text());duck=np.ones(N,np.float32)
for c in cues:
 b=subprocess.run(base+['-i',str(r/c['file']),'-ar',str(SR),'-ac','1','-f','f32le','-'],capture_output=True,check=True).stdout;a=np.frombuffer(b,dtype='<f4').copy();active=a[np.abs(a)>.007];gain=min(.14/max(.001,float(np.sqrt(np.mean(active**2)))),.8/max(.001,float(np.max(np.abs(a)))));a*=gain;s=round(c['start']*SR);voice[s:s+len(a)]+=a;duck[max(0,s-4800):min(N,s+len(a)+6000)]=.28
cum=np.concatenate(([0.],np.cumsum(np.pad(duck,(2400,2399),mode='edge'),dtype=np.float64)));duck=((cum[4800:]-cum[:-4800])/4800).astype(np.float32)
fade=np.minimum(1,np.arange(N)/SR/.015)*np.minimum(1,(90-np.arange(N)/SR)/1.4)
def wav(name,a):
 a=a*fade[:,None]
 with wave.open(str(out/name),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((np.clip(a,-1,1)*32767).astype('<i2').tobytes())
wav('score.wav',score);wav('sfx.wav',sfx);wav('raw.wav',score*duck[:,None]+sfx+voice[:,None])
def measure(p):
 q=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-threads','2','-filter_threads','2','-i',str(p),'-af','loudnorm=I=-15:TP=-3:LRA=8:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr;return json.JSONDecoder().raw_decode(q[q.rfind('{'):])[0]
j=measure(out/'raw.wav');f=f"loudnorm=I=-15:TP=-3:LRA=8:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=false"
subprocess.run(base+['-y','-i',str(out/'raw.wav'),'-af',f,'-ar','48000','-c:a','pcm_s16le',str(out/'mix.wav')],check=True);(out/'raw.wav').unlink();j=measure(out/'mix.wav');gain=-15-float(j['input_i']);assert float(j['input_tp'])+gain<=-1.5
subprocess.run(base+['-y','-i',str(out/'mix.wav'),'-af',f'volume={gain}dB','-c:a','pcm_s16le',str(out/'trim.wav')],check=True);(out/'trim.wav').replace(out/'mix.wav');report={'seed':64048016,'bpm':120,'downbeat':0,'drop':20,'license':'CC0-1.0','pcm':measure(out/'mix.wav')};(out/'mastering.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
