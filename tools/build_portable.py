"""Create a complete Windows portable ZIP without local player data."""
import argparse
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'temp')
FILES=('开始游戏.bat','先看我.txt','agent.md','AGENTS.md','README.md',
       'game.py','combat.py','combat_render.py','flight_rewards.py','requirements.txt')
EXCLUDED_PARTS={'.git','__pycache__','.pytest_cache','.venv','archive'}
EXCLUDED_SUFFIXES={'.pyc','.pyo','.log','.lnk','.pem','.key'}


def source_files():
    paths=[ROOT/name for name in FILES]
    for name in ('assets','runtime'):
        paths.extend(path for path in (ROOT/name).rglob('*') if path.is_file())
    paths.extend((ROOT/'tools').glob('*.py'))
    result=[]
    for path in paths:
        relative=path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.startswith('.env'):
            continue
        if not path.is_file():
            raise FileNotFoundError(path)
        result.append(path)
    return sorted(set(result),key=lambda p:p.relative_to(ROOT).as_posix())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',default=datetime.now().strftime('%Y%m%d'))
    parser.add_argument('--label',default='',help='Optional version suffix such as v2')
    args=parser.parse_args()
    if len(args.date)!=8 or not args.date.isdigit():
        parser.error('--date must use YYYYMMDD')
    if args.label and not re.fullmatch(r'[A-Za-z0-9_-]{1,24}',args.label):
        parser.error('--label must contain 1-24 letters, digits, underscores or hyphens')
    suffix='_'+args.label if args.label else ''
    target=ROOT/'dist'/f'流光穿梭_便携版_{args.date}{suffix}.zip'
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        raise FileExistsError(f'Package already exists: {target}')
    sources=source_files()
    checksums={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sources}
    manifest={'game':'流光穿梭','platform':'Windows 10/11 x64',
              'build_date':args.date,'files':checksums}
    temporary=target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sources:
            archive.write(path,'流光穿梭/'+path.relative_to(ROOT).as_posix())
        archive.writestr('流光穿梭/打包清单.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(temporary) as archive:
        bad=archive.testzip()
        if bad:
            raise ValueError(f'ZIP checksum failed: {bad}')
    temporary.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n',encoding='utf-8')
    print(json.dumps({'path':str(target),'files':len(sources)+1,
                      'size_mb':round(target.stat().st_size/1024**2,2),'sha256':digest},ensure_ascii=False))


if __name__=='__main__':
    main()
