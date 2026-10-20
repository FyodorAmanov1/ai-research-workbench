"""Explicitly ingest only named public companion study JSON, without network access."""
import argparse
import hashlib
import json
from pathlib import Path

PROJECTS=['quantum-estimation-lab','quantum-optimization-lab','market-microstructure-lab','statistical-learning-lab']


def ingest(workspace):
    documents=[]
    for project in PROJECTS:
        raw=(workspace/project/'docs/study.json').read_bytes();study=json.loads(raw)
        if study['slug']!=project:raise ValueError('Unexpected project identity')
        artifact=hashlib.sha256(raw).hexdigest()
        for case in study['cases']:
            title=study['title']+' / '+case['label']
            text='\n'.join([case['description'],*[f"{m['label']}: {m['value']} {m.get('unit','')}" for m in case['metrics']],*case['method'],'Limitations:',*case['limitations']])
            documents.append({'id':project+':'+case['id'],'title':title,'project':project,'url':f'https://github.com/FyodorAmanov1/{project}/blob/main/docs/study.json','demo':f'https://fyodoramanov1.github.io/{project}/#{case["id"]}',
              'artifact_sha256':artifact,'sha256':hashlib.sha256(text.encode()).hexdigest(),'text':text,'metrics':case['metrics']})
    return {'schema_version':1,'description':'Explicit snapshot of four public companion studies; not a live index.','documents':documents}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--out',type=Path,default=Path('docs/registry.json'));a=parser.parse_args()
    payload=ingest(a.workspace.resolve());a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8');print(f'Indexed {len(payload["documents"])} source records')
