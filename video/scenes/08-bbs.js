export async function draw(g,t,{D,M,copy,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,8,'08 / HBBS/1');D.type(g,copy[0],60,V?185:167,V?85:96,D.P.white,W-120);D.type(g,copy[1],60,V?280:258,V?84:88,D.P.cyan,W-120);
 const boards=['General chat','Agent-to-agent','HolyC code share','Nous lore','Announcements'];
 if(V){await M.footage(g,'bbs',t,60,365,960,720);boards.forEach((s,i)=>{D.mono(g,String(i+1).padStart(2,'0'),70,1170+i*78,29,D.P.cyan);D.text(g,s,140,1170+i*78,37,D.P.white)});D.wrap(g,'HBBS/1 • COM2 SERIAL MODEM • OPT-IN HOST RELAY',60,1620,960,29,D.P.yellow,{maxLines:2});}
 else{boards.forEach((s,i)=>{D.mono(g,String(i+1).padStart(2,'0'),60,377+i*94,29,D.P.cyan);D.text(g,s,126,377+i*94,35,D.P.white);D.line(g,60,404+i*94,558,404+i*94,D.P.gray,1)});await M.footage(g,'bbs',t,620,313,1240,572);D.mono(g,'HBBS/1 • COM2 SERIAL MODEM • OPT-IN HOST RELAY',60,936,27,D.P.yellow)}
}
