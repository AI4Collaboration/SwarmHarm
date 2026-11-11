"""A controller-owned reader that never shares a participant's process lock."""
import json
import re
import secrets
import subprocess

from swarmform.publication_updates import ROOT, scan_publications


class PublicationObserver:
    def __init__(self, binding):
        volume, user, image = (binding[k] for k in ('volume', 'user', 'image'))
        if (not re.fullmatch(r'office-[0-9a-f]+', volume)
                or not re.fullmatch(r'\d+:\d+', user)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', image)):
            raise ValueError('Invalid registered publication observer binding')
        self.name = 'office-publication-' + secrets.token_hex(8)
        self.created = False
        try:
            subprocess.run(['docker', 'run', '-d', '--rm', '--pull=never', '--name', self.name,
                '--label', 'org.swarmharm.managed=true', '--network=none', '--read-only',
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=32',
                '--user', user, '--mount', f'type=volume,src={volume},dst={ROOT},readonly',
                image, 'python', '-I', '-c', 'import time; time.sleep(86400)'],
                check=True, capture_output=True, timeout=30)
            self.created = True
            row = json.loads(subprocess.check_output(['docker', 'inspect', self.name], timeout=15))[0]
            mounts = row['Mounts']
            if (len(mounts) != 1 or mounts[0]['Name'] != volume or mounts[0]['RW']
                    or mounts[0]['Destination'] != ROOT or row['Config']['User'] != user
                    or row['Image'] != image or row['HostConfig']['NetworkMode'] != 'none'
                    or row['HostConfig']['ReadonlyRootfs'] is not True
                    or row['HostConfig']['PidMode'] not in ('', 'private')):
                raise RuntimeError('Publication observer isolation differs from its policy')
            self.binding = {'container': self.name, 'volume': volume, 'user': user,
                'image': image, 'read_only': True, 'network': 'none',
                'participant_process_namespace': False, 'participant_lock': False}
        except BaseException:
            self.close()
            raise

    def scan(self):
        return scan_publications(self)

    def close(self):
        if self.created:
            subprocess.run(['docker', 'rm', '-f', self.name], check=True, capture_output=True, timeout=20)
            self.created = False
