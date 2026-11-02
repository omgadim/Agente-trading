from PIL import Image, ImageDraw, ImageFont, ImageFilter
W,H=1080,1920
im=Image.open('/root/.claude/uploads/6e2180ac-0d8a-591a-91e3-874b0baff01e/a0546852-image.jpg').convert('RGB')
s=H/im.height; im=im.resize((round(im.width*s),H),Image.LANCZOS)
x=(im.width-W)//2; bg=im.crop((x,0,x+W,H)).convert('RGBA')
LORA='/mnt/skills/examples/canvas-design/canvas-fonts/'
F=ImageFont.truetype(LORA+'Lora-BoldItalic.ttf',92); f2=ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-SemiBold.otf',42)
def put(img,y,txt,font,fill):
    d=ImageDraw.Draw(img); w=d.textlength(txt,font=font); d.text(((W-w)/2,y),txt,font=font,fill=fill)
sh=Image.new('RGBA',(W,H),(0,0,0,0))
put(sh,1318,'Pide el tuyo hoy',F,(0,0,0,230)); put(sh,1438,'De nuestra finca a tu taza',f2,(0,0,0,230))
bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10))); bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)))
put(bg,1312,'Pide el tuyo hoy',F,(240,200,120,255)); put(bg,1434,'De nuestra finca a tu taza',f2,(255,244,224,255))
bg.convert('RGB').save('work/img/11_cierre.jpg',quality=95)
