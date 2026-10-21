"""流光穿梭 / NEON DRIFT — offline Python desktop arcade game.

Bundled launch: runtime/python/python.exe -B game.py
All saves, errors and temporary files stay inside this project.
"""
from __future__ import annotations
import argparse
from datetime import datetime
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import random
import sys
import uuid

ROOT = Path(__file__).resolve().parent
for name in ('data', 'temp', 'previews'):
    (ROOT / name).mkdir(exist_ok=True)
os.environ['TEMP'] = os.environ['TMP'] = str(ROOT / 'temp')
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['SDL_IME_SHOW_UI'] = '1'
sys.dont_write_bytecode = True
import pygame
from combat_render import CombatEffects, enemy_sprite
from combat import (Actor, Block, Bullet, Encounter, HIT_Z, MAX_LIVES, Meteor, MODES, PATTERNS,
                    HIDDEN_SECONDS, ROUND_SECONDS, Round, SHIP_RADIUS, SPECIALS, Wave)

W, H = 1280, 840
SHIP_DRAW_SCALE=.66
WHITE = (234, 245, 255)
MUTED = (127, 151, 178)
BG = (5, 9, 22)
CYAN = (87, 239, 231)
GOLD = (255, 200, 109)
RED = (255, 92, 124)
PALETTES = [((79, 229, 241), (53, 106, 205), '星海启航'),
            ((177, 122, 255), (73, 105, 214), '极光回廊'),
            ((255, 175, 106), (181, 84, 202), '日冕冲刺'),
            ((255, 74, 151), (113, 79, 255), '超频裂隙')]


def blend(a, b, t):
    t = max(0., min(1., t))
    return tuple(round(x + (y-x)*t) for x, y in zip(a, b))


def tint(color, t):
    return tuple(max(0, min(255, round(c*t))) for c in color)


def rounded(surface, color, rect, radius=16, width=0):
    pygame.draw.rect(surface, color, pygame.Rect(rect), width, border_radius=radius)


@lru_cache(maxsize=80)
def font(size, bold=False):
    filename = 'chinese-bold.ttc' if bold else 'chinese.ttc'
    return pygame.font.Font(str(ROOT/'assets'/'fonts'/filename), size)


@lru_cache(maxsize=1800)
def rendered(value, size, color, bold=False):
    return font(size, bold).render(value, True, color)


def text(surface, value, pos, size=20, color=WHITE, bold=False, center=False):
    image = rendered(str(value), size, tuple(color), bold)
    rect = image.get_rect(center=pos) if center else image.get_rect(topleft=pos)
    surface.blit(image, rect)
    return rect


def fitted(surface, value, pos, width, size=20, color=WHITE, bold=False):
    while size > 12 and font(size, bold).size(value)[0] > width:
        size -= 1
    return text(surface, value, pos, size, color, bold)






