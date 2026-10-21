"""Extract the four isolated atlas cells into centered transparent game frames."""
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'temp')
os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'
import pygame

def main():
    folder=ROOT/'assets'/'mascot'/'combat'
    atlas=pygame.image.load(str(folder/'atlas-v2.png'))
    cw,ch=atlas.get_width()//2,atlas.get_height()//2
    manifest={}
    for index,name in enumerate(('brute','plain','trickster','gunner')):
        col,row=index%2,index//2
        frame=atlas.subsurface((col*cw,row*ch,cw,ch))
        bounds=frame.get_bounding_rect(min_alpha=8)
        if bounds.left<10 or bounds.top<10 or bounds.right>cw-10 or bounds.bottom>ch-10:
            raise ValueError(f'{name} touches cell boundary: {bounds}')
        source=frame.subsurface(bounds)
        scale=min(360/bounds.width,360/bounds.height)
        size=(round(bounds.width*scale),round(bounds.height*scale))
        sprite=pygame.transform.smoothscale(source,size)
        canvas=pygame.Surface((400,400),pygame.SRCALPHA)
        canvas.blit(sprite,((400-size[0])//2,(400-size[1])//2))
        pygame.image.save(canvas,str(folder/(name+'.png')))
        manifest[name]={'cell':[col,row],'bounds':list(bounds),'size':[400,400]}
        print(name,bounds)
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
