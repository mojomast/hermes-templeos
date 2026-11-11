export async function draw(g,t,{D,M,copy,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,3,'03 / AGENT');D.type(g,copy[0],60,V?215:193,V?94:122,D.P.cyan,W-120);
 await M.footage(g,'agent',t,60,V?360:270,V?960:1280,V?690:620);await M.host(g,'typing',t,V?250:1350,V?1115:235,V?580:500,V?510:675);
 const labels=['SEE','CLICK','TYPE','FILES'],active=Math.min(3,Math.floor(t/2));labels.forEach((s,i)=>{const x=60+i*(V?240:312);D.box(g,x,V?1090:915,V?215:287,V?55:33,i===active?D.P.cyan:D.P.panel,2);D.mono(g,s,x+18,V?1127:940,V?29:23,i===active?D.P.ink:D.P.silver)});
}
