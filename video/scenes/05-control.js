export async function draw(g,t,{D,M,copy,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,5,'05 / HANDOVER');D.type(g,copy[0],60,V?214:195,V?110:134,D.P.yellow,W-120);
 const q=D.smooth(t/1.0);D.line(g,60,V?292:235,W-60,V?292:235,D.P.cyan,7);D.line(g,60,V?292:235,60+(W-120)*q,V?292:235,D.P.yellow,7);
 await M.footage(g,'control',t,60,V?385:305,V?960:1530,V?710:586);if(V)await M.host(g,'idle',t,265,1125,540,460);else await M.host(g,'idle',t,1570,489,285,410);
 D.type(g,copy[1],60,V?1636:933,V?67:43,D.P.yellow,W-120);
}
