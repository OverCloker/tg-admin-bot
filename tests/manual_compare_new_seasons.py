"""Build normalized visual-QA pairs, without modifying production image assets."""
import sys
from pathlib import Path
from PIL import Image


def compare(source_path, capture_path, output_path):
    source = Image.open(source_path).convert('RGB').resize((390, 844), Image.Resampling.LANCZOS)
    capture = Image.open(capture_path).convert('RGB').resize((390, 844), Image.Resampling.LANCZOS)
    pair = Image.new('RGB', (796, 844), '#ddd')
    pair.paste(source, (0, 0))
    pair.paste(capture, (406, 0))
    pair.save(output_path)
    crop = (12, 345, 378, 570)
    focused = Image.new('RGB', (744, 225), '#ddd')
    focused.paste(source.crop(crop), (0, 0))
    focused.paste(capture.crop(crop), (378, 0))
    focused.resize((1488, 450), Image.Resampling.LANCZOS).save(Path(output_path).with_name(Path(output_path).stem + '-services.png'))


if __name__ == '__main__':
    compare(*sys.argv[1:])
