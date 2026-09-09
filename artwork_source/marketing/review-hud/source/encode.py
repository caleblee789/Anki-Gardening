from pathlib import Path
import sys,subprocess,json
sys.path.insert(0,'/private/tmp/anki-garden-hud-runtime')
import imageio_ffmpeg

root=Path('/Users/test/Documents/Anki Gardening.nosync/artwork_source/marketing/review-hud')
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
source='/private/tmp/anki-garden-hud-frames/%04d.png'
variant=sys.argv[1] if len(sys.argv)>1 else 'web'
common=[ffmpeg,'-hide_banner','-loglevel','error','-y','-framerate','20','-i',source]
if variant=='mp4':
    dest=root/'anki-garden-review-hud-hd.mp4'
    subprocess.run(common+['-c:v','libx264','-preset','medium','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart','-an',str(dest)],check=True)
else:
    width=960 if variant=='web' else 1080
    palette=Path('/private/tmp/anki-garden-hud-frames')/f'palette-{variant}.png'
    dest=root/('anki-garden-review-hud.gif' if variant=='web' else 'anki-garden-review-hud-hd.gif')
    scale=f'scale={width}:-2:flags=lanczos'
    subprocess.run(common+['-vf',scale+',palettegen=stats_mode=full:reserve_transparent=1','-frames:v','1',str(palette)],check=True)
    subprocess.run(common+['-i',str(palette),'-filter_complex',f'[0:v]{scale}[v];[v][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle','-loop','0',str(dest)],check=True)
print(json.dumps({'variant':variant,'path':str(dest),'bytes':dest.stat().st_size}))
