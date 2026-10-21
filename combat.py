"""Pure-Python flight, moving obstacles, dragon attacks and projectile physics."""
from dataclasses import dataclass, field
import math
import random

ROUND_SECONDS=30.0
HIDDEN_SECONDS=15.0
HIT_Z=3.0
SHIP_RADIUS=.040
MAX_LIVES=3
MODES={
    'easy': {'name':'漫游','tag':'快速热身','speed':15.,'interval':1.00,'gap':.75,'blocks':2,'fire':1.40,'bullets':.50,'invuln':.90},
    'normal': {'name':'疾驰','tag':'高速交锋','speed':20.,'interval':.72,'gap':.63,'blocks':3,'fire':1.20,'bullets':.64,'invuln':.72},
    'hard': {'name':'极限','tag':'进阶挑战','speed':25.,'interval':.53,'gap':.54,'blocks':4,'fire':.95,'bullets':.80,'invuln':.56},
}
SPECIALS={
    'brute':('重装冲锋','',4.5), 'swarm':('奶龙集群','',4.6),
    'trickster':('虚晃变向','',4.5), 'gunner':('双枪弹幕','',5.1),
    'rush':('能量狂潮','',3.8), 'meteor':('流星群','',4.5),
}
PATTERNS=('blocks','moving','laser','grid','ring','mines')


def clamp(value,low,high):
    return max(low,min(high,value))


@dataclass
class Block:
    x:float
    y:float
    width:float=.40
    height:float=.34
    angle:float=0.
    shape:str='block'

    def outline(self):
        """Shared world-space silhouette for crystalline obstacles."""
        w,h=self.width,self.height
        offsets=((-w*.5,-h*.12),(-w*.22,-h*.5),(w*.25,-h*.5),
                 (w*.5,h*.12),(w*.22,h*.5),(-w*.25,h*.5))
        ca,sa=math.cos(self.angle),math.sin(self.angle)
        return [(self.x+dx*ca-dy*sa,self.y+dx*sa+dy*ca) for dx,dy in offsets]

    def collides(self,x,y):
        dx,dy=x-self.x,y-self.y
        if self.shape=='mine':
            return math.hypot(dx,dy)<self.width/2+SHIP_RADIUS
        ca,sa=math.cos(self.angle),math.sin(self.angle)
        local_x=dx*ca+dy*sa
        local_y=-dx*sa+dy*ca
        if self.shape in ('laser','grid'):
            # Rounded energy beams use a capsule rather than a bounding box.
            if self.width>=self.height:
                half=(self.width-self.height)/2
                distance=math.hypot(local_x-clamp(local_x,-half,half),local_y)
            else:
                half=(self.height-self.width)/2
                distance=math.hypot(local_x,local_y-clamp(local_y,-half,half))
            return distance<min(self.width,self.height)/2+SHIP_RADIUS
        vertices=self.outline()
        inside=True
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            ex,ey=b[0]-a[0],b[1]-a[1]
            px,py=x-a[0],y-a[1]
            if ex*py-ey*px<0:
                inside=False
            t=clamp((px*ex+py*ey)/(ex*ex+ey*ey),0,1)
            if math.hypot(px-ex*t,py-ey*t)<SHIP_RADIUS:
                return True
        return inside


