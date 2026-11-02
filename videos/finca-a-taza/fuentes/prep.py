from PIL import Image, ImageOps, ImageFilter, ImageDraw
import os
U='/root/.claude/uploads/6e2180ac-0d8a-591a-91e3-874b0baff01e/'
shots = [  # nombre, archivo, foco x, foco y
 ('01_casa','c6f519a0-image.webp',.64,.5), ('02_jeep','4d538f8d-image.webp',.45,.55),
 ('03_semillero','de87b590-image.webp',.5,.5), ('04_cerezas_rama','9d12a6a1-image.webp',.5,.5),
 ('05_mano_cerezas','fd376e37-image.jpg',.5,.5), ('06_caficultor','af9b7f7f-image.webp',.5,.45),
 ('07_seleccion','c6b64809-image.webp',.5,.3), ('08_zaranda','7c77683e-image.jpg',.5,.5),
 ('10_taza_montanas','e0b0440a-image.webp',.5,.6)]
OW,OH=1440,2560
for name,f,fx,fy in shots:
    im=ImageOps.exif_transpose(Image.open(U+f)).convert('RGB')
    w,h=im.size; r=9/16
    if w/h>r: cw,ch=int(h*r),h
    else: cw,ch=w,int(w/r)
    x=min(max(int(fx*w-cw/2),0),w-cw); y=min(max(int(fy*h-ch/2),0),h-ch)
    im.crop((x,y,x+cw,y+ch)).resize((OW,OH),Image.LANCZOS).save(f'work/img/{name}.jpg',quality=93)
    print(name,(w,h))
# logo: bolsa izquierda de la foto de producto
im=ImageOps.exif_transpose(Image.open(U+'41bb2c72-image.webp')).convert('RGB')
im.crop((30,1460,960,2080)).save('work/img/logo_crop.png'); print('logo',im.size)
