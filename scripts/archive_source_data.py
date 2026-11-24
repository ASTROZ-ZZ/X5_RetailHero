#!/usr/bin/env python3
"""Create and verify a multipart gzip archive of every original CSV."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
DEST=DATA/'backup'
LIMIT=90*1024*1024

class Parts:
    def __init__(self):
        self.file=None
        self.size=0
        self.items=[]
    def write(self,data):
        total=len(data)
        while data:
            if self.file is None or self.size==LIMIT:
                if self.file:self.file.close()
                path=DEST/f'x5_source_data.tar.gz.{len(self.items)+1:03d}.part'
                self.file=path.open('wb');self.items.append(path);self.size=0
            amount=min(len(data),LIMIT-self.size)
            self.file.write(data[:amount]);self.size+=amount;data=data[amount:]
        return total
    def close(self):
        if self.file:self.file.close()

class HashingReader:
    def __init__(self,file):self.file=file;self.hash=hashlib.sha256()
    def read(self,size=-1):
        block=self.file.read(size);self.hash.update(block);return block

class JoinedParts:
    def __init__(self,paths):self.paths=iter(paths);self.file=None
    def read(self,size=-1):
        chunks=[];left=size
        while left!=0:
            if self.file is None:
                try:self.file=next(self.paths).open('rb')
                except StopIteration:break
            block=self.file.read(left)
            if not block:self.file.close();self.file=None;continue
            chunks.append(block)
            if size>=0:left-=len(block)
        return b''.join(chunks)

def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    DEST.mkdir(exist_ok=True)
    assert not list(DEST.glob('*.part')),'Archive already exists. Verify before recreating.'
    sink=Parts();sources=[]
    with tarfile.open(fileobj=sink,mode='w|gz',compresslevel=6,format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(DATA.glob('*.csv')):
            with path.open('rb') as f:
                reader=HashingReader(f)
                tar.addfile(tar.gettarinfo(str(path),arcname=path.name),reader)
            sources.append({'file':path.name,'bytes':path.stat().st_size,'sha256':reader.hash.hexdigest()})
            print('Archived',path.name,flush=True)
    sink.close()
    expected={x['file']:x for x in sources};seen=[]
    with tarfile.open(fileobj=JoinedParts(sink.items),mode='r|gz') as tar:
        for member in tar:
            file=tar.extractfile(member)
            h=hashlib.sha256()
            for chunk in iter(lambda:file.read(4*1024*1024),b''):h.update(chunk)
            assert member.size==expected[member.name]['bytes'] and h.hexdigest()==expected[member.name]['sha256']
            seen.append(member.name)
    assert set(seen)==set(expected)
    parts=[{'file':x.name,'bytes':x.stat().st_size,'sha256':checksum(x)} for x in sink.items]
    manifest={'archive_format':'tar.gz split into ordered binary parts','part_limit_bytes':LIMIT,
              'source_files':sources,'parts':parts,'round_trip_sha256_verified':True}
    (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('VERIFIED',len(sources),'source files in',len(parts),'parts;',sum(x['bytes'] for x in parts),'bytes',flush=True)

if __name__=='__main__':main()
