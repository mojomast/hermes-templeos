export async function draw(g,t,{D,M,copy,W,H,V}){
 D.box(g,0,0,W,H,D.P.ink);D.mono(g,'IN MEMORY',60,V?170:140,30,D.P.yellow);D.line(g,60,V?218:190,W-60,V?218:190,D.P.gray,1);
 if(V){D.wrap(g,copy[0],60,400,960,72,D.P.white,{font:'Display',weight:700,lineHeight:1.18,maxLines:4});D.wrap(g,copy[1],60,1080,950,42,D.P.silver,{maxLines:5,lineHeight:1.4});D.mono(g,'TEMPLEOS → TINKEROS → THE TEMPLE OF HERMES',60,1600,25,D.P.cyan)}
 else{D.wrap(g,copy[0],60,408,1790,80,D.P.white,{font:'Display',weight:700,lineHeight:1.2,maxLines:2});D.wrap(g,copy[1],60,706,1760,43,D.P.silver,{maxLines:3,lineHeight:1.4});D.mono(g,'TEMPLEOS → TINKEROS → THE TEMPLE OF HERMES',60,934,30,D.P.cyan)}
}
