"""One-time source import. Normal build never runs this or changes inputs."""
from pathlib import Path
import json,urllib.request,urllib.parse,shutil,hashlib,math
from PIL import Image
r=Path(__file__).resolve().parents[1];repo=r.parent;source='44d4c542d64b40513a635494ac791d281b748fc4';plugin='e16c9e7f605a70f771513cb0af960ec62d7ad5ee';entries=[]
def record(p,url,license,transform='unchanged'):
 with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 entries.append({'path':str(p.relative_to(r)),'url':url,'sha256':sha,'license':license,'transform':transform})
def download(url,p,license):
 p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():urllib.request.urlretrieve(url,p)
 record(p,url,license)
for n in ['boot-splash','home-launcher','bbs','hermes-chat','shell']:
 download(f'https://raw.githubusercontent.com/mojomast/temple-of-hermes/{source}/docs/images/{n}.png',r/f'assets/placeholders/{n}.png','Unlicense / public domain')
for n in ['pane-agent-log','pane-shared','pane-user-driving']:
 p=r/f'assets/placeholders/{n}.png';shutil.copy2(repo/f'docs/images/{n}.png',p);record(p,f'https://github.com/mojomast/hermes-templeos/blob/{plugin}/docs/images/{n}.png','Repository MIT; original guest public domain')
for family,file,role in [('spacegrotesk','SpaceGrotesk[wght].ttf','Display'),('ibmplexsans','IBMPlexSans[wdth,wght].ttf','Sans'),('ibmplexmono','IBMPlexMono-Medium.ttf','Mono')]:
 base=f'https://raw.githubusercontent.com/google/fonts/main/ofl/{family}/'
 download(base+urllib.parse.quote(file),r/f'assets/fonts/{role}.ttf','SIL Open Font License 1.1');download(base+'OFL.txt',r/f'assets/fonts/{family}-OFL.txt','SIL Open Font License 1.1')
download(f'https://raw.githubusercontent.com/mojomast/temple-of-hermes/{source}/LICENSE',r/'assets/licenses/temple-of-hermes-Unlicense.txt','Unlicense')
shutil.copy2(repo/'LICENSE',r/'assets/licenses/plugin-MIT.txt')
base=repo/'desktop/assets/companion/terry/v4';registry=json.loads((base/'parts.json').read_text());frame=json.loads((base/'baked-presets.json').read_text())['idle']['frames'][0];target=r/'assets/terry';target.mkdir(parents=True,exist_ok=True)
# Static first idle pose from existing HD source parts. This is NOT a substitute animation.
scale=3.5;canvas=Image.new('RGBA',(672,728));parts=sorted(frame['parts'].items(),key=lambda v:registry['slots'].get(v[0],{}).get('layer',0)+v[1].get('layer_boost',0))
used=[]
for slot,pose in parts:
 spec=registry['slots'].get(slot)
 if not spec or pose.get('alpha',1)==0 or pose.get('visible',True)==False or slot in frame.get('hidden_slots',[]) or frame.get('visibility',{}).get(slot)==False or frame.get('props',{}).get(slot)==False:continue
 variant=frame.get('variants',{}).get(slot,pose.get('variant','default'));rel=spec.get('variants',{}).get(variant,spec.get('variants',{}).get('default',''));src=base/rel
 if not src.is_file() or slot=='smoke':continue
 dst=target/'source'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);used.append(rel);record(dst,f'https://github.com/mojomast/hermes-templeos/blob/{plugin}/desktop/assets/companion/terry/v4/{rel}','Fan-made generated illustration; repository MIT')
 im=Image.open(src).convert('RGBA');a=math.radians(pose.get('rot',0));sx=pose.get('sx',1)*(-1 if pose.get('flip') else 1);sy=pose.get('sy',1);piv=pose.get('pivot',spec['pivot']);c=math.cos(a);s=math.sin(a);x=pose['x']*scale;y=pose['y']*scale
 # Source pixels are 3.5x slot-space; inverse affine maps target canvas to those pixels.
 inv=(c/sx,s/sx,piv[0]*scale-(c*x+s*y)/sx,-s/sy,c/sy,piv[1]*scale-(-s*x+c*y)/sy)
 layer=im.transform(canvas.size,Image.Transform.AFFINE,inv,Image.Resampling.BICUBIC)
 if pose.get('alpha',1)!=1:layer.putalpha(layer.getchannel('A').point(lambda v:round(v*pose['alpha'])))
 canvas=Image.alpha_composite(canvas,layer)
canvas.save(target/'placeholder.png');(target/'source/pose.json').write_text(json.dumps({'frame':frame,'registry':{k:registry['slots'][k] for k in frame['parts'] if k in registry['slots']}},indent=2))
record(target/'placeholder.png',f'https://github.com/mojomast/hermes-templeos/tree/{plugin}/desktop/assets/companion/terry/v4','Fan-made generated illustration; repository MIT','Static first idle pose; 3.5x original slot coordinates; no animation')
for name in ['ASSET-MANIFEST.md','SCALE.json','README.txt']:shutil.copy2(base/name,target/'source'/name)
(r/'assets/provenance.json').write_text(json.dumps({'pluginCommit':plugin,'osCommit':source,'assets':entries},indent=2));print('Imported licensed fonts, README stand-ins and static HD Terry source artwork.')
