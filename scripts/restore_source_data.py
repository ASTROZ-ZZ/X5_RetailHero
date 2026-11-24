#!/usr/bin/env python3
"""Verify archive parts and restore the six original CSVs without overwriting files."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from archive_source_data import JoinedParts, checksum

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data')
    args=parser.parse_args()
    folder=ROOT/'data/backup'
    manifest=json.loads((folder/'manifest.json').read_text())
    paths=[folder/row['file'] for row in manifest['parts']]
    for path,row in zip(paths,manifest['parts']):
        if not path.is_file() or path.stat().st_size!=row['bytes'] or checksum(path)!=row['sha256']:
            raise ValueError(f'Archive part failed verification: {path.name}')
    expected={row['file']:row for row in manifest['source_files']}
    args.output.mkdir(parents=True,exist_ok=True)
    for name in expected:
        if (args.output/name).exists():raise FileExistsError(f'Restore destination already exists: {name}')
    restored=set()
    with tarfile.open(fileobj=JoinedParts(paths),mode='r|gz') as archive:
        for member in archive:
            if not member.isfile() or member.name not in expected or Path(member.name).name!=member.name:
                raise ValueError('Unexpected archive member')
            target=args.output/member.name
            temp=target.with_name(target.name+'.restoring')
            digest=hashlib.sha256()
            try:
                with archive.extractfile(member) as source,temp.open('xb') as dest:
                    for block in iter(lambda:source.read(4*1024*1024),b''):
                        dest.write(block);digest.update(block)
                if temp.stat().st_size!=expected[member.name]['bytes'] or digest.hexdigest()!=expected[member.name]['sha256']:
                    raise ValueError(f'Restored file failed verification: {member.name}')
                temp.rename(target)
                restored.add(member.name)
                print('Restored and verified',member.name,flush=True)
            except BaseException:
                if temp.exists():temp.unlink()
                raise
    if restored!=set(expected):raise ValueError('Missing original data files')
    print('All six CSVs restored and verified.')

if __name__=='__main__':main()
