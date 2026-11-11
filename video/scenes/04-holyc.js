export async function draw(g,t,{D,M,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,4,'04 / HOLYC');
 if(V){D.type(g,'WRITE HOLYC.',60,215,118,D.P.white,960);D.type(g,'RUN IT. OPEN IT.',60,315,88,D.P.cyan,960);await M.footage(g,'holyc',t,60,390,960,700);await M.host(g,'typing',t,240,1100,590,500);}
 else{D.type(g,'WRITE',60,263,122,D.P.white,570);D.type(g,'HOLYC.',60,389,128,D.P.cyan,570);D.text(g,'Run it. Read it.',65,455,41,D.P.white);D.text(g,'Open the file.',65,511,41,D.P.white);await M.host(g,'typing',t,110,530,410,388);await M.footage(g,'holyc',t,680,203,1180,680);}
 D.mono(g,'FOUR TOOLS / ONE SHARED MACHINE',60,V?1656:928,V?28:27,D.P.yellow);
}
