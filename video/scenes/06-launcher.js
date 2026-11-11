export async function draw(g,t,{D,M,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,6,'06 / LAUNCHER');
 if(V){D.type(g,'18 ENTRIES.',60,230,145,D.P.yellow,960);D.type(g,'ONE LAUNCHER.',60,333,95,D.P.white,960);await M.footage(g,'launcher',t,60,410,960,720);await M.host(g,'wave',t,265,1145,540,450);}
 else{D.type(g,'18',60,389,280,D.P.yellow,570);D.type(g,'ENTRIES.',70,488,80,D.P.white,540);D.mono(g,'6 × 3 GRID',73,557,36,D.P.cyan);await M.host(g,'wave',t,135,578,370,335);await M.footage(g,'launcher',t,650,180,1210,720,{push:Math.min(.008,t*.001)});}
 D.mono(g,'TEMPLE IS HOME / ABOUT IS HELP',60,V?1660:938,V?28:26,D.P.silver);
}
