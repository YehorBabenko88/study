"""App-local stdlib installer orchestration; planning never downloads or installs."""
import argparse
import json
import re
from pathlib import Path
import socket
import sys
import time

# Official embedded Python starts isolated; add only this reviewed source directory.
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def artifact_summary(manifest,artifact_ids=None):
    result=[]
    licenses={row['id']:row for row in manifest.get('licenses',[]) if isinstance(row,dict) and row.get('id')}
    for artifact in manifest.get('artifacts',[]):
        if artifact_ids is not None and artifact.get('id') not in artifact_ids:continue
        row={key:artifact.get(key) for key in ('id','component','kind','version','size','license_id','sha256','url','source_revision','source_model_card','model_card_url','license_document')}
        if artifact.get('kind')=='model':
            evidence=licenses.get(artifact.get('license_id'),{})
            row['license_document']=artifact.get('license_document') or evidence.get('license_document') or evidence
            document=row['license_document'] if isinstance(row['license_document'],dict) else {}
            row['source_model_card']=artifact.get('source_model_card') or artifact.get('model_card_url') or artifact.get('model_card') or evidence.get('source_model_card') or evidence.get('model_card_url') or document.get('source_model_card') or document.get('model_card_url')
        result.append(row)
    return result


def readonly_summary(manifest,config,audit=None,mode='disabled'):
    return {'status':'READ_ONLY','mode':mode,'actual_host':socket.gethostname(),
            'target_host':'LS5','filesystem_mutation':False,'network_performed':False,
            'artifact_metadata_eligible':manifest.get('release_ready',False),
            'metadata_eligibility_scope':manifest.get('release_ready_scope','candidate_metadata_only'),
            'runtime_acceptance':manifest.get('runtime_acceptance','not_tested'),
            'physical_acceptance':'NOT_PERFORMED',
            'artifacts':artifact_summary(manifest),'hardware_audit':audit,
            'app_root':config.get('app_root'),
            'blockers':manifest.get('release_blockers',manifest.get('blockers',manifest.get('release_gates',[]))),
            'component_gates':{name:item.get('release_gates',[]) for name,item in manifest.get('components',{}).items()},
            'notes':['Candidate metadata is not an installable dependency lock.',
                     'Execution requires fresh LS5 audit and exact immutable plan approval.',
                     'No GPU/model/package choice is inferred from missing hardware data.']}


def assert_execution_host():
    if socket.gethostname().upper()!='LS5':
        raise ValueError('PC1 is development only; execution requires actual LS5 hostname')


def verify_plan_context(plan,manifest,audit,config,digest):
    if plan.get('target_host')!='LS5' or plan.get('manifest_sha256')!=digest(manifest) or plan.get('audit_sha256')!=digest(audit):
        raise ValueError('Saved plan does not match the reviewed manifest/audit')
    # Never execute a plan file which silently changes the selected configuration.
    if plan.get('config')!=json.loads(json.dumps(config,default=str)):
        raise ValueError('Saved plan configuration differs from the selected configuration')


