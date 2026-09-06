"""Authorized technical alpha cleanup and square-canvas export; no creative painting."""
import argparse,json,sys,shutil,hashlib
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[5]
RUN=ROOT/"build/sunflower-redesign/20260905-190549"
SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from scripts.process_direct_soil_asset import remove_connected_chroma
import scripts.process_direct_soil_asset as cleanup

# The generated matte is neutral gray/white rather than magenta. Extend the
# existing edge-only despill predicate locally; never change shared tools.
original_spill_predicate=cleanup._is_boundary_chroma_spill
def neutral_matte_spill(pixel):
 r,g,b,a=pixel
 return original_spill_predicate(pixel) or (a>=16 and min(r,g,b)>170 and max(r,g,b)-min(r,g,b)<35) or (stage=='seed' and a>=16 and min(r,g,b)>140 and max(r,g,b)-min(r,g,b)<75)
records=json.loads((RUN/"final-generation-record.json").read_text())
parser=argparse.ArgumentParser()
parser.add_argument('--stage')
args=parser.parse_args()
result=json.loads((RUN/'asset-production.json').read_text()) if args.stage else {}
for stage,path in records["selected_raw_sources"].items():
 if args.stage and stage!=args.stage:continue
 stem=records.get('stage_file_stems',{}).get(stage,f'sunflower_{stage}')
 raw=SOURCE/f"{stem}_generated.png"
 if not raw.is_file():
  shutil.copy2(path,raw)
 alpha_path=SOURCE/f"{stem}_extracted.png"
 remove_connected_chroma(raw,alpha_path,transparent_threshold=35,connection_threshold=65,include_enclosed_chroma=stage!='seed')
 image=Image.open(alpha_path).convert("RGBA")
 original_alpha=image.getchannel('A').tobytes()
 cleanup._is_boundary_chroma_spill=neutral_matte_spill
 image,edge_pixels=cleanup._despill_transparency_boundary(image,boundary_radius=3,replacement_radius=12)
 cleanup._is_boundary_chroma_spill=original_spill_predicate
 assert image.getchannel('A').tobytes()==original_alpha
 alpha=image.getchannel("A"); bbox=alpha.getbbox()
 confident=alpha.point(lambda a:255 if a>=192 else 0)
 cb=confident.getbbox()
 contact_rows=40 if stage=='seed' else 4
 band=confident.crop((0,cb[3]-contact_rows,image.width,cb[3]))
 contact_bounds=band.getbbox()
 cx=(contact_bounds[0]+contact_bounds[2]-1)/2
 cy=cb[3]-1
 n=1254; ground=1178
 extent=max(cx-bbox[0],bbox[2]-cx)
 scale=min(1.,(n/2-64)/extent,(ground-64)/(cy-bbox[1]))
 scaled=image.convert("RGBa").resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS).convert("RGBA")
 offset=(round(n/2-cx*scale),round(ground-cy*scale))
 out=Image.new("RGBA",(n,n),(0,0,0,0))
 out.alpha_composite(scaled,offset)
 master=SOURCE/f"{stem}_alpha.png"
 out.save(master,optimize=True)
 runtime=RUN/"candidate-assets"/stage/f"sunflower_{stage}_twilight_v6.webp"
 runtime.parent.mkdir(parents=True,exist_ok=True);out.save(runtime,"WEBP",lossless=True,quality=100,method=6,exact=True)
 result[stage]={"raw":str(raw),"extracted":str(alpha_path),"alpha_master":str(master),"runtime":str(runtime),
 "normalization":{"scale":scale,"offset":offset,"contact":[.5,ground/n]},"alpha_bbox":out.getbbox(),"neutral_matte_edge_pixels":edge_pixels,
 "raw_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),"master_sha256":hashlib.sha256(master.read_bytes()).hexdigest(),
 "runtime_sha256":hashlib.sha256(runtime.read_bytes()).hexdigest()}
 print(stage,result[stage]["alpha_bbox"],flush=True)
(RUN/"asset-production.json").write_text(json.dumps(result,indent=2)+"\n")
shutil.copy2(RUN/"final-generation-record.json",SOURCE/"generation-record.json")
