from PIL import Image, ImageDraw, ImageFont, ImageFilter
W,H=1080,1920
LORA='/mnt/skills/examples/canvas-design/canvas-fonts/'
T=ImageFont.truetype(LORA+'Lora-BoldItalic.ttf',96)
S=ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-SemiBold.otf',46)
CREMA=(255,244,224,255); DORADO=(226,178,104,255)
escenas={
 'A':('De nuestra finca…','Donde todo comienza'),
 'B':('Cultivado|con paciencia','Cuidado desde el semillero'),
 'C':('Cosechado|a mano','Solo los granos en su punto'),
 'D':('Seleccionado|grano a grano','Calidad que se nota'),
 'E':('…a tu taza','Café de especialidad'),
}
def centrado(d,y,txt,font,fill):
    for line in txt.split('|'):
        w=d.textlength(line,font=font); d.text(((W-w)/2,y),line,font=font,fill=fill); y+=font.size*1.18
    return y
for k,(t,s) in escenas.items():
    img=Image.new('RGBA',(W,H),(0,0,0,0))
    # degradado oscuro arriba para legibilidad
    g=Image.new('L',(1,760));[g.putpixel((0,i),int(175*(1-i/760)**1.4)) for i in range(760)]
    img.paste((20,12,6,255),(0,0,W,760),g.resize((W,760)))
    sh=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(sh)
    y=centrado(d,300,t,T,(0,0,0,200)); centrado(d,y+18,s,S,(0,0,0,200))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    d=ImageDraw.Draw(img); y=centrado(d,296,t,T,CREMA)
    d.line(((W/2-60,y+4),(W/2+60,y+4)),fill=DORADO,width=3)
    centrado(d,y+22,s,S,CREMA)
    img.save(f'work/txt/{k}.png')
# Tarjeta final
bg=Image.new('RGB',(W,H)); d=ImageDraw.Draw(bg)
for y in range(H):
    t=y/H; c=tuple(int(a*(1-t)+b*t) for a,b in zip((46,28,16),(14,8,5))); d.line(((0,y),(W,y)),fill=c)
logo=Image.open('work/img/logo_crop.png').crop((0,10,930,612)).convert('RGB')
logo=logo.resize((1000,int(logo.height*1000/logo.width)),Image.LANCZOS)
m=Image.new('L',logo.size,0); ImageDraw.Draw(m).rounded_rectangle((70,60,logo.width-70,logo.height-50),radius=90,fill=255)
m=m.filter(ImageFilter.GaussianBlur(55))
bg.paste(logo,((W-logo.width)//2,560),m)
d=ImageDraw.Draw(bg)
F=ImageFont.truetype(LORA+'Lora-BoldItalic.ttf',104)
centrado(d,1300,'Pide el tuyo hoy',F,DORADO)
centrado(d,1450,'De nuestra finca a tu taza',ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-Medium.otf',44),CREMA)
bg.save('work/img/11_cierre.jpg',quality=95)
