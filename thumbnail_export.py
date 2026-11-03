"""High-quality Full HD export with a conservative upload byte budget."""
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps

SIZE=(1920,1080)
MAX_BYTES=2_000_000


def export_thumbnail(source,target):
    with Image.open(source) as image:
        image=ImageOps.fit(ImageOps.exif_transpose(image).convert('RGB'),SIZE,
                           method=Image.Resampling.LANCZOS)
    for quality in (95,92,88,84,80,76,70,64,56,48,40):
        buffer=BytesIO()
        image.save(buffer,format='JPEG',quality=quality,subsampling=0,
                   optimize=False,progressive=False)
        data=buffer.getvalue()
        if len(data)<=MAX_BYTES:
            target=Path(target)
            temporary=target.with_suffix('.tmp.jpg')
            temporary.write_bytes(data)
            temporary.replace(target)
            return dict(width=SIZE[0],height=SIZE[1],bytes=len(data),quality=quality)
    raise ValueError('Full HD thumbnail exceeds export byte budget even after compression')
