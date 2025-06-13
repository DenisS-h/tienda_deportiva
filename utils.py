from PIL import Image
import os

def resize_image(image_path, output_path, size=(400, 300)):
    with Image.open(image_path) as img:
        img.thumbnail(size)
        img.save(output_path, optimize=True, quality=85)