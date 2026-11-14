"""Isolated scoring of a fixed released jq test subset; no model grader."""
import argparse
import base64
from contextlib import contextmanager
from hashlib import sha256
import json
import io
from importlib.metadata import version
import os
from pathlib import Path, PurePosixPath
import secrets
import shlex
import subprocess
import stat
import sys
import zipfile
import tarfile
from unittest.mock import patch

from swarmform.programbench_pilot import specification
from workstation import DockerWorkstation, IMAGE


def file_hash(path):
    value=sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024*1024):value.update(chunk)
    return value.hexdigest()


def candidate_files(raw):
    """One complete, content-bound submission; never combine live directory reads."""
    if not isinstance(raw,bytes) or len(raw)>2_000_000:
        raise ValueError('Candidate archive exceeds the 2 MB artifact allowance')
    files={}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos=archive.infolist()
            if len(infos)>512 or sum(i.file_size for i in infos)>24_000_000:
                raise ValueError('Candidate archive exceeds its member/expanded-size allowance')
            for item in infos:
                name=item.filename;path=PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or '\\' in name:
                    raise ValueError('Invalid archive member path')
                mode=stat.S_IFMT(item.external_attr>>16)
                if item.is_dir():
                    if mode not in (0,stat.S_IFDIR):raise ValueError('Unsupported archive directory type')
                    continue
                if (not name or name!=str(path) or name in files or mode not in (0,stat.S_IFREG)
                        or item.flag_bits&1 or item.file_size>2_000_000):
                    raise ValueError('Archive needs unique regular unencrypted files')
                files[name]=archive.read(item)
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as error:
        raise ValueError('Unreadable candidate archive') from error
    if 'executable' not in files or len(files)>256:
        raise ValueError('Candidate needs a root executable and at most 256 files')
    for name in files:
        if any(str(parent) in files for parent in PurePosixPath(name).parents if str(parent)!='.'):
            raise ValueError('Archive member conflicts with a parent file')
    return files


def test_nodeids(suite):
    nodes=[]
    for name in specification()['selected_tests']:
        stem,sep,param=name.partition('[');parts=stem.split('.')
        nodes.append(str(Path(suite)/'eval'/parts[0]/(parts[1]+'.py'))+'::'+
                     '::'.join(parts[2:])+(sep+param if sep else ''))
    return nodes


def extract_suite(archive, destination):
    archive,destination=Path(archive),Path(destination)
    if file_hash(archive)!=specification()['test_archive_sha256']:
        raise ValueError('Official test archive differs from its fixed identity')
    destination.mkdir(parents=True,exist_ok=False)
    with tarfile.open(archive) as source:
        members=[m for m in source.getmembers() if m.name=='parse_jq_tests.py'
                 or m.name.startswith(('eval/','tests/'))]
        source.extractall(destination,members=members,filter='data')
    return {p.relative_to(destination).as_posix():file_hash(p)
            for p in destination.rglob('*') if p.is_file() and not p.is_symlink()}


@contextmanager
def evaluation_station(files):
    """Use the read-only program mount for a candidate; no oracle is installed."""
    for name,raw in files.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or not isinstance(raw,bytes):
            raise ValueError('Invalid candidate member')
    volume='office-reference-'+secrets.token_hex(8)
    subprocess.run(['docker','volume','create','--label','org.swarmharm.managed=true',
                    '--label',f'org.swarmharm.owner-pid={os.getpid()}',volume],
                   check=True,capture_output=True,timeout=20)
    station=None
    try:
        code='''import base64,json,sys
from pathlib import Path
root=Path('/opt/reference')
for name,body in json.load(sys.stdin).items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(base64.b64decode(body,validate=True))
 p.chmod(0o555)
for p in root.rglob('*'):
 if p.is_dir():p.chmod(0o555)
root.chmod(0o555)
'''
        subprocess.run(['docker','run','--rm','-i','--pull=never','--network=none','--read-only',
            '--cap-drop=ALL','--security-opt=no-new-privileges','--user=0:0',
            '--mount',f'type=volume,src={volume},dst=/opt/reference',IMAGE,'python','-I','-c',code],
            input=json.dumps({p:base64.b64encode(v).decode() for p,v in files.items()}),
            text=True,check=True,capture_output=True,timeout=30)
        station=DockerWorkstation({},reference_volume=volume,registry_enabled=False,
                                  environment={'HOME':'/workspace'})
        yield station
    finally:
        if station is not None:station.close()
        subprocess.run(['docker','volume','rm',volume],check=True,capture_output=True,timeout=20)


