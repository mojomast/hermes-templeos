"""Import the updated integration branch's exact HD loops and quote catalogue."""
from pathlib import Path
import json,hashlib,shutil,subprocess
r=Path(__file__).resolve().parents[1];repo=r.parent;commit='0f50faac279f7a669e66a13d0b1ce881a7a86917';base='desktop/assets/companion/terry/v5';catalog=json.loads((repo/base/'clips.json').read_text());provenance=json.loads((r/'assets/provenance.json').read_text())
def copy(source,dest,license):
 p=r/dest;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(repo/source,p);sha=hashlib.sha256(p.read_bytes()).hexdigest();provenance['assets']=[a for a in provenance['assets'] if a['path']!=dest];provenance['assets'].append({'path':dest,'url':f'https://github.com/mojomast/hermes-templeos/blob/{commit}/{source}','sha256':sha,'license':license,'transform':'unchanged'});return sha
for name,c in catalog['clips'].items():assert copy(base+'/'+c['file'],'assets/terry/'+name+'.webm','Original fan tribute; repository MIT')==c['sha256']
copy('desktop/terry-quotes.json','assets/terry/approved-quotes.json','Verbatim sourced quotations; catalogue from repository MIT')
for name in ['README.md','clips.json']:copy(base+'/'+name,'assets/terry/v5-'+name,'Repository MIT')
for name in ['pane-1920x1240','pane-typing']:copy('docs/images/'+name+'.png','assets/placeholders/'+name+'.png','Repository MIT; original guest public domain')
provenance['pluginCommit']=commit;(r/'assets/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');print('Imported six verified HD loops, exact quote catalogue and updated README screenshots.')
