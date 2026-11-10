/* Dependency-free reference renderer. This is integration source, not a plugin.
 * Input: baked-presets.json-shaped data, parts.json registry, smoke.json.
 * Assets are straight-alpha RGBA. Canvas performs its own alpha handling.
 */
(function(root){
'use strict';
const lerp=(a,b,t)=>a+(b-a)*t;
const angle=(a,b,t)=>a+(((b-a+540)%360)-180)*t;
function sample(clip,time){
  const count=clip.frames.length,duration=clip.duration_ms;
  const phase=clip.loop===false ? Math.max(0,Math.min(1,time/duration))*(count-1)
    : (((time%duration)+duration)%duration)/duration*count;
  // Complete pre-solved poses preserve all bone lengths and attachment points.
  return structuredClone(clip.frames[Math.min(count-1,Math.floor(phase))]);
}
function speechAt(events,time,fallback='neutral'){
  let chosen=fallback;
  for(const event of events){if(event.time_ms>time)break;chosen=event.plate;}
  return chosen;
}
function solveTwoBone(shoulder,target,a=24,b=22,bend=1){
  const dx=target[0]-shoulder[0],dy=target[1]-shoulder[1];
  const d=Math.max(Math.abs(a-b)+.001,Math.min(a+b-.001,Math.hypot(dx,dy)));
  const clamp=v=>Math.max(-1,Math.min(1,v));
  return {shoulder_deg:(Math.atan2(-dx,dy)-bend*Math.acos(clamp((a*a+d*d-b*b)/(2*a*d))))*180/Math.PI,
    elbow_deg:bend*Math.acos(clamp((d*d-a*a-b*b)/(2*a*b)))*180/Math.PI};
}
class Renderer{
  constructor(canvas,data,base='../modular/'){
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.data=data;this.base=base;
    this.images=new Map();this.particles=[];this.last=0;this.next=0;this.seed=721;
  }
  random(){this.seed=(Math.imul(1664525,this.seed)+1013904223)>>>0;return this.seed/4294967296;}
  async load(){
    const paths=new Set();
    for(const slot of Object.values(this.data.registry.slots))for(const p of Object.values(slot.variants||{}))paths.add(p);
    for(const asset of Object.values(this.data.smoke.assets))paths.add('../'+asset.path);
    await Promise.all([...paths].map(path=>new Promise((resolve,reject)=>{
      const image=new Image();image.onload=()=>{this.images.set(path,image);resolve();};
      image.onerror=()=>reject(new Error('Could not load '+path));image.src=this.base+path;
    })));
  }
  reset(){this.particles=[];this.next=0;this.last=0;this.seed=721;}
  drawPose(frame,costume='base',headOverride=null,options={}){
    const ctx=this.ctx,registry=this.data.registry;
    const p=structuredClone(frame.parts),variants={...(frame.variants||{})};
    const c=this.data.costumes[costume];
    if(c){Object.assign(variants,c.replace||{});for(const ov of c.overlays||[]){if(!p[ov.follow])continue;p[ov.slot]={...p[ov.follow]};variants[ov.slot]=ov.variant;}}
    if(headOverride)variants.head_base=headOverride;
    const list=Object.entries(p).filter(([s,pose])=>registry.slots[s] && pose.alpha!==0 && !frame.hidden_slots?.includes(s));
    list.sort(([a,pa],[b,pb])=>(registry.slots[a].layer+(pa.layer_boost||0))-(registry.slots[b].layer+(pb.layer_boost||0))||a.localeCompare(b));
    for(const [slot,pose]of list){
      if(pose.visible===false||frame.visibility?.[slot]===false||frame.props?.[slot]===false)continue;
      if(slot==='smoke'&&options.hideStaticSmoke)continue;
      const spec=registry.slots[slot];let variant=variants[slot]||pose.variant||'default';
      if(slot.startsWith('eye_')&&variant==='default')variant='open';
      if((slot.startsWith('brow_')||slot==='mouth')&&variant==='default')variant='neutral';
      const path=spec.variants[variant]||spec.variants.default;
      if(!path)continue;const image=this.images.get(path);if(!image)continue;
      const pivot=pose.pivot||spec.pivot;
      ctx.save();ctx.globalAlpha=pose.alpha??1;ctx.translate(pose.x,pose.y);
      ctx.rotate((pose.rot||0)*Math.PI/180);
      ctx.scale((pose.flip?-1:1)*(pose.sx??1),pose.sy??1);
      // Mirroring follows the compositor's width-1-pivot convention.
      ctx.drawImage(image,-pivot[0],-pivot[1]);ctx.restore();
    }
  }
  emit(preset,origin,now){
    if(this.particles.length>=preset.max_particles)return;
    const keys=preset.textures,key=keys[Math.floor(this.random()*keys.length)];
    const rand=(a,b)=>lerp(a,b,this.random());
    this.particles.push({key,x:origin[0],y:origin[1],birth:now,life:rand(...preset.life_ms),
      vx:rand(...preset.velocity_x),vy:rand(...preset.velocity_y),ay:preset.acceleration_y,
      scale:rand(...preset.scale_start),end:preset.scale_end,alpha:preset.opacity,
      rot:rand(-.1,.1),spin:rand(-.12,.12),phase:rand(0,Math.PI*2)});
  }
  smoke(presetName,origin,now,emitting=true){
    const preset=this.data.smoke.presets[presetName],ctx=this.ctx;
    // Birth positions are world positions. Old particles never follow the hand.
    if(preset&&emitting&&now>=this.next){this.emit(preset,origin,now);this.next=now+1000/preset.rate_per_second;}
    this.particles=this.particles.filter(p=>now-p.birth<p.life);
    for(const p of this.particles){
      const ms=now-p.birth;if(ms<0)continue;const age=ms/1000,u=ms/p.life;
      const spec=this.data.smoke.assets[p.key],image=this.images.get('../'+spec.path);if(!image)continue;
      const fade=Math.min(1,u/.12)*Math.pow(1-u,1.8);
      ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha=p.alpha*fade;
      ctx.translate(p.x+p.vx*age+Math.sin(age*2+p.phase)*2,p.y+p.vy*age+.5*p.ay*age*age);
      ctx.rotate(p.rot+p.spin*age);const scale=lerp(p.scale,p.end,u);ctx.scale(scale,scale);
      ctx.drawImage(image,-spec.anchor[0],-spec.anchor[1]);ctx.restore();
    }
  }
}
root.TerryCompanion={Renderer,sample,speechAt,solveTwoBone};
if(typeof module!=='undefined')module.exports=root.TerryCompanion;
})(typeof window!=='undefined'?window:globalThis);
