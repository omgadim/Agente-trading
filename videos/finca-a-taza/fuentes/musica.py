# Guitarra acústica sintetizada (Karplus-Strong), arpegios cálidos. Pista original, libre de derechos.
import numpy as np, wave
SR=48000; BPM=78; DUR=33.5
beat=60/BPM; e=beat/2
rng=np.random.default_rng(7)
def pluck(freq,dur,amp=0.5,bright=0.5):
    n=int(SR*dur); N=int(SR/freq)
    buf=rng.uniform(-1,1,N)
    buf=np.convolve(buf,[bright,1-bright],'same')
    out=np.empty(n); d=0.996
    for i in range(n):
        out[i]=buf[i%N]; buf[i%N]=d*0.5*(buf[i%N]+buf[(i+1)%N])
    env=np.minimum(1,np.arange(n)/(0.004*SR))
    return out*env*amp
def hz(m): return 440*2**((m-69)/12)
# I – V/vii – vi – IV en Do: C, G/B, Am, F  (2 compases cada uno → 4 acordes x 2)
chords=[[48,55,60,64,67],[47,55,59,62,67],[45,52,57,60,64],[41,53,57,60,65]]
pattern=[0,2,3,4,3,2,1,3]  # arpegio en corcheas
L=int(SR*(DUR+3)); mixL=np.zeros(L); mixR=np.zeros(L)
t=0.0; bar=0
while t<DUR:
    ch=chords[(bar//2)%4]
    for k,idx in enumerate(pattern):
        s=int(t*SR); note=ch[idx]
        a=0.42 if k==0 else 0.3
        x=pluck(hz(note),2.2,a,0.35 if idx<2 else 0.55)
        pan=0.5+0.25*np.sin(note)  # reparto estéreo suave
        end=min(L,s+len(x)); mixL[s:end]+=x[:end-s]*(1-pan); mixR[s:end]+=x[:end-s]*pan
        t+=e
    bar+=1
# bajo suave en cada compás
for b in range(int(DUR/(4*beat))+1):
    s=int(b*4*beat*SR); x=pluck(hz(chords[(b//2)%4][0]-12),3.0,0.35,0.15)
    end=min(L,s+len(x)); mixL[s:end]+=x[:end-s]; mixR[s:end]+=x[:end-s]
# "sala": ecos cortos para calidez
def room(x):
    y=x.copy()
    for dly,g in [(0.031,0.35),(0.057,0.25),(0.089,0.18),(0.137,0.12),(0.211,0.08)]:
        n=int(dly*SR); y[n:]+=g*x[:-n]
    return y
mixL,mixR=room(mixL),room(mixR[::-1])[::-1]*0+room(mixR)
n=int(DUR*SR); st=np.stack([mixL[:n],mixR[:n]],1)
fi=int(1.5*SR); fo=int(3.0*SR)
st[:fi]*=np.linspace(0,1,fi)[:,None]; st[-fo:]*=np.linspace(1,0,fo)[:,None]
st/=np.max(np.abs(st))*1.12
with wave.open('work/musica_acustica.wav','wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st*32767).astype('<i2').tobytes())
print('ok',DUR)
