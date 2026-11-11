from pathlib import Path
import json,subprocess
from PIL import Image,ImageDraw
r=Path(__file__).resolve().parents[1];p=r/'out/submission.mp4';dest=r/'preview/encoded';dest.mkdir(exist_ok=True);times=[2,6.5,12,23,32,40,48,55,62,70,76,82,87];base=['nice','-n','19','ffmpeg','-y','-v','error','-nostdin','-threads','2','-filter_threads','2']
for t in times:subprocess.run(base+['-ss',str(t),'-i',str(p),'-frames:v','1','-threads','2',str(dest/(str(t)+'.png'))],check=True)
sheet=Image.new('RGB',(1440,1470),'#060916');d=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
 im=Image.open(dest/(str(t)+'.png'));im.thumbnail((480,270));x=i%3*480;y=i//3*294;sheet.paste(im,(x,y));d.text((x+8,y+273),f'{t}s / ENCODED PLACEHOLDER CUT',fill='white')
sheet.save(r/'preview/contact-sheet.jpg',quality=93)
def sample(t):return subprocess.run(base+['-ss',str(t),'-i',str(p),'-frames:v','1','-vf','scale=192:108','-pix_fmt','rgb24','-threads','2','-f','rawvideo','-'],capture_output=True,check=True).stdout
settings=json.loads((r/'settings.json').read_text());cuts=[s['start'] for s in settings['scenes'][1:]];sheet=Image.new('RGB',(1152,len(cuts)*242),'#060916');d=ImageDraw.Draw(sheet)
for y,cut in enumerate(cuts):
 for x,f in enumerate([cut-1,cut,cut+1]):
  b=sample(f/30);assert len(b)==192*108*3 and max(b)-min(b)>25;sheet.paste(Image.frombytes('RGB',(192,108),b).resize((384,216)),(x*384,y*242));d.text((x*384+8,y*242+221),str(f),fill='white')
sheet.save(r/'preview/cut-boundaries.jpg',quality=93);movement=[]
for s in settings['scenes'][:-1]:
 a=sample(s['start']/30+.1);b=sample(s['start']/30+.6);diff=sum(x!=y for x,y in zip(a,b));assert diff>0;movement.append({'scene':s['id'],'changedChannelValues':diff})
a,b=sample(87),sample(89);hold=sum(abs(x-y) for x,y in zip(a,b))/len(a);assert hold<1
(r/'out/encoded-review.json').write_text(json.dumps({'stills':times,'cutFrames':cuts,'movement':movement,'memorialHoldMeanDifference':hold,'source':'actual encoded landscape master'},indent=2));print('Encoded scene/cut/motion/hold checks passed.')