def evaluate(candidate_archive, archive, output):
    # One fresh CLI process per candidate avoids pytest module-cache reuse.
    import pytest
    from swarmform import programbench_pilot
    import workstation
    repository = Path(programbench_pilot.__file__).resolve().parents[2]
    runtime = {'python': sys.version.split()[0], 'pytest': pytest.__version__,
               'pytest_timeout': version('pytest-timeout')}
    if (sys.version_info[:2] != (3, 12) or runtime['pytest'] != '8.3.5'
            or runtime['pytest_timeout'] != '2.3.1'):
        raise ValueError('Use the pinned Python 3.12, pytest 8.3.5 and pytest-timeout 2.3.1 evaluator')
    sources = [Path(__file__).resolve(), Path(programbench_pilot.__file__).resolve(),
               *Path(workstation.__file__).resolve().parent.glob('*.py'),
               Path(programbench_pilot.__file__).with_name('fixtures') / 'programbench-jq.json']
    code_hashes = {p.relative_to(repository).as_posix(): file_hash(p) for p in sources}
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(repository):
        raise ValueError('Choose an evaluator output directory outside the repository')
    if output.exists():raise FileExistsError(output)
    candidate_raw=Path(candidate_archive).read_bytes()
    files=candidate_files(candidate_raw)
    hashes={p:sha256(v).hexdigest() for p,v in sorted(files.items())}
    output.mkdir(parents=True)
    suite=output/'suite';test_hashes=extract_suite(archive,suite)
    executable=suite/'executable';executable.write_text('Evaluator placeholder; never executed on the host.\n')
    os.environ['JQ_BINARY']=str(executable)
    nodes=test_nodeids(suite);calls=[];reports=[];collected=[];transport_errors=[]
    original_run=subprocess.run
    class Report:
        def pytest_collection_finish(self,session):collected.extend(x.nodeid for x in session.items)
        def pytest_runtest_logreport(self,report):
            reports.append({'nodeid':report.nodeid,'phase':report.when,'outcome':report.outcome,
                'duration':report.duration,'failure':str(report.longrepr) if report.failed else None})

    with evaluation_station(files) as station:
        (output/'workstation.json').write_text(json.dumps({'name':station.name,'image':IMAGE})+'\n')
        def isolated_run(args,*positional,**kwargs):
            if not isinstance(args,(tuple,list)) or not args or str(args[0]) not in (
                    str(executable),'./executable','/workspace/executable'):
                return original_run(args,*positional,**kwargs)
            assert not positional and not kwargs.get('shell')
            assert str(kwargs.get('cwd')) in ('None','/workspace',str(suite))
            translated=['/opt/reference/executable'];installed={}
            for arg in args[1:]:
                value=str(arg);path=Path(value)
                if path.is_absolute() and path.exists():
                    dest='/workspace/.cli-inputs/'+sha256(value.encode()).hexdigest()[:16]
                    if path.is_dir():
                        for file in path.rglob('*'):
                            if file.is_file() and file.suffix in ('.jq','.json'):
                                installed[dest+'/'+str(file.relative_to(path))]=base64.b64encode(file.read_bytes()).decode()
                    else:installed[dest]=base64.b64encode(path.read_bytes()).decode()
                    translated.append(dest)
                else:translated.append(value)
            data=kwargs.get('input') or b''
            if isinstance(data,str):data=data.encode(kwargs.get('encoding') or 'utf-8')
            request={'argv':translated,'stdin':base64.b64encode(data).decode(),'files':installed,
                'env':{k:v for k,v in kwargs.get('env',{}).items() if k in ('LC_ALL','LANG','PAGER')}}
            code='''import base64,json,os,subprocess,sys
from pathlib import Path
r=json.loads(base64.b64decode(sys.argv[1]))
for path,body in r['files'].items():
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(body))
try:
 x=subprocess.run(r['argv'],input=base64.b64decode(r['stdin']),capture_output=True,timeout=10,cwd='/opt/reference',env={**os.environ,**r['env']})
 out={'returncode':x.returncode,'stdout':base64.b64encode(x.stdout).decode(),'stderr':base64.b64encode(x.stderr).decode(),'timeout':False}
except subprocess.TimeoutExpired as e:
 out={'returncode':124,'stdout':base64.b64encode(e.stdout or b'').decode(),'stderr':base64.b64encode(e.stderr or b'').decode(),'timeout':True}
except OSError as e:
 out={'returncode':126,'stdout':'','stderr':base64.b64encode(str(e).encode()).decode(),'timeout':False}
print(json.dumps(out))
'''
            try:
                result,_=station.execute('python -I -c '+shlex.quote(code)+' '+
                    shlex.quote(base64.b64encode(json.dumps(request).encode()).decode()),{})
            except Exception as error:
                problem={'stage':'candidate transport','type':type(error).__name__,'message':str(error)}
                transport_errors.append(problem)
                (output/f'transport-error-{len(transport_errors):04d}.json').write_text(json.dumps(problem,indent=2)+'\n')
                raise RuntimeError('Candidate transport failed; evaluation is incomplete') from error
            if result['exit_code'] or result.get('output_truncated'):
                transport_errors.append(result)
                (output/f'transport-error-{len(transport_errors):04d}.json').write_text(json.dumps(result,indent=2)+'\n')
                raise RuntimeError('Candidate invocation exceeded transport limits or failed; raw result retained')
            try:
                response=json.loads(result['stdout'])
            except (KeyError,ValueError) as error:
                transport_errors.append(result)
                (output/f'transport-error-{len(transport_errors):04d}.json').write_text(json.dumps(result,indent=2)+'\n')
                raise RuntimeError('Candidate transport returned invalid data; evaluation is incomplete') from error
            record={'index':len(calls),'argv':list(map(str,args)),'translated_argv':translated,
                'stdin_sha256':sha256(data).hexdigest(),
                'installed':{p:sha256(base64.b64decode(v)).hexdigest() for p,v in installed.items()},
                'response':response}
            calls.append(record)
            (output/f'call-{len(calls):04d}.json').write_text(json.dumps(record,indent=2)+'\n')
            stdout,stderr=(base64.b64decode(response[k]) for k in ('stdout','stderr'))
            if kwargs.get('text') or kwargs.get('universal_newlines') or kwargs.get('encoding'):
                stdout,stderr=(v.decode(kwargs.get('encoding') or 'utf-8',kwargs.get('errors') or 'strict')
                    .replace('\r\n','\n').replace('\r','\n') for v in (stdout,stderr))
            completed=subprocess.CompletedProcess(args,response['returncode'],stdout,stderr)
            if kwargs.get('check'):completed.check_returncode()
            return completed
        with patch('subprocess.run',isolated_run):
            status=pytest.main(['-q','--tb=short','--timeout=45',*nodes],plugins=[Report()])
    result={'pytest_status':int(status),'transport_errors':len(transport_errors),'selected_count':len(nodes),'collected_count':len(collected),
        'passed_items':sum(r['phase']=='call' and r['outcome']=='passed' for r in reports),
        'candidate_archive_sha256':sha256(candidate_raw).hexdigest(),
        'candidate_files':hashes,'content_manifest_sha256':sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        'test_files':test_hashes,'archive_sha256':file_hash(archive),'reports':reports,'calls':len(calls),
        'image':IMAGE,'source_sha256':file_hash(__file__),'code_hashes':code_hashes,
        'runtime':runtime,'resources_closed':station.closed,'model_calls':0,
        'scope':'Prespecified 61-item jq development subset, native ARM adaptation; not an official ProgramBench score.',
        'isolation':'Read-only candidate copy; no original oracle, tests, expected answers or network in the candidate workstation. Only explicit CLI inputs transferred.',
        'execution_limits':{'seconds_per_invocation':10,'candidate_read_only':True,'files':256,'bytes':24_000_000}}
    result['source_unchanged'] = all(file_hash(repository/name)==digest for name,digest in code_hashes.items())
    result['evaluation_complete']=(result['source_unchanged'] and len(collected)==len(nodes) and status in (0,1) and not transport_errors
        and len([r for r in reports if r['phase']=='call'])==len(nodes)
        and all(r['outcome']=='passed' for r in reports if r['phase'] in ('setup','teardown'))
        and all(r['outcome'] in ('passed','failed') for r in reports if r['phase']=='call'))
    result.update(quality(reports, len(nodes), result['evaluation_complete']))
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


