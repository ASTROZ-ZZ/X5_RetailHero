#!/usr/bin/env python3
"""Adjust body page breaks and cached contents-page numbers without restyling."""
import argparse
from pathlib import Path
import re
from zipfile import ZipFile
from lxml import etree

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def compact(source,output,chapter_pages=None):
    with ZipFile(source) as archive:
        root=etree.fromstring(archive.read('word/document.xml'))
        started=False
        removed=0
        for p in root.find('w:body',NS).findall('w:p',NS):
            if p.xpath('./w:bookmarkStart[@w:name="Chapter1"]',namespaces=NS):
                started=True
            if started:
                for item in p.xpath('./w:pPr/w:pageBreakBefore',namespaces=NS):
                    item.getparent().remove(item)
                    removed+=1
            elif chapter_pages:
                for instruction in p.xpath('.//w:instrText',namespaces=NS):
                    match=re.search(r'PAGEREF\s+Chapter(\d+)\b',instruction.text or '')
                    if match:
                        cached=instruction.getparent().find('w:t',NS)
                        if cached is None:
                            run=instruction.getparent().getnext()
                            while run is not None:
                                cached=run.find('w:t',NS)
                                if cached is not None:break
                                run=run.getnext()
                        assert cached is not None
                        cached.text=str(chapter_pages[int(match[1])-1])
        assert removed>0
        with ZipFile(output,'w') as dest:
            for item in archive.infolist():
                data=etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True) if item.filename=='word/document.xml' else archive.read(item.filename)
                dest.writestr(item,data)
        print(f'Removed {removed} forced body page breaks')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--chapter-pages',type=int,nargs=8)
    a=p.parse_args();compact(a.source,a.output,a.chapter_pages)
