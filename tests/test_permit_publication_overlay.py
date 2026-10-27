"""Execute the deployed overlay JS against row/cell stubs without network."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_new_publication_overlays_stale_tel_hai_status_but_not_deadline():
    source = (ROOT / 'src/ginot/page.py').read_text()
    overlay = source.split('function applyPublicationEvidence(){', 1)[1].split("fetch('publications_active.json')", 1)[0]
    js = '''
const TODAY='2026-10-27';
const PUBLICATION_EVIDENCE_MAX_DAYS=90;
const original={"data-tik":"1975/0743.02","data-group":"review","data-active":"1",
"data-status":"שולמה מקדמה","data-pub":"","data-pubend":""};
function validIso(s){return /^\\d{4}-\\d{2}-\\d{2}$/.test(s||'')&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;}
const cell={textContent:'',setAttribute(k,v){this[k]=v;}};
const row={a:{...original},querySelector(){return cell;},getAttribute(k){return this.a[k];},setAttribute(k,v){this.a[k]=v;}};

var rows=[row],publicationEvidence=[];
function applyPublicationEvidence(){
''' + overlay + '''
const results=[];
for(const [inside,date,active,current] of [[true,'2026-10-26','1',''],[false,'2026-10-26','1',''],[null,'2026-10-26','1',''],[true,'2026-02-30','1',''],[true,'2026-10-26','0',''],[true,'2026-10-20','1','2026-10-26'],[true,'2026-10-26','1','2026-10-26'],[true,'2019-04-17','1',''],[true,'2026-10-28','1',''],[true,'2026-07-28','1','']]){
 row.a={...original,'data-active':active,'data-pub':current};cell.textContent='';
 publicationEvidence=[{tik_num:'1975/0743.02',in_polygon:inside,publication_date:date}];
 applyPublicationEvidence();results.push({attrs:{...row.a},text:cell.textContent});
}
const stageResults=[];
for(const [group,stage,date] of [['postpub','2026-10-27','2026-10-26'],['postpub','','2026-10-26'],['review','2026-10-27','2026-10-26'],['postpub','2026-10-25','2026-10-26']]){
 row.a={...original,'data-group':group,'data-statusdate':stage};
 publicationEvidence=[{tik_num:'1975/0743.02',in_polygon:true,publication_date:date}];
 applyPublicationEvidence();stageResults.push({...row.a});
}
console.log(JSON.stringify({results,stageResults}));
'''
    r = subprocess.run(['node', '-e', js], text=True, capture_output=True, check=False)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    results = payload['results']
    stages = payload['stageResults']
    assert [x['data-group'] for x in stages] == ['postpub', 'postpub', 'review', 'obj']
    first = results[0]
    assert first['attrs']['data-group'] == 'obj'
    assert first['attrs']['data-pub'] == '2026-10-26'
    assert first['attrs']['data-status'] == 'שולמה מקדמה'
    assert first['attrs']['data-pubend'] == ''  # no fabricated deadline
    assert 'פרסום עירוני' in first['text']
    assert all(x['attrs']['data-group'] == 'review' for x in results[1:])


def test_superseded_planned_end_is_preserved_but_does_not_hide_new_publication():
    source = (ROOT / 'src/ginot/page.py').read_text()
    body = source.split("    var evidence=r.getAttribute('data-publication-evidence')||'';", 1)[1].split("  if(!pfclosed.checked", 1)[0].rsplit('  }', 1)[0]
    # Execute the exact end-date filter fragment, including its return-false.
    js = """
function validIso(v){return /^\\d{4}-\\d{2}-\\d{2}$/.test(v||'');}
const TODAY='2026-10-27';
function visible(pe,evidence){
const r={getAttribute(){return evidence;}};
var evidence=r.getAttribute('data-publication-evidence')||'';
""" + body + """
return true;}
console.log(JSON.stringify([visible('2026-09-01','2026-10-26'),visible('2026-09-01',''),visible('2026-10-28','2026-10-26'),visible('2026-09-01','2026-09-01')]));
"""
    result = subprocess.run(['node', '-e', js], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [True, False, True, False]
    assert "r.setAttribute('data-pubend'" not in source.split('function applyPublicationEvidence(){', 1)[1].split("fetch('publications_active.json')", 1)[0]
