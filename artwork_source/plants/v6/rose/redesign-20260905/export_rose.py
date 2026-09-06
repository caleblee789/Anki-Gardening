"""Reproducible Rose-only matte export; never rewrites the shared manifest."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
from PIL import Image, ImageFilter
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "scripts"))
import process_direct_soil_asset as matte
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SOURCE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
# The built-in generator returned RGB rather than the requested true alpha.
# Cyan is far from the authored botanical/petal colors. Expand only the
# boundary RGB despill predicate; the existing extractor owns the alpha.
original_spill = matte._is_boundary_chroma_spill
def cyan_boundary(pixel):
    r,g,b,a = pixel
    return original_spill(pixel) or (a >= 16 and g > 130 and b > 130
        and r < 0.65 * min(g,b) and abs(g-b) < 75)
matte._is_boundary_chroma_spill = cyan_boundary
reports = []
for stage in STAGES:
    source = SOURCE / f"rose_{stage}_cyan.png"
    raw = OUT / f"rose_{stage}_raw_alpha.png"
    matte.remove_connected_chroma(source, raw, transparent_threshold=45,
        connection_threshold=75)
    im = Image.open(raw).convert("RGBA")
    source_rgb = Image.open(source).convert("RGB")
    key = matte._border_key(source_rgb.convert("RGBA"))
    # Verify all source-interior pixels well away from the technical key.
    core = Image.frombytes("L", im.size, bytes(
        255 if sum((c-k)**2 for c,k in zip(pixel,key)) > 125**2 else 0
        for pixel in source_rgb.getdata())).filter(ImageFilter.MinFilter(7))
    samples = lost = changed = 0
    for src, dst, yes in zip(source_rgb.getdata(), im.getdata(), core.getdata()):
        if yes:
            samples += 1
            lost += dst[3] != 255
            changed += tuple(src) != tuple(dst[:3])
    if lost or changed:
        raise ValueError(f"{stage}: interior changed: {lost} alpha, {changed} RGB")
    alpha = im.getchannel("A")
    bounds = alpha.point(lambda a: 255 if a >= 192 else 0).getbbox()
    all_bounds = alpha.getbbox()
    if bounds is None or all_bounds is None: raise ValueError(stage)
    ground_y = bounds[3] - 1
    root_xs = [x for y in range(max(bounds[1], ground_y-3), ground_y+1)
        for x in range(bounds[0],bounds[2]) if alpha.getpixel((x,y)) >= 192]
    ground_x = (min(root_xs) + max(root_xs)) / 2
    left,top,right,bottom = all_bounds
    factor = min(1.0, 1129/max(1,ground_y-top),
        577/max(1,ground_x-left), 577/max(1,right-ground_x))
    crop = im.crop(all_bounds)
    if factor < 1:
        crop = crop.resize((round(crop.width*factor),round(crop.height*factor)),
            Image.Resampling.LANCZOS)
    dest_x = round(627 - (ground_x-left)*factor)
    dest_y = round(1179 - (ground_y-top)*factor)
    normalized = Image.new("RGBA",(1254,1254),(0,0,0,0))
    normalized.alpha_composite(crop,(dest_x,dest_y))
    normalized.putdata([pixel if pixel[3] else (0,0,0,0)
        for pixel in normalized.getdata()])
    master = SOURCE / f"rose_{stage}_rgba.png"
    runtime = OUT / f"rose_{stage}_twilight_v6.webp"
    normalized.save(master,"PNG",optimize=True)
    normalized.save(runtime,"WEBP",lossless=True,quality=100,method=6,exact=True)
    decoded = Image.open(runtime).convert("RGBA")
    if decoded.tobytes() != normalized.tobytes(): raise ValueError("WebP pixel mismatch")
    a = decoded.getchannel("A")
    reports.append({"stage":stage,"source":str(source.relative_to(ROOT)),
        "source_sha256":sha(source),"normalized_master":str(master.relative_to(ROOT)),
        "master_sha256":sha(master),"runtime":str(runtime),"runtime_sha256":sha(runtime),
        "source_interior_samples":samples,"changed_interior_alpha":lost,
        "changed_interior_rgb":changed,"normalization_scale":factor,
        "ground_anchor":[627/1254,1179/1254],"alpha_bounds":a.getbbox(),
        "confident_bounds":a.point(lambda x:255 if x>=192 else 0).getbbox(),
        "pixel_lossless":True})
    print("Exported",stage,flush=True)
(OUT/"export-report.json").write_text(json.dumps(reports,indent=2)+"\n")