CORE_TESTS = (
    'test_basic.py::test_array_index_out_of_bounds',
    'test_smoke.py::test_array_map',
    'test_cli.py::test_parse_error_exit_code',
    'test_cli_gaps_extended.py::test_compact_sort_keys_combined',
)


def quality(reports, total, complete):
    calls={}
    for row in reports:
        if row['phase']!='call':continue
        path,rest=row['nodeid'].split('::',1)
        key=Path(path).name+'::'+rest
        if key in calls:raise ValueError('Duplicate scored test identity')
        calls[key]=row['outcome']
    core={name:calls.get(name)=='passed' for name in CORE_TESTS}
    passed=sum(value=='passed' for value in calls.values())
    return {'score_fraction':passed/total if total else None,
        'core_checks':core, 'quality_threshold':{'fraction':0.6,'all_core_checks_required':True},
        'threshold_reached':bool(complete and total==61 and passed*5>=total*3 and all(core.values())),
        'quality_scope':'Prespecified 60% development threshold plus basic indexing, array transformation, parse-error status and CLI flag behavior. Partial results retained; no official benchmark threshold is implied.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-archive',type=Path,required=True)
    parser.add_argument('--test-archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=evaluate(args.candidate_archive,args.test_archive,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('reports','test_files','candidate_files')}))
    return 0 if result['evaluation_complete'] else 1


if __name__=='__main__':raise SystemExit(main())
