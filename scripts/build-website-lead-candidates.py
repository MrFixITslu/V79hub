#!/usr/bin/env python3
"""Build pinned candidates and run new tests only. Never switch live services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

HUB = '2e5f872914bb85f98651ce00a4a90b1880e44076'
WEBSITE = '43de17780357e776c86a7f8898168a50fa5e2820'


def main():
    os.umask(0o077)
    root = Path(tempfile.mkdtemp(prefix='v79-lead-candidates-'))
    log = root / 'build.log'
    stage = 'inventory'

    def run(args, capture=False):
        with log.open('ab') as output:
            result = subprocess.run(args, stdout=subprocess.PIPE if capture else output,
                                    stderr=output, timeout=1200, check=True)
        return result.stdout.decode().strip() if capture else ''

    def live():
        items = json.loads(run(['docker','inspect','v79-hub','V79website'], True))
        return {item['Name']: {'id':item['Id'], 'image':item['Image']} for item in items}, items

    try:
        before, containers = live()
        website = next(c for c in containers if c['Name'] == '/V79website')
        website_repo = website['Config'].get('Labels', {}).get('com.docker.compose.project.working_dir','')
        if not website_repo or not Path(website_repo).is_dir():
            raise RuntimeError('WEBSITE_COMPOSE_WORKDIR_UNAVAILABLE')
        sources = [('hub', '/opt/v79/hub', HUB), ('website', website_repo, WEBSITE)]
        candidates = {}
        for name, repo, commit in sources:
            stage = name + '_source'
            run(['git','-C',repo,'rev-parse','--show-toplevel'], True)
            run(['git','-C',repo,'fetch','--no-tags','origin',commit])
            source = root / name
            run(['git','-C',repo,'worktree','add','--detach',str(source),commit])
            if run(['git','-C',str(source),'rev-parse','HEAD'],True) != commit:
                raise RuntimeError('SOURCE_PIN_MISMATCH')
            if run(['git','-C',str(source),'status','--porcelain'],True):
                raise RuntimeError('SOURCE_NOT_CLEAN')
            stage = name + '_build'
            tag = ('v79hub' if name == 'hub' else 'v79website') + ':lead-events-' + commit[:12]
            print(json.dumps({'stage':stage,'status':'RUNNING'}), flush=True)
            run(['docker','build','--label','org.opencontainers.image.revision='+commit,
                 '-t',tag,str(source)])
            image = run(['docker','image','inspect','--format','{{.Id}}',tag],True)
            stage = name + '_new_tests'
            command = ['docker','run','--rm','--network','none','--read-only',
                       '--tmpfs','/tmp:rw,nosuid,noexec,size=64m','--cap-drop','ALL',
                       '--security-opt','no-new-privileges','--entrypoint','node']
            if name == 'hub':
                command += [image,'--test','/app/tests/website-lead-events.test.mjs']
            else:
                for part in ['tests/hub-event-replay.test.ts','server/hub-event-replay.ts']:
                    command += ['--mount',f'type=bind,source={source / part},target=/focused/{part},readonly']
                command += [image,'--test','/focused/tests/hub-event-replay.test.ts']
            run(command)
            candidates[name] = {'commit':commit,'image':image,'tag':tag,'new_tests':'PASS'}
        stage = 'closeout'
        after, _ = live()
        if before != after:
            raise RuntimeError('LIVE_IDENTITIES_CHANGED_DURING_BUILD')
        receipt = {'result':'PASS_CANDIDATES_BUILT_ONLY','candidates':candidates,
                   'live_identities_unchanged':True,'deployed':False}
        (root / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({**receipt,'evidence_directory':str(root)},indent=2))
    except Exception as error:
        reason = str(error) if isinstance(error,RuntimeError) else type(error).__name__
        print(json.dumps({'result':'STOP','stage':stage,'reason':reason,
                          'evidence_directory':str(root),'deployed':False}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
