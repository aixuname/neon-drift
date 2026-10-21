"""Real-time combat artwork, six obstacle styles and projectile rendering."""
from functools import lru_cache
import math
from pathlib import Path
import pygame
from combat import HIT_Z

ROOT=Path(__file__).resolve().parent
RED=(255,92,124)
GOLD=(255,200,109)
WHITE=(234,245,255)
COLORS={'blocks':(255,145,93),'moving':(255,93,139),'laser':(255,119,84),
        'grid':(179,129,255),'ring':(255,86,149),'mines':(248,113,226)}


def tint(color,t):
    return tuple(max(0,min(255,round(c*t))) for c in color)


@lru_cache(maxsize=4)
def source(variant):
    return pygame.image.load(str(ROOT/'assets'/'mascot'/'combat'/(variant+'.png'))).convert_alpha()


@lru_cache(maxsize=112)
def enemy_sprite(variant,size,flip=False,angle=0):
    image=pygame.transform.smoothscale(source(variant),(size,size))
    if flip:
        image=pygame.transform.flip(image,True,False)
    if angle:
        image=pygame.transform.rotozoom(image,angle,1)
    return image


class CombatEffects:
    def block(self,block,z,color=RED):
        x,y,w,h=block.x,block.y,block.width,block.height
        if block.shape=='mine':
            px,py=self.project(x,y,z)
            rx=w*.5*1900/(z+1)
            ry=w*.5*1140/(z+1)
            # Solid spherical core, radial fins and a tilted orbital band.
            pygame.draw.ellipse(self.surface,tint(color,.16),(px-rx*.74,py-ry*.74,rx*1.48,ry*1.48))
            self.ring((px,py),max(1,rx*.74),max(1,ry*.74),color,2)
            points=[]
            for i in range(8):
                angle=i*math.tau/8+self.t*.8
                a=(px+math.cos(angle)*rx*.62,py+math.sin(angle)*ry*.62)
                b=(px+math.cos(angle)*rx,py+math.sin(angle)*ry)
                self.line(color,[a,b],2,power=.55)
            for i in range(33):
                a=i*math.tau/32
                points.append((px+math.cos(a)*rx*.94,py+math.sin(a)*ry*.30+math.cos(a)*ry*.2))
            self.line(tint(WHITE,.55),points,1,power=.25)
            self.ring((px,py),max(1,rx*.30),max(1,ry*.30),GOLD,2)
            pygame.draw.ellipse(self.surface,WHITE,(px-rx*.10,py-ry*.10,max(1,rx*.20),max(1,ry*.20)))
            return
        if block.shape in ('laser','grid'):
            self.energy_beam(block,z,color)
            return
        # Faceted amber crystals: the outline is also used by collision physics.
        front=[self.project(a,b,z) for a,b in block.outline()]
        back=[self.project(a,b,z+.65) for a,b in block.outline()]
        peak=self.project(x-w*.10,y-h*.08,z-.18)
        self.line(tint(color,.35),back,1,True,.18)
        shades=(.20,.42,.28,.12,.09,.14)
        for i in range(6):
            j=(i+1)%6
            pygame.draw.polygon(self.surface,tint(color,shades[i]),[front[i],front[j],peak])
            if i%2==0:
                self.line(tint(color,.52),[front[i],peak],1,power=.20)
                self.line(tint(color,.36),[front[i],back[i]],1,power=.15)
        self.line(color,front,2,True,.42)
        self.line(tint(WHITE,.80),front[:3],2,power=.32)

    def energy_beam(self,block,z,color):
        x,y,w,h=block.x,block.y,block.width,block.height
        ca,sa=math.cos(block.angle),math.sin(block.angle)
        vertical=h>w
        length=max(w,h)
        radius=min(w,h)/2
        half=length/2-radius
        def point(along,across,depth=z):
            dx,dy=(across,along) if vertical else (along,across)
            return self.project(x+dx*ca-dy*sa,y+dx*sa+dy*ca,depth)
        silhouette=[]
        for center,start in ((half,-math.pi/2),(-half,math.pi/2)):
            for i in range(9):
                a=start+i*math.pi/8
                silhouette.append(point(center+math.cos(a)*radius,math.sin(a)*radius))
        pygame.draw.polygon(self.surface,tint(color,.22),silhouette)
        self.line(tint(color,.65),silhouette,1,True,.24)
        # A continuous luminous core replaces rectangular wire frames.
        core=[]
        for i in range(25):
            along=-half+2*half*i/24
            oscillation=math.sin(i*.85+self.t*8)*radius*.32 if block.shape=='grid' else 0
            core.append(point(along,oscillation,z-.025))
        self.line(color,core,5 if block.shape=='laser' else 3,power=.55)
        self.line(WHITE,core,2 if block.shape=='laser' else 1,power=.60)
        for along in (-half,half):
            center=point(along,0)
            rx=max(1,radius*1900/(z+1))
            ry=max(1,radius*1140/(z+1))
            self.ring(center,rx,ry,color,2)

    def energy_gate(self,wave,z,color,opening):
        x,y,w,h=opening
        rx,ry=w/2,h/2
        count=48
        inner=[]
        outer=[]
        back=[]
        for i in range(count):
            angle=i*math.tau/count
            a,b=math.cos(angle),math.sin(angle)
            inner.append(self.project(x+a*rx,y+b*ry,z))
            outer.append(self.project(a*1.20,b*1.20,z))
            back.append(self.project(x+a*rx,y+b*ry,z+.55))
        # Curved, shaded iris sectors make the dangerous outer area visible.
        for sector in range(8):
            ids=[(sector*6+i)%count for i in range(7)]
            shape=[outer[i] for i in ids]+[inner[i] for i in reversed(ids)]
            pygame.draw.polygon(self.surface,tint(color,.055 if sector%2 else .095),shape)
            a=ids[0]
            self.line(tint(color,.24),[inner[a],outer[a]],1,power=.12)
        self.line(tint(color,.35),back,2,True,.15)
        self.line(tint(color,.26),outer,1,True,.15)
        self.line(color,inner,3,True,.58)
        # Orbiting arcs and metal rim facets add depth without obscuring the gap.
        for sector in range(8):
            indices=[(sector*6+i)%count for i in range(4)]
            rim=[]
            for i in indices:
                a=i*math.tau/count
                rim.append(self.project(x+math.cos(a)*(rx+.045),y+math.sin(a)*(ry+.045),z))
            facet=[inner[i] for i in indices]+list(reversed(rim))
            pygame.draw.polygon(self.surface,tint(color,.40 if sector%2 else .22),facet)
            self.line(tint(color,.82),rim,2,power=.30)
        phase=int(wave.age*7)%count
        for i in range(0,count,16):
            arc=[inner[(i+phase+j)%count] for j in range(5)]
            self.line(WHITE,arc,2,power=.50)

    def draw_wave(self,wave):
        z=wave.z
        if z<1.0 or z>74:
            return
        fade=min(1.,(74-z)/24)
        if wave.checked:
            fade*=.20
        color=tint(COLORS.get(wave.kind,RED),fade)
        opening=wave.opening_at()
        if opening is not None and wave.kind in ('ring','moving'):
            self.energy_gate(wave,z,color,opening)
        elif opening is not None:
            from combat import Block
            x,y,w,h=opening
            left,right,top,bottom=x-w/2,x+w/2,y-h/2,y+h/2
            for block in (Block((-1+left)/2,0,left+1,2),Block((right+1)/2,0,1-right,2),
                          Block(x,(-1+top)/2,w,top+1),Block(x,(bottom+1)/2,w,1-bottom)):
                if block.width>.01 and block.height>.01:
                    self.block(block,z,color)
        else:
            for block in wave.geometry():
                self.block(block,z,color)
        if not wave.checked:
            for x,y in wave.orbs:
                px,py=self.project(x,y,z-.12)
                radius=max(2,105/(z+1))*(1.15 if wave.source!='normal' else 1.)
                points=[(px,py-radius),(px+radius*.67,py),(px,py+radius),(px-radius*.67,py)]
                pygame.draw.polygon(self.surface,tint(GOLD,.24*fade),points)
                self.line(tint(GOLD,fade),points,2,True,.65)

    def draw_combat(self,game):
        for encounter in game.encounters:
            if encounter.kind=='rush':
                points=[self.project(*wave.orbs[0],wave.z)
                        for wave in sorted(game.waves,key=lambda w:w.z,reverse=True)
                        if wave.source=='rush' and not wave.checked and wave.orbs and 1<wave.z<70]
                if len(points)>1:
                    self.line(tint(GOLD,.35),points,1,power=.6)
            elif encounter.kind=='meteor':
                for meteor in encounter.meteors:
                    until=meteor.impact-game.elapsed
                    if until>1. or until<-.35:
                        continue
                    tx,ty=self.project(meteor.x,meteor.y,HIT_Z)
                    if until>=0:
                        z=HIT_Z+until*28
                        x=meteor.x+meteor.side*.85*until
                        y=meteor.y-.75*until
                        head=self.project(x,y,z)
                        tail=self.project(x+meteor.side*.40,y-.45,z+10)
                        self.line(tint(RED,.8),[tail,head],8,power=.85)
                        self.line(GOLD,[tail,head],3,power=.7)
                        radius=max(3,88/(z+1))
                        pygame.draw.circle(self.surface,GOLD,head,radius)
                        pygame.draw.circle(self.surface,WHITE,head,radius*.45)
                    else:
                        fade=max(0,1+until/.35)
                        radius=22-until*220
                        self.ring((tx,ty),radius,radius*.65,tint(RED,fade),2)
        for bullet in game.bullets:
            px,py=self.project(bullet.x,bullet.y,HIT_Z)
            tail=self.project(bullet.x-bullet.vx*.045,bullet.y-bullet.vy*.045,HIT_Z)
            color=(255,109,190) if bullet.color=='pink' else (255,170,92)
            self.line(color,[tail,(px,py)],3,power=.50)
            rx=max(3,bullet.radius*475)
            ry=max(2,bullet.radius*285)
            pygame.draw.ellipse(self.surface,color,(px-rx,py-ry,rx*2,ry*2))
            pygame.draw.ellipse(self.surface,WHITE,(px-rx*.37,py-ry*.37,rx*.74,ry*.74))
        for actor in sorted(game.actors,key=lambda a:a.z,reverse=True):
            if actor.z<1.1:
                continue
            px,py=self.project(actor.x,actor.y,actor.z)
            size=round(max(40,min(512,actor.size*1900/(actor.z+1)))/8)*8
            if not (-size<px<1280+size and -size<py<840+size):
                continue
            flip=actor.side<0 and actor.motion in ('cross','trickster')
            angle=round(math.sin(actor.age*8)*3) if actor.motion!='gunner' else 0
            if actor.motion=='trickster':
                angle=round(math.sin(actor.age*9)*6)
            image=enemy_sprite(actor.variant,size,flip,angle)
            if actor.motion=='charge' and actor.checked:
                image=image.copy()
                image.set_alpha(round(255*max(0,min(1,(actor.z-1.1)/1.8))))
            self.mascot_overlays.append((image,image.get_rect(center=(px,py))))
