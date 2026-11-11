export async function draw(g,t,{D,M,copy,W,H,V,intensity}){
 D.background(g,t,W,H,intensity);D.mast(g,W,9,'09 / BUILD TOGETHER');D.type(g,copy[0],60,V?210:197,V?106:136,D.P.cyan,W-120);
 if(V){D.box(g,60,327,960,198,D.P.panel,6);D.mono(g,'hermes plugins install',83,402,36,D.P.white);D.mono(g,'mojomast/hermes-templeos --enable',83,469,35,D.P.yellow);D.mono(g,copy[2],60,612,31,D.P.white);D.mono(g,copy[3],60,672,31,D.P.white);D.wrap(g,'Plugin install. QEMU and the custom guest image are separate.',60,747,950,28,D.P.silver,{maxLines:2});M.quote(g,'closing-quote',60,928,960,178);await M.host(g,'speaking',t,270,1120,540,520);}
 else{D.box(g,60,337,1220,114,D.P.panel,6);D.mono(g,copy[1],85,407,29,D.P.yellow);D.mono(g,copy[2],65,567,34,D.P.white);D.mono(g,copy[3],65,635,34,D.P.white);D.wrap(g,'Plugin install. QEMU and the custom guest image are separate.',65,724,1120,30,D.P.silver,{maxLines:2});await M.host(g,'speaking',t,1370,420,440,485);M.quote(g,'closing-quote',1170,222,660,178)}
}