def ask_approval(plan,manifest,digest,input_fn=input):
    plan_hash=digest(plan)
    selected=artifact_summary(manifest,set(plan.get('artifact_ids',[])))
    for artifact in selected:
        if artifact['kind']=='model':
            evidence=artifact['license_document']
            card=artifact['source_model_card'];card_url=card.get('url','') if isinstance(card,dict) else card
            if (not isinstance(evidence,dict) or not str(evidence.get('url','')).startswith('https://')
                    or not re.fullmatch('[0-9a-f]{64}',str(evidence.get('sha256','')))
                    or evidence.get('sha256')=='0'*64 or not str(card_url or '').startswith('https://')):raise ValueError('Selected model needs an actual pinned license document URL/hash and source model card before approval')
    print(json.dumps({'exact_installation_plan':plan,'plan_sha256':plan_hash,
                      'selected_artifacts_and_license_evidence':selected,
                      'selected_artifact_total_bytes':sum(item.get('size') or 0 for item in selected),
                      'approved_download_byte_budget':plan.get('approved_download_bytes',0)},ensure_ascii=False,indent=2))
    if input_fn('Type the exact plan SHA256 to approve this transaction: ').strip()!=plan_hash:
        raise ValueError('Installation plan not approved')
    license_phrase='LICENSES '+(','.join(sorted(plan.get('accepted_licenses',[]))) or 'NONE')
    if input_fn('Type '+license_phrase+' to accept only these selected licenses: ').strip()!=license_phrase:
        raise ValueError('Selected licenses not accepted')
    download_phrase='DOWNLOAD '+str(plan.get('approved_download_bytes',0))
    if input_fn('Type '+download_phrase+' to approve this exact byte budget: ').strip()!=download_phrase:
        raise ValueError('Download budget not approved')
    return {'schema_version':1,'approved':True,'plan_sha256':plan_hash,
            'manifest_sha256':digest(manifest),'expires_at':int(time.time())+900,
            'model_license_accepted':True,'large_download_approved':True,
            'hardware_changes_approved':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=['plan','install','update','rollback','uninstall'],default='plan')
    parser.add_argument('--mode',choices=['managed','external','disabled'],default='disabled')
    parser.add_argument('--manifest',default=str(Path(__file__).with_name('release_catalog.json')))
    parser.add_argument('--config',required=True)
    parser.add_argument('--audit')
    parser.add_argument('--plan-file')
    parser.add_argument('--approval-file')
    parser.add_argument('--component',action='append',choices=['study','comfy'])
    parser.add_argument('--accepted-license',action='append',default=[])
    parser.add_argument('--approved-download-bytes',type=int,default=0)
    parser.add_argument('--device',choices=['cuda','cpu'])
    parser.add_argument('--cpu-opt-in',action='store_true')
    parser.add_argument('--rollback-transaction-id')
    args=parser.parse_args(argv)
    manifest=read_json(args.manifest);config=read_json(args.config)
    config.setdefault('bundle_root',str(Path(args.manifest).resolve().parent))
    audit=read_json(args.audit) if args.audit else None
    if args.action=='plan':
        result=readonly_summary(manifest,config,audit,args.mode)
        if audit is not None:
            try:
                from installer_engine import build_plan,canonical_digest
                plan=build_plan(manifest,audit,config,mode=args.mode,components=tuple(args.component or (['study','comfy'] if args.mode=='managed' else ['study'])),accepted_licenses=args.accepted_license,approved_download_bytes=args.approved_download_bytes,device=args.device,cpu_opt_in=args.cpu_opt_in)
                result.update(exact_plan=plan,plan_sha256=canonical_digest(plan))
            except (ImportError,ValueError,RuntimeError) as error:
                result['execution_blocker']=str(error)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    assert_execution_host()
    if args.action=='uninstall':
        from installer_uninstall import build_uninstall_plan,execute_uninstall
        from installer_engine import canonical_digest,validate_audit
        from study_service import load_config
        validate_audit(audit)
        if len(args.component or [])!=1:raise ValueError('Select exactly one component for removal')
        if args.component[0]=='comfy' and args.mode!='managed':raise ValueError('External/Disabled Comfy is never removed')
        config=load_config(args.config);config.setdefault('bundle_root',str(Path(args.manifest).resolve().parent))
        if args.plan_file:
            plan=read_json(args.plan_file)
            if (plan.get('operation')!='uninstall' or plan.get('target_host')!='LS5'
                    or plan.get('component')!=args.component[0]
                    or Path(plan.get('app_root','')).resolve()!=Path(config['app_root']).resolve()
                    or Path(plan.get('data_dir','')).resolve()!=Path(config['study']['data_dir']).resolve()):
                raise ValueError('Saved removal plan differs from selected application/data/component context')
            # The executor validates the exact approval, active pointer/marker,
            # retention and interruption journal; rebuilding would allocate a
            # different random transaction and break recovery after deactivation.
        else:plan=build_uninstall_plan(config,args.component[0])
        print(json.dumps({'removal_plan':plan,'plan_sha256':canonical_digest(plan)},ensure_ascii=False,indent=2))
        if args.approval_file:approval=read_json(args.approval_file)
        else:
            if input('Type the exact removal plan SHA256: ').strip()!=canonical_digest(plan):raise ValueError('Removal not approved')
            if input('Type REMOVE '+args.component[0]+' to confirm only the selected owned component: ').strip()!='REMOVE '+args.component[0]:raise ValueError('Component removal not confirmed')
            approval={'approved':True,'plan_sha256':canonical_digest(plan),'expires_at':int(time.time())+900}
        print(json.dumps(execute_uninstall(plan,approval),ensure_ascii=False,indent=2));return 0
    from installer_engine import InstallerEngine,build_plan,canonical_digest,validate_audit
    from study_service import load_config
    config=load_config(args.config);config.setdefault('bundle_root',str(Path(args.manifest).resolve().parent))
    validate_audit(audit)
    if args.plan_file:
        plan=read_json(args.plan_file)
        verify_plan_context(plan,manifest,audit,config,canonical_digest)
        if plan.get('mode')!=args.mode:raise ValueError('Saved plan mode differs from selected mode')
        expected='rollback' if args.action=='rollback' else 'install'
        if plan.get('action','install') not in (expected,args.action):raise ValueError('Saved plan action differs from selected operation')
    else:
        # No model/CPU/GPU choice is silently inferred. Managed execution must
        # have a reviewed saved plan with compatibility decisions and licenses.
        if args.mode=='managed':raise ValueError('Managed execution requires an exact reviewed plan file; hardware/model/dependency choices cannot be inferred')
        options={}
        if args.action=='rollback':
            if not args.rollback_transaction_id:raise ValueError('Rollback requires an explicitly selected transaction')
            options.update(action='rollback',rollback_transaction_id=args.rollback_transaction_id)
        plan=build_plan(manifest,audit,config,mode=args.mode,components=tuple(args.component or ['study']),**options)
        selected=set(plan['artifact_ids'])
        licenses=sorted({item['license_id'] for item in manifest.get('artifacts',[]) if item.get('id') in selected and item.get('license_id')})
        plan['accepted_licenses']=args.accepted_license or licenses
        if args.approved_download_bytes:plan['approved_download_bytes']=args.approved_download_bytes
    approval=read_json(args.approval_file) if args.approval_file else ask_approval(plan,manifest,canonical_digest)
    engine=InstallerEngine(manifest,plan,approval,audit)
    result=engine.rollback() if args.action=='rollback' else engine.execute()
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError,EOFError) as error:
        print(json.dumps({'status':'REFUSED','error':str(error),'automatic_approval':False}),file=sys.stderr)
        raise SystemExit(2)