@dataclass
class Wave:
    z:float=57.
    blocks:list=field(default_factory=list)
    opening:tuple|None=None
    orbs:list=field(default_factory=list)
    checked:bool=False
    source:str='normal'
    kind:str='blocks'
    age:float=0.
    phase:float=0.
    pressure_relief:bool=False

    def opening_at(self):
        if self.opening is None:
            return None
        x,y,w,h=self.opening
        if self.kind=='moving':
            x+=math.sin(self.age*1.45+self.phase)*.20
            y+=math.cos(self.age*1.2+self.phase)*.15
        return (x,y,w,h)

    def geometry(self):
        if self.kind=='laser':
            angle=self.age*.95+self.phase
            beams=[Block(0,0,1.92,.060,angle,'laser'),
                   Block(0,0,1.92,.060,angle+math.pi/2,'laser')]
            return beams[:1] if self.pressure_relief else beams
        if self.kind=='grid':
            vertical=math.sin(self.phase)>0
            offset=math.sin(self.age*1.1+self.phase)*.13
            positions=(-.48,.48) if self.pressure_relief else (-.58,0.,.58)
            return [Block(x+offset,0,.075,1.95,shape='grid') if vertical
                    else Block(0,x+offset,1.95,.075,shape='grid') for x in positions]
        if self.kind=='mines':
            return [Block(b.x+math.sin(self.age*1.7+i)*.10,
                          b.y+math.cos(self.age*1.4+i)*.07,b.width,b.height,shape='mine')
                    for i,b in enumerate(self.blocks)]
        return self.blocks

    def collides(self,x,y):
        opening=self.opening_at()
        if opening is not None:
            gx,gy,w,h=opening
            if self.kind in ('ring','moving'):
                return ((x-gx)/(w/2-SHIP_RADIUS))**2+((y-gy)/(h/2-SHIP_RADIUS))**2>1
            return abs(x-gx)>w/2-SHIP_RADIUS or abs(y-gy)>h/2-SHIP_RADIUS
        return any(block.collides(x,y) for block in self.geometry())


@dataclass
class Bullet:
    x:float
    y:float
    vx:float
    vy:float
    radius:float=.018
    age:float=0.
    color:str='orange'
    arm_time:float=.14

    def advance(self,dt):
        self.x+=self.vx*dt
        self.y+=self.vy*dt
        self.age+=dt


@dataclass
class Meteor:
    x:float
    y:float
    impact:float
    side:int=1
    resolved:bool=False


@dataclass
class Actor:
    variant:str
    motion:str
    x:float
    y:float
    z:float=HIT_Z
    side:int=1
    age:float=0.
    duration:float=3.0
    touched:bool=False
    checked:bool=False
    lane:float=0.
    radius_x:float=.12
    radius_y:float=.20
    size:float=.34
    charge_speed:float=32.

    def advance(self,dt):
        self.age+=dt
        if self.motion=='charge':
            self.z-=self.charge_speed*dt
        elif self.motion=='cross':
            p=clamp(self.age/self.duration,0,1)
            self.x=self.side*(1.2-2.4*p)
            self.y=self.lane+math.sin(p*math.tau)*.065
        elif self.motion=='trickster':
            t=self.age
            if t<.75:
                offset=1.1-1.5*t/.75
            elif t<1.05:
                offset=-.4
            elif t<1.8:
                offset=-.4+1.25*(t-1.05)/.75
            else:
                offset=.85-2.05*clamp((t-1.8)/1.4,0,1)
            self.x=self.side*offset
            self.y=self.lane+math.sin(t*3.5)*.19
        elif self.motion=='gunner':
            self.x=math.sin(self.age*1.5)*.57
            self.y=-.28+math.sin(self.age*.9)*.11

    def collides(self,x,y):
        if self.motion=='gunner':
            return False
        return ((x-self.x)/(self.radius_x+SHIP_RADIUS))**2+((y-self.y)/(self.radius_y+SHIP_RADIUS))**2<1


@dataclass
class Encounter:
    kind:str
    start:float
    side:int=-1
    lane:float=0.
    age:float=0.
    spawned:int=0
    shots:int=0
    fire_at:float=.75
    actors:list=field(default_factory=list)
    meteors:list=field(default_factory=list)
    auxiliary:bool=False
    auxiliary_sent:bool=False

    @property
    def duration(self):
        return SPECIALS[self.kind][2]


