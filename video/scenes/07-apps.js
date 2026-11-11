export async function draw(g,t,{D,M,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,7,'07 / APPS + LORE');const names=['WORLDSIM.','CAPYBARA. DOJO.','MESSENGER. CADUCEUS.','CODEX. OFFERINGS.'];const k=t<3?0:t<6?1:t<9?2:3;
 D.type(g,names[k],60,V?205:183,V?91:110,k===3?D.P.yellow:D.P.white,W-120);if(V)D.type(g,'A WHOLE TEMPLE TO EXPLORE.',60,295,60,D.P.cyan,960);
 await M.footage(g,'apps',t,60,V?395:260,V?960:1360,V?710:628,{push:Math.sin(t*.4)*.004+.004});await M.host(g,k===3?'idle':'wave',t,V?280:1430,V?1140:305,V?520:420,V?440:590);
 if(k===3)D.wrap(g,'CHARACTERS FROM THE NOUS UNIVERSE',60,V?1625:933,W-120,V?34:30,D.P.yellow,{maxLines:2});else D.mono(g,'REAL APPS / ACTUAL CAPTURE SLOT',60,V?1650:933,V?29:26,D.P.cyan);
}
