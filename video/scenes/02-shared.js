export async function draw(g,t,{D,M,copy,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,2,'02 / SHARED');D.type(g,copy[0],60,V?195:171,V?83:91,D.P.white,W-120);D.type(g,copy[1],60,V?292:254,V?66:78,D.P.cyan,W-120);
 await M.footage(g,'shared',t,60,V?380:322,V?960:1280,V?675:560,{push:Math.min(.01,t*.0007)});await M.host(g,'idle',t,V?275:1360,V?1100:300,V?530:470,V?490:594);
 const y=V?1100:925;D.line(g,60,y,V?300:650,y,D.P.cyan,5);D.line(g,V?700:650,y,W-60,y,D.P.yellow,5);if(V)D.mono(g,'HUMAN  +  AGENT',60,1658,32,D.P.yellow);
}
