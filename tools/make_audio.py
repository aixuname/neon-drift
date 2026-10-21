"""Create original synthwave music and arcade effects, entirely locally."""
import array
import math
import os
from pathlib import Path
import random
import wave

ROOT=Path(__file__).resolve().parents[1]
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'temp')
FOLDER=ROOT/'assets'/'sounds'
FOLDER.mkdir(parents=True,exist_ok=True)
RATE=22050


def write(name,samples):
    peak=max(.9,max(abs(x) for x in samples))
    pcm=array.array('h',(int(max(-1,min(1,x/peak))*.88*32767) for x in samples))
    with wave.open(str(FOLDER/(name+'.wav')),'wb') as file:
        file.setparams((1,2,RATE,0,'NONE','not compressed'))
        file.writeframes(pcm.tobytes())


def music():
    samples=[0.]*(RATE*16)
    noise=random.Random(238)
    def note(start,duration,midi,gain,voice='pluck'):
        frequency=440*2**((midi-69)/12)
        first=round(start*RATE)
        count=min(round(duration*RATE),len(samples)-first)
        for i in range(count):
            t=i/RATE
            if voice=='pad':
                envelope=min(1,t/.16)*min(1,(duration-t)/.2)
                value=math.sin(math.tau*frequency*t)+.25*math.sin(math.tau*frequency*1.003*t)
            elif voice=='bass':
                envelope=min(1,t/.007)*math.exp(-t*7)*min(1,(duration-t)/.035)
                value=math.sin(math.tau*frequency*t)+.27*math.sin(math.tau*frequency*2*t)
            else:
                envelope=min(1,t/.004)*math.exp(-t*11)*min(1,(duration-t)/.05)
                value=math.sin(math.tau*frequency*t)+.28*math.sin(math.tau*frequency*2*t)+.12*math.sin(math.tau*frequency*4*t)
            samples[first+i]+=value*envelope*gain
    chords=[(48,60,63,67),(44,56,60,63),(51,58,63,67),(46,58,62,65)]
    for bar in range(8):
        chord=chords[bar%4]
        start=bar*2
        for midi in chord[1:]:
            note(start,1.92,midi,.025,'pad')
        for step in range(8):
            note(start+step*.25,.23,chord[0] if step%2==0 else chord[0]+12,.14,'bass')
            note(start+step*.25,.23,chord[1+step%3]+12,.075)
        for beat in range(4):
            position=round((start+beat*.5)*RATE)
            for i in range(round(.18*RATE)):
                t=i/RATE
                kick=math.sin(math.tau*(47*t+55*.025*(1-math.exp(-t/.025))))*math.exp(-t*24)*.23
                if position+i<len(samples):
                    samples[position+i]+=kick
            hat_start=position+round(.25*RATE)
            for i in range(round(.055*RATE)):
                if hat_start+i<len(samples):
                    samples[hat_start+i]+=noise.uniform(-1,1)*math.exp(-i/RATE*80)*.025
    write('neon_loop',samples)


def effect(name,duration,notes=None,noise_amount=0,sweep=None):
    rng=random.Random(91)
    data=[]
    for i in range(round(duration*RATE)):
        t=i/RATE
        p=t/duration
        envelope=min(1,t/.006)*min(1,(duration-t)/.04)*math.exp(-p*2.8)
        value=0.
        if sweep:
            f0,f1=sweep
            phase=math.tau*(f0*t+(f1-f0)*t*t/(2*duration))
            value=math.sin(phase)+.17*math.sin(phase*2)
        if notes:
            n=min(len(notes)-1,int(p*len(notes)))
            frequency=440*2**((notes[n]-69)/12)
            local_t=t-n*duration/len(notes)
            value+=math.sin(math.tau*frequency*local_t)*math.exp(-local_t*9)
        value+=rng.uniform(-1,1)*noise_amount
        data.append(value*envelope*.5)
    write(name,data)


if __name__=='__main__':
    music()
    effect('click',.08,sweep=(780,490))
    effect('collect',.24,notes=[79,86])
    effect('hit',.35,sweep=(140,42),noise_amount=.65)
    effect('shield',.52,sweep=(210,1050),notes=[60,67,72])
    effect('pass',.12,sweep=(280,510),noise_amount=.04)
    effect('finish',.85,notes=[72,75,79,84])
    effect('tick',.10,sweep=(990,750))
    effect('event',.45,notes=[72,76,79,84])
    effect('warning',.48,notes=[76,64,76])
    effect('shot',.09,sweep=(920,290),noise_amount=.10)
    print('Original soundtrack and ten sound effects ready.')