class Storage:
    def __init__(self, folder=None):
        self.folder = Path(folder or ROOT/'data')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.records = self.read('scores.json', [])
        if not isinstance(self.records, list):
            self.records = []
        self.records = [r for r in self.records if isinstance(r, dict)
                        and r.get('mode') in MODES and isinstance(r.get('score'), int)
                        and isinstance(r.get('name'), str) and isinstance(r.get('date'), str)]
        self.settings = self.read('settings.json', {})
        if not isinstance(self.settings, dict):
            self.settings = {}

    def read(self, name, default):
        path = self.folder/name
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            if path.exists():
                try:
                    backup = self.folder/(path.stem+'-backup-'+uuid.uuid4().hex[:8]+'.json')
                    backup.write_bytes(path.read_bytes())
                except OSError:
                    pass
            return default

    def write(self, name, value):
        path = self.folder/name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)

    def save_settings(self):
        self.write('settings.json', self.settings)

    def top(self, mode, limit=10):
        return sorted([r for r in self.records if r['mode']==mode],
                      key=lambda r: (-r['score'], -r.get('orbs', 0), r['date']))[:limit]

    def add(self, name, game):
        record = {'id': uuid.uuid4().hex, 'name': name.strip()[:12], 'mode': game.mode,
                  'score': game.score, 'orbs': game.orbs, 'dodges': game.dodges,
                  'seconds': round(game.elapsed, 2), 'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        record['surprises']=len(game.special_history)
        record['hidden_unlocked']=game.hidden_unlocked
        record['hidden_completed']=game.hidden_completed
        self.write('scores.json', self.records+[record])
        self.records.append(record)
        self.settings['last_name'] = record['name']
        try:
            self.save_settings()
        except OSError:
            pass
        return record


class Audio:
    def __init__(self, muted=False):
        self.muted = muted
        self.enabled = bool(pygame.mixer.get_init())
        self.sounds = {}
        if not self.enabled:
            return
        for name in ('click', 'collect', 'hit', 'shield', 'pass', 'finish', 'tick', 'event', 'warning','shot'):
            path = ROOT/'assets'/'sounds'/(name+'.wav')
            if path.exists():
                self.sounds[name] = pygame.mixer.Sound(str(path))
        music = ROOT/'assets'/'sounds'/'neon_loop.wav'
        if music.exists():
            pygame.mixer.music.load(str(music))
            pygame.mixer.music.play(-1)
        self.apply()

    def apply(self):
        if self.enabled:
            pygame.mixer.music.set_volume(0 if self.muted else .28)
            for name, sound in self.sounds.items():
                sound.set_volume(0 if self.muted else (.13 if name=='shot' else (.25 if name in ('hit', 'pass') else .42)))

    def play(self, name):
        if self.enabled and not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle(self):
        self.muted = not self.muted
        self.apply()

    def pause(self, paused):
        if self.enabled:
            if paused:
                pygame.mixer.music.pause()
            else:
                pygame.mixer.music.unpause()




class Scene(CombatEffects):
    def __init__(self):
        self.glow = pygame.Surface((W//2,H//2))
        self.star_rng = random.Random(73)
        self.stars = [(self.star_rng.uniform(1.1,2.9),self.star_rng.uniform(0,math.tau),
                       self.star_rng.uniform(0,75),self.star_rng.uniform(.4,1.1)) for _ in range(180)]
        self.backgrounds = [self.background(p[0],p[1]) for p in PALETTES]
        self.surface = None
        self.center = (640,430)
        self.accent = CYAN
        self.secondary = (81,100,200)
        self.t = self.distance = 0.
        self.mascot_overlays=[]

    @staticmethod
    def background(accent, secondary):
        small = pygame.Surface((320,210))
        for y in range(210):
            for x in range(320):
                r = math.hypot((x-160)/180,(y-106)/124)
                halo = max(0.,1-r)*.095
                floor = max(0.,(y-110)/100)*.05
                small.set_at((x,y),blend(BG,accent,halo+floor))
        return pygame.transform.smoothscale(small,(W,H))

    def project(self,x,y,z):
        z = max(.5,z)
        bend = math.sin(self.t*.27+z*.049)-math.sin(self.t*.27+HIT_Z*.049)
        cx = self.center[0]+bend*58
        cy = self.center[1]+(math.cos(self.t*.19+z*.038)-math.cos(self.t*.19+HIT_Z*.038))*32
        return (cx+x*1900/(z+1),cy+y*1140/(z+1))

    def line(self,color,points,width=1,closed=False,power=.36):
        if len(points)<2:
            return
        if width > 1:
            pygame.draw.lines(self.surface,color,closed,points,width)
        pygame.draw.aalines(self.surface,color,closed,points)
        scaled=[(x/2,y/2) for x,y in points]
        pygame.draw.lines(self.glow,tint(color,power),closed,scaled,max(2,width+2))



    def ship(self,x,y,shield=False,blink=False,bank=0,gold=False):
        if blink:
            return
        px,py=self.project(x,y,HIT_Z)
        def point(dx,dy):
            return (px+dx*SHIP_DRAW_SCALE,py+dy*SHIP_DRAW_SCALE)
        # Layered swept wings, silver hull and twin ion engines.
        wobble=math.sin(self.t*17)*2
        pts=[point(0,-25),point(12,-1),point(36,17+bank),point(11,12),
             point(0,23),point(-11,12),point(-36,17-bank),point(-12,-1)]
        pygame.draw.polygon(self.surface,(23,43,68),pts)
        self.line(self.accent,pts,2,True,.55)
        pygame.draw.polygon(self.surface,(174,210,225),[point(0,-25),point(8,7),point(0,15),point(-8,7)])
        self.line(WHITE,[point(0,-25),point(0,8)],2,power=.3)
        engine_color=GOLD if gold else self.accent
        for dx in (-14,14):
            length=64 if gold else 40
            engine=[point(dx-4,13),point(dx+4,13),point(dx,length+wobble)]
            pygame.draw.polygon(self.surface,tint(engine_color,.65),engine)
            self.line(engine_color,[point(dx,15),point(dx,length*.8+wobble)],2,power=.85)
        if shield:
            ring=[point(math.cos(i*math.tau/48)*54,math.sin(i*math.tau/48)*44) for i in range(48)]
            self.line(self.accent,ring,2,True,.65)
            self.line(tint(WHITE,.8),ring[6:16],3,power=.8)

    def ring(self,center,rx,ry,color,width=2):
        x,y=center
        points=[(x+math.cos(i*math.tau/48)*rx,y+math.sin(i*math.tau/48)*ry) for i in range(48)]
        self.line(color,points,width,True,.48)


    def draw(self,surface,game,t,menu=False,particles=()):
        self.surface=surface
        self.mascot_overlays=[]
        self.t=t
        self.distance=game.distance if not menu else t*13
        self.center=(892,402) if menu else (640,430)
        phase=game.phase if not menu else int(t/12)%3
        phase_t=(game.elapsed%10)/1.2 if not menu else (t%12)/1.2
        if game.hidden_unlocked and not menu:
            phase_t=(game.elapsed-ROUND_SECONDS)/1.2
        prev=max(0,phase-1)
        if menu:
            prev=(phase-1)%3
        self.accent=blend(PALETTES[prev][0],PALETTES[phase][0],phase_t)
        self.secondary=blend(PALETTES[prev][1],PALETTES[phase][1],phase_t)
        surface.blit(self.backgrounds[phase],(0,0))
        self.glow.fill((0,0,0))
        # Faceted tunnel walls provide depth beneath the luminous guide rails.
        for index in range(27,0,-1):
            near=index*3-self.distance%3
            if near<.8:
                continue
            far=near+3
            for segment in range(12):
                a=segment*math.tau/12
                b=(segment+1)*math.tau/12
                points=[self.project(math.cos(a),math.sin(a),near),
                        self.project(math.cos(b),math.sin(b),near),
                        self.project(math.cos(b),math.sin(b),far),
                        self.project(math.cos(a),math.sin(a),far)]
                strength=(.035 if segment%2 else .055)*min(1,18/(near+2))
                pygame.draw.polygon(surface,blend(BG,self.secondary,strength),points)
        for radius,angle,z0,power in self.stars:
            z=(z0-self.distance)%75+1
            x,y=radius*math.cos(angle),radius*math.sin(angle)
            a=self.project(x,y,z)
            b=self.project(x,y,z+(.45 if menu else .85))
            if -100<a[0]<W+100 and -100<a[1]<H+100:
                brightness=min(1.,14/(z+2))*power
                self.line(tint(self.accent,brightness),[a,b],1,power=.25)
        # Travel is visible through receding polygon rings and long light rails.
        segments=12
        for index in range(26,0,-1):
            z=index*3.0-self.distance%3.0
            if z<.8:
                continue
            fade=min(1.,18/(z+2))*.68
            points=[self.project(math.cos(i*math.tau/segments),math.sin(i*math.tau/segments),z) for i in range(segments)]
            self.line(tint(self.accent,fade),points,2 if index%4==0 else 1,True,.28)
            if index%4==0:
                for i in (1,4,7,10):
                    self.line(tint(WHITE,fade*.7),[points[i],points[(i+1)%segments]],2,power=.45)
        for i in range(segments):
            angle=i*math.tau/segments
            points=[self.project(math.cos(angle),math.sin(angle),z) for z in (1.3,3,6,12,24,48,80)]
            self.line(tint(self.secondary,.36),points,1,power=.30)
        if menu:
            demo=[Wave(17,[Block(-.42,-.3)],orbs=[(.35,.17)]),
                  Wave(31,[Block(.52,.24)],orbs=[(-.30,-.05)]),
                  Wave(9,orbs=[(-.08,-.10)])]
            for wave in sorted(demo,key=lambda w:w.z,reverse=True):
                self.draw_wave(wave)
            self.ship(.18+math.sin(t*.6)*.08,.26+math.sin(t*.9)*.07,bank=math.sin(t)*3)
        else:
            for wave in sorted(game.waves,key=lambda w:w.z,reverse=True):
                self.draw_wave(wave)
            self.draw_combat(game)
            for px,py,life,color,vx,vy in particles:
                if life>0:
                    self.line(tint(color,min(1,life*3)),[(px,py),(px-vx*.03,py-vy*.03)],2,power=.65)
            self.ship(game.x,game.y,game.shield>0,
                      game.invulnerable>0 and int(t*15)%2==0,
                      bank=max(-6,min(6,(game.target[0]-game.x)*15)),gold=game.gold_trail>0)
        glow=pygame.transform.smoothscale(self.glow,(W,H))
        surface.blit(glow,(0,0),special_flags=pygame.BLEND_RGB_ADD)
        # Compose the textured character after bloom so the tunnel's glow
        # cannot shine through its face, glasses and opaque fur.
        for image,position in self.mascot_overlays:
            surface.blit(image,position)
        if self.mascot_overlays and not menu:
            self.ship(game.x,game.y,game.shield>0,
                      game.invulnerable>0 and int(t*15)%2==0,
                      bank=max(-6,min(6,(game.target[0]-game.x)*15)),gold=game.gold_trail>0)
        # A quiet edge treatment keeps the center bright and the UI readable.
        pygame.draw.line(surface,(22,40,60),(28,114),(W-28,114),1)


class App:
    def __init__(self,storage=None):
        if not pygame.font.get_init():
            font.cache_clear()
            rendered.cache_clear()
        pygame.mixer.pre_init(22050,-16,2,512)
        pygame.init()
        self.screen=pygame.display.set_mode((W,H),pygame.RESIZABLE)
        pygame.display.set_caption('流光穿梭 · NEON DRIFT')
        icon=pygame.Surface((64,64),pygame.SRCALPHA)
        pygame.draw.polygon(icon,CYAN,[(32,5),(58,53),(32,42),(6,53)])
        pygame.display.set_icon(icon)
        self.canvas=pygame.Surface((W,H))
        self.clock=pygame.time.Clock()
        self.storage=storage or Storage()
        self.mode=self.storage.settings.get('mode','normal')
        if self.mode not in MODES:
            self.mode='normal'
        self.control=self.storage.settings.get('control','mouse')
        if self.control not in ('mouse','keyboard'):
            self.control='mouse'
        self.audio=Audio(bool(self.storage.settings.get('muted',False)))
        self.game=Round(self.mode)
        self.scene=Scene()
        self.state='menu'
        self.running=True
        self.t=self.scene_time=0.
        self.mouse=(-100,-100)
        self.buttons=[]
        self.countdown=3.
        self.last_tick=31
        self.particles=[]
        self.messages=[]
        self.shake=self.flash=0.
        self.toast=''
        self.toast_left=0.
        self.name=str(self.storage.settings.get('last_name',''))[:12]
        self.composition=''
        self.ime_guard=0.
        self.saved=False
        self.saved_record=None
        self.fullscreen=False
        self.window_size=(W,H)

    def save_settings(self):
        self.storage.settings.update(mode=self.mode,control=self.control,muted=self.audio.muted)
        try:
            self.storage.save_settings()
        except OSError:
            self.say('设置暂时无法保存')

    def say(self,message):
        self.toast,self.toast_left=message,2.8

    def start(self):
        self.game=Round(self.mode)
        self.state='countdown'
        self.countdown=3.
        self.saved=False
        self.saved_record=None
        self.last_tick=31
        self.particles.clear()
        self.messages.clear()
        self.shake=self.flash=0.
        self.scene_time=0.
        self.composition=''
        self.audio.pause(False)
        self.audio.play('tick')
        pygame.key.stop_text_input()
        self.save_settings()

    def finish(self):
        self.state='result'
        self.audio.play('finish')
        pygame.key.start_text_input()
        self.ime_rect()

    def pause(self):
        if self.state in ('playing','countdown'):
            self.pause_from=self.state
            self.state='paused'
            self.audio.pause(True)

    def resume(self):
        self.state=getattr(self,'pause_from','playing')
        self.audio.pause(False)

    def end_early(self):
        self.game.ended,self.game.reason=True,'本次航行结束'
        self.audio.pause(False)
        self.finish()

    def menu(self):
        self.state='menu'
        self.audio.pause(False)
        pygame.key.stop_text_input()

    def leaderboard(self):
        self.board_from=self.state
        self.state='leaderboard'
        pygame.key.stop_text_input()

    def submit(self):
        if self.saved or self.composition:
            return
        if not self.name.strip():
            self.say('输入你的名字，留下这次航行记录')
            return
        try:
            self.saved_record=self.storage.add(self.name,self.game)
            self.saved=True
            self.audio.play('collect')
            pygame.key.stop_text_input()
            self.say('成绩已保存')
        except OSError:
            self.say('无法保存，请检查项目目录的空间和权限')

    def set_mode(self,mode):
        self.mode=mode

    def set_control(self,control):
        self.control=control

    def mute(self):
        self.audio.toggle()
        self.save_settings()

    def pos(self,pos):
        sw,sh=self.screen.get_size()
        scale=min(sw/W,sh/H)
        return ((pos[0]-(sw-W*scale)/2)/scale,(pos[1]-(sh-H*scale)/2)/scale)

    def ime_rect(self):
        sw,sh=self.screen.get_size()
        scale=min(sw/W,sh/H)
        ox,oy=(sw-W*scale)/2,(sh-H*scale)/2
        pygame.key.set_text_input_rect(pygame.Rect(int(ox+389*scale),int(oy+477*scale),int(502*scale),int(56*scale)))

    def handle(self,event):
        if event.type==pygame.QUIT:
            self.running=False
        elif event.type==pygame.WINDOWFOCUSLOST:
            self.pause()
        elif event.type==pygame.VIDEORESIZE:
            self.ime_rect()
        elif event.type==pygame.MOUSEMOTION:
            self.mouse=self.pos(event.pos)
            if self.state=='playing' and self.control=='mouse':
                self.game.target=((self.mouse[0]-640)/475,(self.mouse[1]-430)/285)
        elif event.type==pygame.TEXTEDITING and self.state=='result' and not self.saved:
            self.composition=event.text
        elif event.type==pygame.TEXTINPUT and self.state=='result' and not self.saved:
            if self.composition:
                self.ime_guard=self.t+.2
            self.name=(self.name+''.join(c for c in event.text if c.isprintable()))[:12]
            self.composition=''
        elif event.type==pygame.KEYDOWN:
            if event.key==pygame.K_F11:
                self.fullscreen=not self.fullscreen
                if self.fullscreen:
                    self.window_size=self.screen.get_size()
                    self.screen=pygame.display.set_mode((0,0),pygame.FULLSCREEN)
                else:
                    self.screen=pygame.display.set_mode(self.window_size,pygame.RESIZABLE)
                self.ime_rect()
            elif self.state=='result' and not self.saved:
                if event.key==pygame.K_BACKSPACE and not self.composition:
                    self.name='' if event.mod&pygame.KMOD_CTRL else self.name[:-1]
                elif event.key==pygame.K_a and event.mod&pygame.KMOD_CTRL:
                    self.name=''
                elif event.key in (pygame.K_RETURN,pygame.K_KP_ENTER) and not self.composition and self.t>=self.ime_guard:
                    self.submit()
            elif event.key==pygame.K_ESCAPE:
                if self.state in ('playing','countdown'):
                    self.pause()
                elif self.state=='paused':
                    self.resume()
                elif self.state=='leaderboard':
                    self.state=getattr(self,'board_from','menu')
            elif event.key==pygame.K_m:
                self.mute()
            elif event.key==pygame.K_SPACE:
                if self.state=='menu':
                    self.start()
                elif self.state=='paused':
                    self.resume()
                elif self.state=='playing':
                    self.game.activate_shield()
                    self.consume_events()
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            self.mouse=self.pos(event.pos)
            for rect,action in reversed(self.buttons):
                if rect.collidepoint(self.mouse):
                    self.audio.play('click')
                    action()
                    return
            if self.state=='playing':
                self.game.activate_shield()
                self.consume_events()

    def consume_events(self):
        for kind,x,y,message in self.game.events:
            px,py=self.scene.project(x,y,HIT_Z)
            if kind in ('collect','hit','blocked','shield','special_bonus'):
                color=RED if kind=='hit' else (GOLD if kind in ('collect','special_bonus') else CYAN)
                if message:
                    self.messages.append([message,px,py-65,.75,color])
                for _ in range(24 if kind=='hit' else 14):
                    angle=random.uniform(0,math.tau)
                    speed=random.uniform(80,250)
                    self.particles.append([px,py,random.uniform(.35,.8),color,math.cos(angle)*speed,math.sin(angle)*speed])
            if kind=='hit':
                self.shake=.28
                self.flash=.22
                self.audio.play('hit')
            elif kind in ('shield','blocked'):
                self.audio.play('shield')
            elif kind=='collect':
                self.audio.play('collect')
            elif kind=='special_bonus':
                self.audio.play('collect')
            elif kind=='event_start':
                pass
            elif kind=='hidden_start':
                self.audio.play('warning')
                self.last_tick=math.ceil(HIDDEN_SECONDS)
            elif kind=='shot':
                self.audio.play('shot')
            elif kind=='meteor_impact':
                self.shake=max(self.shake,.07)
                self.audio.play('pass')
            elif kind=='pass':
                self.audio.play('pass')
        self.game.events.clear()

    def update(self,dt):
        self.t+=dt
        self.toast_left=max(0.,self.toast_left-dt)
        if self.state not in ('paused','result','leaderboard'):
            self.scene_time+=dt
        if self.state=='countdown':
            before=math.ceil(self.countdown)
            self.countdown-=dt
            if self.countdown<=0:
                self.state='playing'
                self.audio.play('shield')
            elif before!=math.ceil(self.countdown):
                self.audio.play('tick')
        elif self.state=='playing':
            if self.control=='keyboard':
                keys=pygame.key.get_pressed()
                self.game.axis=(int(keys[pygame.K_RIGHT] or keys[pygame.K_d])-int(keys[pygame.K_LEFT] or keys[pygame.K_a]),
                                int(keys[pygame.K_DOWN] or keys[pygame.K_s])-int(keys[pygame.K_UP] or keys[pygame.K_w]))
            else:
                self.game.axis=None
            self.game.update(dt)
            self.consume_events()
            second=math.ceil(self.game.remaining)
            if 0<second<=5 and second!=self.last_tick:
                self.audio.play('tick')
            self.last_tick=second
            if self.game.ended:
                self.finish()
        if self.state!='paused':
            self.shake=max(0.,self.shake-dt)
            self.flash=max(0.,self.flash-dt)
            for particle in self.particles[:]:
                particle[2]-=dt
                particle[0]+=particle[4]*dt
                particle[1]+=particle[5]*dt
                if particle[2]<=0:
                    self.particles.remove(particle)
            for message in self.messages[:]:
                message[2]-=dt*25
                message[3]-=dt
                if message[3]<=0:
                    self.messages.remove(message)

    def glass(self,rect,border=(35,55,80)):
        rounded(self.canvas,(10,19,35),rect,18)
        rounded(self.canvas,border,rect,18,1)

    def button(self,rect,label,action,primary=False,selected=False,size=18):
        rect=pygame.Rect(rect)
        hover=rect.collidepoint(self.mouse)
        if primary:
            rounded(self.canvas,tint(CYAN,.18),rect.inflate(8,8),20)
            rounded(self.canvas,blend(CYAN,WHITE,.18) if hover else CYAN,rect,16)
            color=(9,34,43)
        else:
            rounded(self.canvas,(20,43,58) if selected or hover else (11,21,38),rect,14)
            rounded(self.canvas,CYAN if selected else (43,63,88),rect,14,1)
            color=CYAN if selected else WHITE
        text(self.canvas,label,rect.center,size,color,True,True)
        self.buttons.append((rect,action))

    def header(self):
        s=self.canvas
        pygame.draw.polygon(s,CYAN,[(47,31),(61,58),(47,51),(33,58)])
        text(s,'流光穿梭',(75,27),26,WHITE,True)
        text(s,'N E O N   D R I F T',(78,65),10,MUTED)
        active=self.state in ('playing','countdown')
        self.button((949,31,126,43),'暂停' if active else '排行榜',self.pause if active else self.leaderboard,size=16)
        self.button((1093,31,151,43),'声音：关' if self.audio.muted else '声音：开',self.mute,size=16)

    def menu_ui(self):
        s=self.canvas
        # Left-side fade creates a clear editorial layout over a moving tunnel.
        fade=pygame.Surface((640,H),pygame.SRCALPHA)
        for x in range(640):
            pygame.draw.line(fade,(5,9,22,max(0,int(239*(1-x/640)**.45))),(x,115),(x,H))
        s.blit(fade,(0,0))
        text(s,'30 秒，穿越光的边界',(77,169),19,CYAN)
        text(s,'流 光',(70,216),76,WHITE,True)
        text(s,'穿 梭',(70,307),76,WHITE,True)
        text(s,'穿越光栅与弹幕，躲开奶龙的进攻。',(79,418),18,MUTED)
        text(s,'速度更快，变化更多。',(79,449),17,MUTED)
        for i,(key,config) in enumerate(MODES.items()):
            self.button((78+i*116,508,105,51),config['name'],lambda k=key:self.set_mode(k),selected=self.mode==key,size=19)
        text(s,MODES[self.mode]['tag']+'  /  每局 30 秒',(79,576),14,MUTED)
        self.button((78,615,337,68),'启 动 穿 梭    ›',self.start,True,size=25)
        self.button((78,710,160,42),'鼠标操控',lambda:self.set_control('mouse'),selected=self.control=='mouse',size=15)
        self.button((254,710,160,42),'方向键 / WASD',lambda:self.set_control('keyboard'),selected=self.control=='keyboard',size=15)
        text(s,'单击 / 空格：护盾    Esc：暂停    F11：全屏',(79,781),12,MUTED)
        self.glass((856,685,350,91),(37,66,88))
        text(s,'四 种 奶 龙，六 类 障 碍',(881,704),16,WHITE,True)
        text(s,'冲锋  ·  变向  ·  集群  ·  双枪弹幕',(881,741),13,MUTED)
        variant=('brute','plain','trickster','gunner')[int(self.t/4)%4]
        image=enemy_sprite(variant,192,False,0)
        s.blit(image,(1035,474+math.sin(self.t*2)*5))

    def hud(self):
        s=self.canvas
        self.glass((31,137,186,82))
        text(s,'得分',(48,150),12,MUTED)
        text(s,f'{self.game.score:05}',(47,171),29,WHITE,True)
        self.glass((231,137,154,82))
        text(s,'隐藏关 · 时间' if self.game.hidden_unlocked else '时间',(249,150),12,GOLD if self.game.hidden_unlocked else MUTED)
        text(s,f'{self.game.remaining:04.1f}',(247,171),29,RED if self.game.remaining<=5 else CYAN,True)
        self.glass((1063,137,185,82))
        text(s,'装甲',(1082,151),12,MUTED)
        for i in range(MAX_LIVES):
            step=148/MAX_LIVES
            rounded(s,CYAN if i<self.game.lives else (30,45,62),(1082+i*step,180,int(step-7),16),5)
        for message,x,y,life,color in self.messages:
            text(s,message,(x,y),16,color,True,True)
        self.glass((448,747,384,53),(33,69,82))
        text(s,'护盾',(466,756),12,WHITE,True)
        value=f'{self.game.shield:.1f}s' if self.game.shield>0 else f'{int(self.game.charge)}%'
        text(s,value,(777,756),12,CYAN)
        rounded(s,(25,43,58),(466,782,348,5),2)
        charge=self.game.shield/2 if self.game.shield>0 else self.game.charge/100
        if charge>0:
            rounded(s,CYAN,(466,782,max(1,round(348*charge)),5),2)
        if self.game.hidden_unlocked and self.game.elapsed-ROUND_SECONDS<2.0:
            self.glass((402,242,476,66),(157,63,111))
            text(s,'隐 藏 航 线 已 解 锁',(640,263),23,GOLD,True,True)
            text(s,'超频模式',(640,290),12,WHITE,center=True)

    def dim(self):
        overlay=pygame.Surface((W,H),pygame.SRCALPHA)
        overlay.fill((2,6,17,192))
        self.canvas.blit(overlay,(0,0))
        self.buttons.clear()

    def countdown_ui(self):
        self.dim()
        self.glass((436,255,408,324),(54,91,113))
        text(self.canvas,'准备进入航线',(640,304),25,WHITE,True,True)
        text(self.canvas,str(max(1,math.ceil(self.countdown))),(640,407),99,CYAN,True,True)
        text(self.canvas,'R E A D Y',(640,535),13,MUTED,center=True)

    def paused_ui(self):
        self.dim()
        self.glass((421,248,438,351),(54,91,113))
        text(self.canvas,'航线已暂停',(640,303),31,WHITE,True,True)
        text(self.canvas,'下一束光，等你出发',(640,354),17,MUTED,center=True)
        self.button((473,410,334,59),'继 续 航 行',self.resume,True,size=22)
        self.button((473,493,334,49),'结束本局并记录成绩',self.end_early,size=17)
        text(self.canvas,'Esc / 空格：继续',(640,571),13,MUTED,center=True)

    def result_ui(self):
        self.dim()
        s=self.canvas
        self.glass((328,111,624,616),(45,82,105))
        text(s,'F L I G H T   R E C O R D',(640,150),12,CYAN,True,True)
        text(s,self.game.reason or '穿越完成',(640,204),34,WHITE,True,True)
        text(s,f'{self.game.score:05}',(640,283),70,CYAN,True,True)
        detail=MODES[self.game.mode]['name']+f'  ·  航行 {self.game.elapsed:.1f} 秒  ·  彩蛋 {len(self.game.special_history)} 次'
        if self.game.hidden_unlocked:
            detail+='  ·  隐藏航线'
        text(s,detail,(640,352),16,MUTED,center=True)
        for x,value,label in [(447,str(self.game.orbs),'收集能量'),(640,str(self.game.dodges),'成功穿越'),(833,str(self.game.best_chain),'最高连收')]:
            text(s,value,(x,400),24,WHITE,True,True)
            text(s,label,(x,435),12,MUTED,center=True)
        field_rect=pygame.Rect(389,477,502,55)
        rounded(s,(8,15,29),field_rect,12)
        rounded(s,(41,89,106) if self.saved else CYAN,field_rect,12,1)
        value=self.name+self.composition
        if value:
            fitted(s,value,(407,490),450,23,WHITE)
        else:
            text(s,'写下你的名字，留下这次高光',(407,495),17,MUTED)
        if not self.saved and int(self.t*2)%2==0:
            cursor=min(867,408+font(23).size(value)[0])
            pygame.draw.line(s,CYAN,(cursor,490),(cursor,519),2)
        if self.saved:
            text(s,'成绩已保存到本地排行榜',(640,559),14,CYAN,center=True)
            self.button((389,589,240,58),'查 看 排 行 榜',self.leaderboard,True,size=18)
            self.button((650,589,241,58),'再 次 出 发',self.start,size=18)
        else:
            text(s,'中文 / 英文，最多12字  ·  Ctrl+A 清空  ·  Enter 保存',(640,556),12,MUTED,center=True)
            self.button((389,589,502,58),'保 存 成 绩',self.submit,True,size=22)
        self.button((506,676,268,30),'返回首页' if self.saved else '暂不保存，返回首页',self.menu,size=13)

    def leaderboard_ui(self):
        self.dim()
        s=self.canvas
        self.glass((181,95,918,658),(45,82,105))
        text(s,'航 行 荣 誉 榜',(223,126),29,WHITE,True)
        text(s,'每一次穿梭，都有迹可循',(225,176),14,MUTED)
        for i,(key,config) in enumerate(MODES.items()):
            self.button((680+i*122,138,105,43),config['name'],lambda k=key:self.set_mode(k),selected=self.mode==key,size=16)
        rounded(s,(17,33,51),(219,217,842,37),9)
        for label,x in [('名次',236),('飞行员',320),('得分',596),('能量',737),('日期',900)]:
            text(s,label,(x,226),13,MUTED,True)
        rows=self.storage.top(self.mode)
        if not rows:
            pygame.draw.polygon(s,CYAN,[(640,332),(691,426),(640,405),(589,426)],3)
            text(s,'第一条航行记录，等你来创造',(640,496),22,WHITE,True,True)
        for i,record in enumerate(rows):
            y=269+i*37
            active=self.saved_record and self.saved_record['id']==record.get('id')
            if active or i%2==0:
                rounded(s,(19,46,57) if active else (12,23,40),(219,y-2,842,35),7)
            text(s,f'{i+1:02}',(240,y+3),17,GOLD if i<3 else MUTED,True)
            fitted(s,record['name'],(320,y+3),248,17,WHITE,active)
            text(s,str(record['score']),(596,y+3),17,CYAN,True)
            text(s,str(record.get('orbs',0)),(744,y+3),16,WHITE)
            text(s,record['date'][5:16],(896,y+5),13,MUTED)
        text(s,'三个难度分别排名 · 显示前10名 · 所有已提交记录均保存在本地',(640,667),12,MUTED,center=True)
        self.button((379,700,242,37),'返回首页',self.menu,size=16)
        self.button((646,700,242,37),'再次出发',self.start,True,size=16)

    def draw(self):
        self.buttons=[]
        self.scene.draw(self.canvas,self.game,self.scene_time,self.state=='menu',self.particles)
        if self.flash>0:
            layer=pygame.Surface((W,H),pygame.SRCALPHA)
            layer.fill((255,60,88,int(self.flash/.22*60)))
            self.canvas.blit(layer,(0,0))
        self.header()
        if self.state=='menu':
            self.menu_ui()
        else:
            self.hud()
        if self.state=='countdown':
            self.countdown_ui()
        elif self.state=='paused':
            self.paused_ui()
        elif self.state=='result':
            self.result_ui()
        elif self.state=='leaderboard':
            self.leaderboard_ui()
        if self.toast_left>0:
            width=min(1100,font(17).size(self.toast)[0]+48)
            self.glass(((W-width)//2,28,width,47),(47,100,116))
            text(self.canvas,self.toast,(640,51),17,WHITE,center=True)
        sw,sh=self.screen.get_size()
        scale=min(sw/W,sh/H)
        size=(round(W*scale),round(H*scale))
        image=self.canvas if size==(W,H) else pygame.transform.smoothscale(self.canvas,size)
        self.screen.fill((2,4,12))
        ox,oy=(sw-size[0])//2,(sh-size[1])//2
        if self.shake>0:
            ox+=random.randint(-4,4)
            oy+=random.randint(-3,3)
        self.screen.blit(image,(ox,oy))
        pygame.display.flip()

    def run(self):
        self.draw()
        while self.running:
            dt=self.clock.tick(60)/1000
            for event in pygame.event.get():
                self.handle(event)
            self.update(dt)
            self.draw()
        pygame.key.stop_text_input()
        pygame.quit()


def main():
    parser=argparse.ArgumentParser(description='流光穿梭 — 30秒霓虹飞行挑战')
    parser.add_argument('--preview',choices=['menu','playing','paused','result','leaderboard'])
    args=parser.parse_args()
    if args.preview:
        os.environ['SDL_VIDEODRIVER']='dummy'
        os.environ['SDL_AUDIODRIVER']='dummy'
        app=App(Storage(ROOT/'previews'/'sample-data'))
        app.state=args.preview
        app.scene_time=8.4
        if args.preview!='menu':
            app.game.elapsed=14.2
            app.game.distance=234
            app.game.orbs=8
            app.game.dodges=7
            app.game.bonus=440
            app.game.best_chain=5
            app.game.x,app.game.y=.12,.23
            app.game.waves=[Wave(13,[Block(-.34,-.20)],orbs=[(.4,.2)]),
                            Wave(24,opening=(.1,-.1,.66,.63),orbs=[(.1,-.1)]),
                            Wave(6,[Block(.56,-.4)],orbs=[(-.4,.3)])]
            app.game.reason='穿越完成'
            app.name='追光者'
            if args.preview=='result':
                app.game.elapsed=ROUND_SECONDS
                app.game.distance=app.game.config['speed']*ROUND_SECONDS+10*ROUND_SECONDS/2
        app.draw()
        path=ROOT/'previews'/(args.preview+'.png')
        pygame.image.save(app.canvas,str(path))
        print(path)
        pygame.quit()
    else:
        App().run()


if __name__=='__main__':
    try:
        main()
    except Exception:
        import traceback
        (ROOT/'data'/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        if '--preview' not in sys.argv and sys.platform=='win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'启动遇到问题，详细信息已保存在项目 data/error.log。','流光穿梭',16)
        raise
