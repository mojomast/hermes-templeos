import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {execFileSync} from 'node:child_process';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');process.chdir(root);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));const slots=read('slots.json'),terry=read('terry-slots.json');fs.mkdirSync('.cache/media',{recursive:true});const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
export function decode(file,name,{seconds=0,inpoint=0,alpha=false,width=1440,fps=30}={}){
 if(!fs.existsSync(file))return {available:false,reason:'file missing',file};
 try{
  const j=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',file],{encoding:'utf8'})),v=j.streams.find(v=>v.codec_type==='video');if(!v)throw Error('no video stream');const duration=Number(j.format.duration);if(!Number.isFinite(duration)||duration<.1)throw Error('invalid duration');if(seconds&&duration+.05<seconds+inpoint)throw Error(`needs ${seconds+inpoint}s; got ${duration}s`);
  if(alpha&&(v.codec_name!=='vp9'||v.width!==720||v.height!==1080||Math.abs(evalRate(v.r_frame_rate)-20)>.01||v.tags?.alpha_mode!=='1'))throw Error('Terry loop must be transparent VP9, 720x1080, 20fps');
  const hash=sha(file),key=createHash('sha256').update(JSON.stringify({hash,seconds,inpoint,alpha,width,fps})).digest('hex').slice(0,20),dir=`.cache/media/${name}-${key}`,ext=alpha?'png':'jpg',count=Math.floor((seconds||duration)*fps+1e-4);
  if(!fs.existsSync(dir+'/ready.json')){fs.mkdirSync(dir,{recursive:true});const ff=['-y','-hide_banner','-loglevel','error','-nostdin','-threads','2','-filter_threads','2',...(alpha?['-c:v','libvpx-vp9']:[]),'-ss',String(inpoint),'-i',file,'-t',String(seconds||duration),'-an','-vf',`fps=${fps},scale='min(${width},iw)':-2:flags=${alpha?'lanczos':'neighbor'}`,...(alpha?['-pix_fmt','rgba']:['-q:v','2']),'-frames:v',String(count),'-threads','2',dir+`/%05d.${ext}`];execFileSync('nice',['-n','19','ffmpeg',...ff],{stdio:'pipe'});const actual=fs.readdirSync(dir).filter(n=>n.endsWith('.'+ext)).length;if(actual!==count)throw Error(`decoded ${actual}/${count}`);fs.writeFileSync(dir+'/ready.json',JSON.stringify({hash,count}));}
  return {available:true,file,sha256:hash,path:dir.replace('.cache/',''),ext,count,fps,width:v.width,height:v.height,duration,sourceIn:inpoint};
 }catch(e){return {available:false,file,reason:String(e.message).split('\n')[0]};}
}
function evalRate(s){const [a,b='1']=s.split('/').map(Number);return a/b;}
const result={slots:{},terry:{},quotes:{},quoteSource:null};for(const s of slots)result.slots[s.id]={...decode('footage/'+s.file,s.id,{seconds:s.end-s.start,inpoint:s.sourceIn}),placeholder:s.placeholder};
for(const [name,file] of Object.entries(terry.loops))result.terry[name]=decode(file,'terry-'+name,{alpha:true,width:720,fps:20});
if(fs.existsSync(terry.quoteSource)){
 const j=read(terry.quoteSource),list=Array.isArray(j)?j.map((q,i)=>({...q,id:q.id??`#/${i}`})):Array.isArray(j.quotes)?j.quotes:Object.entries(j).map(([id,v])=>typeof v==='string'?{id,text:v}:{id,...v});
 for(const q of list){if(typeof q.id!=='string'||typeof q.text!=='string')throw Error('Quotes require string id and text');if(result.quotes[q.id])throw Error('Duplicate quote id');result.quotes[q.id]=q.text;}
 result.quoteSource={file:terry.quoteSource,sha256:sha(terry.quoteSource)};
}
result.missing=[...Object.entries(result.slots).filter(([,s])=>!s.available).map(([id,s])=>`${id}: ${s.reason}`),...Object.entries(result.terry).filter(([,s])=>!s.available).map(([id,s])=>`terry/${id}: ${s.reason}`),...terry.quoteCues.filter(c=>!c.id||!result.quotes[c.id]).map(c=>`${c.slot}: approved quote id pending`)];
fs.writeFileSync('.cache/media.json',JSON.stringify(result,null,2));console.log(`Media ready: ${8-Object.values(result.slots).filter(s=>!s.available).length}/8 live slots. ${result.missing.length} labelled missing inputs.`);
if(process.argv.includes('--final')&&result.missing.length)throw Error('Final mode requires all footage, Terry loops and approved quote IDs. See .cache/media.json.');