class Round:
    def __init__(self,mode='normal',rng=None,events_enabled=True):
        self.mode=mode
        self.config=MODES[mode]
        self.hidden_unlocked=False
        self.hidden_completed=False
        self.rng=rng or random.Random()
        self.elapsed=self.distance=0.
        self.bonus=self.orbs=self.dodges=self.chain=self.best_chain=0
        self.x=self.y=0.
        self.target=(0.,0.)
        self.axis=None
        self.lives=MAX_LIVES
        self.charge=100.
        self.shield=self.invulnerable=0.
        self.waves=[]
        self.bullets=[]
        self.actors=[]
        self.encounters=[]
        self.spawn_in=.45
        self.spawned=0
        self.events=[]
        self.ended=False
        self.reason=''
        self.special_history=[]
        self.specials_completed=0
        self.gold_trail=0.
        self.last_shield_fx=-10.
        self.special_schedule=[]
        if events_enabled:
            # Three spaced encounters; all four characters rotate across rounds.
            primaries=['gunner']+self.rng.sample(['brute','swarm','trickster'],2)
            if mode=='hard':
                windows=((4.0,4.4),(13.2,13.6),(22.4,22.8))
            else:
                windows=((4.6,5.0),(13.8,14.2),(23.0,23.4))
            self.rng.shuffle(primaries)
            self.special_schedule=[(self.rng.uniform(*window),kind) for window,kind in zip(windows,primaries)]

    @property
    def encounter(self):
        return self.encounters[0] if self.encounters else None

    @property
    def combat_active(self):
        return bool(self.actors or self.bullets or any(e.kind!='rush' for e in self.encounters))

    @property
    def remaining(self):
        end=ROUND_SECONDS+HIDDEN_SECONDS if self.hidden_unlocked else ROUND_SECONDS
        return max(0.,end-self.elapsed)

    @property
    def attack_mode(self):
        return 'hard' if self.hidden_unlocked else self.mode

    @property
    def speed(self):
        if self.hidden_unlocked:
            return self.config['speed']+(self.elapsed-ROUND_SECONDS)/HIDDEN_SECONDS*6
        return self.config['speed']+self.elapsed/ROUND_SECONDS*10

    @property
    def score(self):
        return int(self.distance*2+1e-7)+self.bonus

    @property
    def phase(self):
        if self.hidden_unlocked:
            return 3
        return min(2,int(self.elapsed/10))

    def enter_hidden(self):
        entry_speed=max(38.,self.speed*1.28)
        self.hidden_unlocked=True
        # A private configuration keeps the selected leaderboard difficulty
        # and future rounds unchanged.
        self.config=dict(MODES['hard'],speed=entry_speed,interval=.40,gap=.50,
                         fire=.78,bullets=.94,invuln=.55)
        self.waves.clear()
        self.bullets.clear()
        self.actors.clear()
        self.encounters.clear()
        self.spawn_in=.10
        self.special_schedule=[(ROUND_SECONDS+.60,'gunner'),
                               (ROUND_SECONDS+8.2,self.rng.choice(('brute','swarm','trickster')))]
        self.events.append(('hidden_start',self.x,self.y,''))

    def activate_shield(self):
        if self.ended or self.charge<100 or self.shield>0:
            return False
        self.charge=0.
        self.shield=2.
        self.events.append(('shield',self.x,self.y,''))
        return True

    def damage(self,x,y,label=''):
        if self.shield>0:
            if self.elapsed-self.last_shield_fx>.14:
                self.events.append(('blocked',x,y,''))
                self.last_shield_fx=self.elapsed
            return 'blocked'
        if self.invulnerable>0:
            return 'ignored'
        self.lives-=1
        self.chain=0
        self.invulnerable=self.config['invuln']
        self.events.append(('hit',x,y,''))
        if self.lives<=0:
            self.ended=True
            self.reason='隐藏关挑战结束' if self.hidden_unlocked else '本次航行结束'
        return 'hit'

    def spawn(self):
        self.spawned+=1
        gx=self.rng.choice((-.43,0.,.43))
        gy=self.rng.choice((-.33,0.,.33))
        kind=PATTERNS[(self.spawned-1)%len(PATTERNS)]
        # Random phase preserves variety while cycling through every style.
        wave=Wave(kind=kind,phase=self.rng.uniform(0,math.tau))
        gap=self.config['gap']
        if kind=='moving':
            wave.opening=(gx*.6,gy*.6,gap,gap*1.35)
        elif kind=='ring':
            wave.opening=(gx*.45,gy*.45,gap+.23,gap+.23)
        elif kind in ('blocks','mines'):
            candidates=[(x,y) for x in (-.56,0.,.56) for y in (-.40,0.,.40)
                        if abs(x-gx)>.32 or abs(y-gy)>.30]
            self.rng.shuffle(candidates)
            count=self.config['blocks'] if kind=='mines' else self.rng.randint(2,self.config['blocks'])
            width=.26 if kind=='mines' else .38
            wave.blocks=[Block(x,y,width,.30,self.rng.uniform(-.35,.35)) for x,y in candidates[:count]]
        if kind in ('blocks','mines'):
            wave.orbs=[(gx,gy)]
        elif kind in ('ring','moving'):
            wave.orbs=[(gx*.4,gy*.4)]
        if self.combat_active:
            self.ease_for_encounter(wave)
        self.waves.append(wave)

    @staticmethod
    def ease_for_encounter(wave):
        if wave.pressure_relief:
            return
        wave.pressure_relief=True
        if wave.opening is not None:
            x,y,w,h=wave.opening
            wave.opening=(x,y,min(1.15,w+.12),min(1.15,h+.12))

    def begin_special(self,kind,auxiliary=False):
        if self.ended or len(self.encounters)>=(2 if self.attack_mode=='hard' else 1):
            return False
        if kind!='rush' and any(e.kind!='rush' for e in self.encounters):
            return False
        e=Encounter(kind,self.elapsed,self.rng.choice((-1,1)),self.rng.choice((-.38,0.,.38)),auxiliary=auxiliary)
        self.encounters.append(e)
        self.special_history.append(kind)
        self.events.append(('event_start',0,0,''))
        if kind!='rush':
            for wave in self.waves:
                if not wave.checked:
                    self.ease_for_encounter(wave)
            self.spawn_in=max(self.spawn_in,self.config['interval']*1.65)
        if kind=='gunner':
            actor=Actor('gunner','gunner',0,-.28,5.2,duration=e.duration,size=.91)
            self.actors.append(actor)
            e.actors.append(actor)
        elif kind=='trickster':
            actor=Actor('trickster','trickster',e.side*1.1,e.lane,side=e.side,
                        duration=3.5,lane=e.lane,radius_x=.17,radius_y=.25,size=.43)
            self.actors.append(actor)
            e.actors.append(actor)
        elif kind=='rush':
            for i in range(9):
                x=e.side*(.25+math.sin(i*.6)*.17)
                y=math.sin(i*.5)*.32
                self.waves.append(Wave(HIT_Z+self.speed*(.55+i*.27),orbs=[(x,y)],source='rush'))
        elif kind=='meteor':
            count=4 if self.attack_mode=='easy' else (5 if self.attack_mode=='normal' else 7)
            for i in range(count):
                x=clamp(self.x+self.rng.uniform(-.40,.40),-.65,.65) if i%2==0 else self.rng.uniform(-.62,.62)
                y=clamp(self.y+self.rng.uniform(-.38,.38),-.56,.56)
                e.meteors.append(Meteor(x,y,self.elapsed+1.0+i*.43,e.side))
        return True

    def emit_bullets(self,e):
        if not e.actors:
            return
        shooter=e.actors[0]
        factor=(HIT_Z+1)/(shooter.z+1)
        cx,cy=shooter.x*factor,shooter.y*factor-.05
        speed=self.config['bullets']
        mode=self.attack_mode
        pattern=e.shots%3
        ports=(-1,1) if pattern!=2 else ((-1,) if e.shots%2==0 else (1,))
        cap={'easy':40,'normal':60,'hard':80}[mode]
        for port in ports:
            x,y=cx+port*.25,cy+port*.045
            if pattern==0:
                aimed=math.atan2(self.y-y,self.x-x)
                if mode=='easy':
                    offsets=(-.62,.62)
                elif mode=='normal':
                    offsets=(-.55,.55)
                else:
                    offsets=(-.82,-.40,.40,.82)
                angles=[aimed+offset for offset in offsets]
            elif pattern==1:
                offsets=(0.,) if mode=='easy' else ((-.48,.48) if mode=='normal' else (-.6,0.,.6))
                angles=[math.pi/2+offset for offset in offsets]
            else:
                count={'easy':5,'normal':6,'hard':8}[mode]
                angles=[j*math.tau/count+e.shots*.31+port*.12 for j in range(count)]
            for angle in angles:
                if len(self.bullets)<cap:
                    self.bullets.append(Bullet(x,y,math.cos(angle)*speed,math.sin(angle)*speed,
                                               color='pink' if pattern==2 else 'orange'))
        e.shots+=1
        self.events.append(('shot',cx,cy,''))

    def update_events(self,dt):
        if self.special_schedule and self.elapsed>=self.special_schedule[0][0]:
            _,kind=self.special_schedule[0]
            if self.begin_special(kind):
                self.special_schedule.pop(0)
        for e in self.encounters[:]:
            e.age=self.elapsed-e.start
            if e.kind=='brute':
                times=(.35,) if self.attack_mode!='hard' else (.35,2.35)
                while e.spawned<len(times) and e.age>=times[e.spawned]:
                    x=clamp(self.x+self.rng.uniform(-.15,.15),-.55,.55)
                    y=clamp(self.y+self.rng.uniform(-.12,.12),-.42,.42)
                    actor=Actor('brute','charge',x,y,40,side=e.side,duration=2.,
                                radius_x=.27,radius_y=.41,size=.70,
                                charge_speed=38 if self.hidden_unlocked else {'easy':26,'normal':29,'hard':32}[self.mode])
                    self.actors.append(actor)
                    e.actors.append(actor)
                    e.spawned+=1
            elif e.kind=='swarm':
                count=1 if self.attack_mode=='easy' else 2
                while e.spawned<count and e.age>=.30+e.spawned*1.55:
                    lane=(-.40,.40)[e.spawned]
                    actor=Actor('plain','cross',e.side*1.2,lane,side=e.side*(-1 if e.spawned%2 else 1),
                                duration=1.6 if self.hidden_unlocked else (2.6 if self.mode=='easy' else 1.9),lane=lane)
                    self.actors.append(actor)
                    e.actors.append(actor)
                    e.spawned+=1
            elif e.kind=='gunner' and e.age>=e.fire_at:
                self.emit_bullets(e)
                e.fire_at+=self.config['fire']
            elif e.kind=='meteor':
                for meteor in e.meteors:
                    if not meteor.resolved and self.elapsed>=meteor.impact:
                        meteor.resolved=True
                        if math.hypot(self.x-meteor.x,self.y-meteor.y)<.16+SHIP_RADIUS:
                            self.damage(self.x,self.y)
                        else:
                            self.bonus+=50
                            self.dodges+=1
                        self.events.append(('meteor_impact',meteor.x,meteor.y,''))
            if self.attack_mode=='hard' and not e.auxiliary and not e.auxiliary_sent and e.age>=1.4:
                if self.begin_special('rush',True):
                    e.auxiliary_sent=True
            if e.age>=e.duration:
                self.specials_completed+=1
                self.encounters.remove(e)

    def update_actors(self,dt):
        for actor in self.actors[:]:
            before=actor.z
            actor.advance(dt)
            contact=False
            if actor.motion=='charge':
                if not actor.checked and before>HIT_Z>=actor.z:
                    actor.checked=True
                    contact=actor.collides(self.x,self.y)
                    if not contact:
                        self.bonus+=90
                        self.dodges+=1
            elif actor.motion!='gunner' and not actor.touched:
                contact=actor.collides(self.x,self.y)
            if contact:
                actor.touched=True
                self.damage(self.x,self.y)
            if actor.age>=actor.duration or actor.z<.7:
                if actor.motion in ('cross','trickster') and not actor.touched:
                    self.bonus+=45
                    self.dodges+=1
                self.actors.remove(actor)

    def update_bullets(self,dt):
        for bullet in self.bullets[:]:
            bullet.advance(dt)
            if bullet.age>=bullet.arm_time and math.hypot(self.x-bullet.x,self.y-bullet.y)<SHIP_RADIUS+bullet.radius:
                self.damage(self.x,self.y)
                self.bullets.remove(bullet)
            elif bullet.age>3.6 or abs(bullet.x)>1.25 or abs(bullet.y)>1.25:
                self.bullets.remove(bullet)

    def update(self,dt):
        if self.ended or dt<=0:
            return
        left=min(float(dt),ROUND_SECONDS+HIDDEN_SECONDS-self.elapsed)
        while left>1e-8 and not self.ended:
            boundary=ROUND_SECONDS+HIDDEN_SECONDS if self.hidden_unlocked else ROUND_SECONDS
            step=min(.025,left,max(0.,boundary-self.elapsed))
            if step>0:
                self._step(step)
            left-=step
            if self.elapsed>=boundary-1e-7 and not self.ended:
                self.elapsed=boundary
                if not self.hidden_unlocked and self.lives==MAX_LIVES:
                    self.enter_hidden()
                else:
                    self.ended=True
                    self.hidden_completed=self.hidden_unlocked
                    self.reason='隐藏关通关' if self.hidden_completed else '穿越完成'

    def _step(self,dt):
        previous_speed=self.speed
        self.elapsed+=dt
        distance=(previous_speed+self.speed)*.5*dt
        self.distance+=distance
        self.shield=max(0,self.shield-dt)
        self.invulnerable=max(0,self.invulnerable-dt)
        self.gold_trail=max(0,self.gold_trail-dt)
        if self.axis is not None:
            ax,ay=self.axis
            length=max(1.,math.hypot(ax,ay))
            self.x+=ax/length*2.25*dt
            self.y+=ay/length*2.25*dt
        else:
            ease=1-math.exp(-16*dt)
            self.x+=(self.target[0]-self.x)*ease
            self.y+=(self.target[1]-self.y)*ease
        length=math.hypot(self.x,self.y)
        if length>.84:
            self.x*=.84/length
            self.y*=.84/length
        self.update_events(dt)
        self.update_actors(dt)
        if self.ended:
            return
        self.update_bullets(dt)
        if self.ended:
            return
        # Keep traffic moving, with fewer waves while enemies or their
        # remaining bullets are active.
        self.spawn_in-=dt
        if self.spawn_in<=0:
            self.spawn()
            self.spawn_in+=self.config['interval']*(1.65 if self.combat_active else 1.)
        for wave in self.waves[:]:
            before=wave.z
            wave.z-=distance
            wave.age+=dt
            if not wave.checked and before>HIT_Z>=wave.z:
                wave.checked=True
                if wave.collides(self.x,self.y):
                    self.damage(self.x,self.y)
                else:
                    self.dodges+=1
                    self.bonus+=15
                collected=False
                for ox,oy in wave.orbs:
                    if math.hypot(self.x-ox,self.y-oy)<.20:
                        collected=True
                        self.orbs+=1
                        self.chain+=1
                        self.best_chain=max(self.best_chain,self.chain)
                        points=(25+min(25,self.chain*2))*(2 if wave.source=='rush' else 1)
                        self.bonus+=points
                        self.charge=min(100,self.charge+20)
                        if wave.source=='rush':
                            self.gold_trail=1.
                        self.events.append(('collect',ox,oy,'+'+str(points)))
                if wave.orbs and not collected:
                    self.chain=0
            if wave.z<.55:
                self.waves.remove(wave)
