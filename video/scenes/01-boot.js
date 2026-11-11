export async function draw(g,t,{D,M,copy,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,1,'01 / BOOT');const p=D.ease(t/.7);g.save();g.globalAlpha=.7+.3*p;D.type(g,copy[0],60,V?190:203,V?102:118,D.P.white,W-120);D.type(g,copy[1],60,V?305:326,V?102:118,D.P.cyan,W-120);g.restore();
 await M.footage(g,'boot',t,60,V?385:409,V?960:940,V?700:465,{push:t*.001});const move=D.smooth(t/2.7);await M.host(g,t<3.6?'walk':'wave',t,V?610:1400-(1-move)*400,V?1125:320,V?410:490,V?520:585);
 if(t>=5.5)M.quote(g,'opening-quote',V?60:1135,V?1150:125,V?545:690,172);
 if(!V)D.mono(g,copy[2],63,921,26,D.P.yellow);else D.wrap(g,copy[2],62,1430,520,30,D.P.yellow,{maxLines:3});
}
