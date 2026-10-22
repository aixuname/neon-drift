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
FILES=('开始游戏.bat','game.py','combat.py','combat_render.py','flight_rewards.py')
EXCLUDED_PARTS={'.git','__pycache__','.pytest_cache','.venv','archive',
                'docs','examples','tests','__briefcase','__pyinstaller'}
EXCLUDED_SUFFIXES={'.pyc','.pyo','.pyi','.log','.lnk','.pem','.key'}
PLAYER_GUIDE='''# 流光穿梭

适用：Windows 10/11 64 位。完整解压后双击“开始游戏.bat”。
无需安装 Python、安装依赖、登录或联网。请保留整个游戏文件夹。

## 操作与玩法
- 鼠标、方向键或 WASD 移动；单击或空格释放两秒护盾。
- Esc 暂停，F11 全屏，M 静音。
- 普通局 30 秒、三条命，提供漫游、疾驰、极限三档难度。
- 躲开红紫色障碍和奶龙攻击，收集金色能量，为护盾充能。
- 满三条命撑过 30 秒，进入额外 15 秒隐藏关；最后五秒为旋转光刃。
- 结算可输入姓名，保存评级、成就和本地排行榜。

## 文件与维护
assets 是素材，runtime 是自带运行环境，四个 .py 文件是游戏程序，均不能删除。
data 和 temp 会自动创建，存档和日志只保存在自己的游戏文件夹内。
需要维护时，从 game.py 入手；规则在 combat.py，绘制在 combat_render.py，
评级与成就在 flight_rewards.py。所有路径应跟随当前目录，不要写死盘符。
仅修改运行代码即可，勿删除 runtime 中的 .pyd、.dll 或许可证。
遇到启动错误，可检查 data/error.log，并确认已完整解压、文件夹可写。
'''


def source_files():
    paths=[ROOT/name for name in FILES]
    paths.extend((ROOT/'assets'/'fonts'/name) for name in ('chinese.ttc','chinese-bold.ttc'))
    paths.extend((ROOT/'assets'/'sounds').glob('*.wav'))
    paths.extend((ROOT/'assets'/'mascot'/'combat'/f'{name}.png')
                 for name in ('brute','plain','trickster','gunner'))
    paths.extend(path for path in (ROOT/'runtime').rglob('*') if path.is_file())
    result=[]
    for path in paths:
        relative=path.relative_to(ROOT)
        if any(part.endswith('.dist-info') for part in relative.parts):
            continue
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
    extra={'agent.md':PLAYER_GUIDE.encode('utf-8'),
           'runtime/licenses/pygame-LGPL.txt':(ROOT/'runtime/libs/pygame/docs/generated/LGPL.txt').read_bytes()}
    checksums={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    checksums.update({name:hashlib.sha256(data).hexdigest() for name,data in extra.items()})
    manifest={'game':'流光穿梭','platform':'Windows 10/11 x64',
              'build_date':args.date,'files':checksums}
    temporary=target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sources:
            archive.write(path,'流光穿梭/'+path.relative_to(ROOT).as_posix())
        for name,data in extra.items():
            archive.writestr('流光穿梭/'+name,data)
    with zipfile.ZipFile(temporary) as archive:
        bad=archive.testzip()
        if bad:
            raise ValueError(f'ZIP checksum failed: {bad}')
    temporary.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n',encoding='utf-8')
    target.with_suffix('.zip.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'path':str(target),'files':len(checksums),
                      'size_mb':round(target.stat().st_size/1024**2,2),'sha256':digest},ensure_ascii=False))


if __name__=='__main__':
    main()
