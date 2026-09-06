"""Export only Lavender runtimes and prepare an asset-ID-keyed integration handoff."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/"ankigarden").is_dir())
OUT=ROOT/"build/lavender-redesign/20260905-190634"
SNAPSHOT=OUT/"source-snapshot"
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP","1")
sys.path.insert(0,str(SNAPSHOT))
from ankigarden.asset_manager import AssetPlacement
from ankigarden.ui.plant_display import plant_layout, plant_layout_item

STAGES=("seed","sprout","young","mature","flowering","rare")
TARGET_WIDTHS=dict(zip(STAGES,(32,48,78,104,132,140)))
sha=lambda b:hashlib.sha256(b).hexdigest()
def rect(b):
    x,y,r,bottom=b
    return [round(x/1254,8),round(y/1254,8),round((r-x)/1254,8),round((bottom-y)/1254,8)]

def main():
    previous=json.loads((OUT/"prior-lavender-entries.json").read_text())
    snapshot_manifest=SNAPSHOT/"ankigarden/assets/manifest.json"
    frozen=json.loads(snapshot_manifest.read_text())
    bg=next(a for a in frozen["assets"] if a["asset_id"]=="bg_verdant_twilight_any_soil_master_v6")
    bgp=AssetPlacement.from_manifest(bg["placement"],category="backgrounds").to_dict()
    rows={}; records={}
    for stage in STAGES:
        asset_id=f"plant_lavender_{stage}_twilight_v6"
        row=copy.deepcopy(previous[asset_id]["entry"])
        source=HERE/f"lavender_{stage}_alpha.png"
        with Image.open(source) as opened:
            im=opened.convert("RGBA")
        a=im.getchannel("A")
        visible=a.point(lambda v:255 if v>=16 else 0).getbbox()
        body=a.point(lambda v:255 if v>=192 else 0).getbbox()
        if not visible or not body: raise ValueError(stage)
        # Measure the actual authored root/seed underside, not the canvas centre.
        bottom=body[3]
        contact_band=a.crop((0,max(0,bottom-3),1254,bottom)).point(lambda v:255 if v>=192 else 0)
        contact_bounds=contact_band.getbbox()
        ax=(contact_bounds[0]+contact_bounds[2]-1)/2/1254
        ay=(bottom-1)/1254
        base_height=min(30,max(12,round((body[3]-body[1])*.055)))
        base_band=a.crop((0,bottom-base_height,1254,bottom)).point(lambda v:255 if v>=192 else 0).getbbox()
        base=(base_band[0],bottom-base_height+base_band[1],base_band[2],bottom)
        p=row["placement"]
        center=[(body[0]+body[2])/2/1254,(body[1]+body[3])/2/1254]
        p.update({"anchor_x":ax,"baseline_y":ay,"ground_anchor":[ax,ay],
                  "ground_anchor_x":ax,"ground_anchor_y":ay,"soil_contact":[ax,ay],
                  "art_bounds":rect(body),"visible_bounds":rect(visible),
                  "foliage_bounds":rect(visible),"plant_above_rim_bounds":rect(visible),
                  "interaction_bounds":rect(body),"base_bounds":rect(base),"support_bounds":rect(base),
                  "visual_center":center,"thumbnail_bounds":rect(visible),
                  "thumbnail_optical_center":center,"thumbnail_safe_padding":.08,
                  "shadow_offset":[0.,0.],"contact_shadow":[.78,.07],
                  "review_provenance":"lavender-redesign-20260905-v1",
                  "visual_scale_correction":1.0})
        p.pop("thumbnail_scale",None)
        row["source_master_file"]=source.relative_to(ROOT).as_posix()
        row["source_master_sha256"]=sha(source.read_bytes())
        row["source"]="Built-in ImageGen Lavender redraw; approved background/alpha cleanup; full prompt lineage beside native-alpha master"
        def layout():
            item={"plant_id":"lavender-calibration","slot_index":0,"species":"lavender",
                  "stage":stage,"placement":AssetPlacement.from_manifest(p,category="plants").to_dict(),"canvas_aspect":1.0}
            items=[plant_layout_item(item,0)]+[plant_layout_item({},i) for i in range(1,6)]
            return plant_layout(1260,840,items,bgp,composition_count=1,protected_status=False)[0]
        baseline=layout()
        p["visual_scale_correction"]=TARGET_WIDTHS[stage]/baseline.visible.width
        measured=layout()
        if not .5<=p["visual_scale_correction"]<=1.5: raise ValueError((stage,p["visual_scale_correction"]))
        if abs(measured.visible.width-TARGET_WIDTHS[stage])>.5: raise ValueError((stage,measured.visible.width))
        target=ROOT/"ankigarden"/row["file"]
        # Refuse to overwrite somebody else's change to the species lane.
        oldhash=sha(target.read_bytes())
        accepted={previous[asset_id]["runtime_sha256"]}
        old_export=OUT/"runtime-validation.json"
        if old_export.exists():
            accepted.add(json.loads(old_export.read_text())["stages"][stage]["runtime_sha256"])
        if oldhash not in accepted: raise ValueError(f"Concurrent Lavender runtime change: {target}")
        im.save(target,"WEBP",lossless=True,method=6,exact=True)
        with Image.open(target) as loaded:
            encoded=loaded.convert("RGBA")
            if im.getchannel("A").tobytes()!=encoded.getchannel("A").tobytes(): raise ValueError("alpha changed")
            for src,dst in zip(im.getdata(),encoded.getdata()):
                if src[3] and src!=dst: raise ValueError("visible color changed")
        snapshot_file=SNAPSHOT/"ankigarden"/row["file"]
        snapshot_file.write_bytes(target.read_bytes())
        rows[asset_id]=row
        records[stage]={"asset_id":asset_id,"runtime_file":row["file"],
                        "runtime_sha256":sha(target.read_bytes()),"source_file":row["source_master_file"],
                        "source_sha256":row["source_master_sha256"],"alpha_color_parity":True,
                        "visible_size":[measured.visible.width,measured.visible.height],
                        "source_ground_anchor":[ax,ay],"warnings":list(measured.validation_warnings)}
    for i,row in enumerate(frozen["assets"]):
        if row["asset_id"] in rows: frozen["assets"][i]=rows[row["asset_id"]]
    snapshot_manifest.write_text(json.dumps(frozen,indent=2)+"\n")
    payload={"schema_version":1,"species":"lavender","shared_file_owner":"Coordinate plant species agents",
             "prior_entry_hash_encoding":"sha256(sorted-key compact JSON UTF-8)",
             "entries":{aid:{"prior_entry_sha256":previous[aid]["entry_sha256"],"replacement":row} for aid,row in rows.items()},
             "installer_handoff":{"source_file_overrides":{stage:f"redesign-20260905-v1/lavender_{stage}_alpha.png" for stage in STAGES},
                                  "species_visual_scale":{stage:rows[f"plant_lavender_{stage}_twilight_v6"]["placement"]["visual_scale_correction"] for stage in STAGES},
                                  "placement_overrides_by_asset_id":{aid:row["placement"] for aid,row in rows.items()}},
             "compatibility_sources":"Existing unversioned Lavender *_chroma.png sources are preserved; actual new source provenance points to versioned alpha masters."}
    (HERE/"integration-handoff.json").write_text(json.dumps(payload,indent=2)+"\n")
    (OUT/"runtime-validation.json").write_text(json.dumps({"stages":records},indent=2)+"\n")
    print(json.dumps({s:r["visible_size"] for s,r in records.items()},indent=2))
if __name__=="__main__":main()
