from pathlib import Path
import os, sys, types, json, math, time, hashlib, zipfile, io
from dataclasses import replace
from types import SimpleNamespace

ROOT = Path('/Users/test/Documents/Anki Gardening.nosync')
OUT = ROOT / 'artwork_source/marketing/review-hud'
PACKAGE = ROOT / 'dist/anki_garden.ankiaddon'
package_bytes = PACKAGE.read_bytes()
package_sha256 = hashlib.sha256(package_bytes).hexdigest()
package_base = Path('/private/tmp/anki-garden-hud-packages') / package_sha256
package_code = package_base / 'ankigarden'
with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
    for entry in archive.infolist():
        relative = Path(entry.filename)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid package entry: ' + entry.filename)
        if entry.is_dir():
            continue
        target = package_code / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(entry))
package_manifest = json.loads((package_code / 'manifest.json').read_text())
(OUT/'source/package-source.json').write_text(json.dumps({
    'archive': str(PACKAGE), 'sha256': package_sha256,
    'version': package_manifest['human_version'],
    'runtime_source': str(package_code),
    'hud_module_sha256': hashlib.sha256((package_code/'ui/reviewer_hud_widget.py').read_bytes()).hexdigest()
}, indent=2)+'\n')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_SCALE_FACTOR'] = '3'
os.environ['ANKI_GARDEN_SKIP_STARTUP'] = '1'
sys.path[:0] = ['/private/tmp/anki-garden-hud-runtime', str(package_base)]

from PyQt6 import QtCore, QtGui, QtWidgets, QtSvg
from PyQt6.QtTest import QTest
aqt = types.ModuleType('aqt')
qt = types.ModuleType('aqt.qt')
for module in (QtCore, QtGui, QtWidgets, QtSvg):
    for name in dir(module):
        if not name.startswith('_'):
            setattr(qt, name, getattr(module, name))
aqt.qt = qt
sys.modules['aqt'] = aqt
sys.modules['aqt.qt'] = qt

from aqt.qt import *
from ankigarden.ui.reviewer_hud import ReviewerHudProjection, TodayCardsProjection, NurtureProjection
from ankigarden.ui.reviewer_hud_widget import ReviewGardenHud
from ankigarden.reward_presentation import RewardBundleProjection, RewardHero, RewardItemProjection

app = QApplication([])
app.setStyle('Fusion')
base_font=QFont('Helvetica Neue'); base_font.setPixelSize(13); app.setFont(base_font)
palette=app.palette()
for role,color in [(QPalette.ColorRole.Window,'#292929'),(QPalette.ColorRole.Base,'#0b2119'),(QPalette.ColorRole.Button,'#233b31'),(QPalette.ColorRole.Text,'#f4f5e9'),(QPalette.ColorRole.WindowText,'#f4f5e9'),(QPalette.ColorRole.ButtonText,'#f4f5e9'),(QPalette.ColorRole.Highlight,'#57d4a4')]:
    palette.setColor(role,QColor(color))
app.setPalette(palette)
review_capture = QImage(str(ROOT/'build/ui-face-captures/full/capture-sequence-20260908-012834/assembled/49-workspace-reviewer-collapsed.png'))
nav_capture = review_capture.copy(1335, 0, 750, 66)
edit_capture = review_capture.copy(0, 1994, 210, 72)
more_capture = review_capture.copy(3210, 1994, 210, 72)
cards = [('What do roots absorb?', 'Water and minerals.'),
         ('What gives leaves their green color?', 'Chlorophyll.'),
         ('What carries water through a plant?', 'Xylem.'),
         ('What do seeds need to germinate?', 'Water, oxygen, and warmth.')]
class ReviewViewport(QWidget):
    card_index=0
    answer_visible=False
    def paintEvent(self, event):
        super().paintEvent(event)
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#2b2b2b'))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(self.width()/2-187.5,0,375,33),nav_capture)
        f=QFont('Helvetica Neue');f.setPixelSize(13);f.setWeight(QFont.Weight.DemiBold);p.setFont(f)
        p.setPen(QColor('#eeeeed'))
        f.setPixelSize(20);f.setWeight(QFont.Weight.Normal);p.setFont(f);p.setPen(QColor('#eeefed'))
        question,answer=cards[self.card_index%len(cards)]
        p.drawText(QRectF(self.width()/2-310,70,620,40),Qt.AlignmentFlag.AlignCenter,question)
        if self.answer_visible:
            p.setPen(QColor('#606060'));p.drawLine(self.width()//2-280,128,self.width()//2+280,128)
            p.setPen(QColor('#eeefed'));p.drawText(QRectF(self.width()/2-310,145,620,40),Qt.AlignmentFlag.AlignCenter,answer)
        p.setPen(QColor('#242424'));p.drawLine(0,self.height()-55,self.width(),self.height()-55)
        p.drawImage(QRectF(0,self.height()-44,105,36),edit_capture)
        p.drawImage(QRectF(self.width()-105,self.height()-44,105,36),more_capture)
        f.setPixelSize(12);p.setFont(f)
        buttons=[(self.width()/2-62,124,'Show Answer','')]
        if self.answer_visible:
            buttons=[(self.width()/2-176,80,'Again','<1m'),(self.width()/2-88,80,'Hard','<6m'),(self.width()/2,80,'Good','<10m'),(self.width()/2+88,80,'Easy','4d')]
        else:
            p.setPen(QColor('#a4cff1'));p.drawText(QRectF(self.width()/2-55,self.height()-51,110,20),Qt.AlignmentFlag.AlignCenter,f'{18-self.card_index} + 0 + 0')
        for x,w,label,interval in buttons:
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#5d5d5d'));p.drawRoundedRect(QRectF(x,self.height()-30,w,22),11,11)
            p.setPen(QColor('#eeeeed'));p.drawText(QRectF(x,self.height()-30,w,22),Qt.AlignmentFlag.AlignCenter,label)
            if interval:
                p.setPen(QColor('#d3d3d3'));p.drawText(QRectF(x,self.height()-49,w,18),Qt.AlignmentFlag.AlignCenter,interval)
        p.end()

host = ReviewViewport()
host.resize(review_capture.width()//2, review_capture.height()//2)
host.setObjectName('promoReviewViewport')
host.setStyleSheet('QWidget#promoReviewViewport { background: #292929; }')
host.show()
art = ROOT / 'artwork_source/plants/v6/bonsai/redesign_20260905/alpha/bonsai_sprout_alpha_v1.png'
runtime = package_code / 'assets/v6_storybook_gouache'

def resolve(item):
    identity = str(getattr(item, 'artwork_ref', '') or '')
    if Path(identity).is_file():
        return QPixmap(identity)
    aliases = {'prism_trellis': ROOT/'artwork_source/garden_features/masters/prism_trellis.png',
               'firefly_lantern': ROOT/'artwork_source/garden_features/masters/firefly_lantern.png',
               'ui_growth_charge_standard': runtime/'ui/growth_charge_standard.webp'}
    path = aliases.get(identity)
    return QPixmap(str(path)) if path and path.is_file() else None

nurture = NurtureProjection(True, plant_id='bonsai', plant_name='Bonsai Sprout', species_name='Bonsai',
    stage_key='sprout', next_stage_key='young', stage_points=850, stage_goal=1600,
    progress_percent=53, next_answer_growth_units=1700, art_path=str(art))
projection = ReviewerHudProjection(248, TodayCardsProjection('in_progress', 'Today’s cards', '24 / 42', (), 24,42),
    nurture, False, 'right')
hud = ReviewGardenHud(host, animations_enabled=True, resolve_reward_art=resolve)
hud.update_projection(projection)

def bundle(identity,kind=RewardHero.ROUTINE_GROWTH,title='Growth earned',units=0,coins=0,rarity='',ref=''):
    item=RewardItemProjection(event_id=identity,kind=kind,title=title,category_label='Growth' if kind==RewardHero.ROUTINE_GROWTH else 'Garden Find',growth_units=units,garden_coins=coins,rarity=rarity,artwork_ref=ref)
    return RewardBundleProjection(identity,'2026-09-09T12:00:00Z',(item,),displayed_coin_delta=coins)

history=[bundle('earlier-growth-1',units=1600),
         bundle('earlier-coin-pouch',RewardHero.GARDEN_FIND,'Coin Pouch',coins=12,rarity='Common'),
         bundle('earlier-growth-2',units=2000),
         bundle('earlier-lantern',RewardHero.ENVIRONMENT_DISCOVERY,'Firefly Lantern',rarity='rare',ref='firefly_lantern'),
         bundle('earlier-growth-3',units=5000)]
for b in history: hud.present_committed_result(b,reveal=False)
totals={'growth':8600,'coins':12,'finds':2,'points':850,'balance':248}
def update_totals():
    hud.update_session_totals(SimpleNamespace(footer_growth_units=totals['growth'],footer_coin_count=totals['coins'],footer_find_count=totals['finds'],environment_discoveries=()))
update_totals()
hud.set_collapsed(True)
hud._position=hud._position_at(1613,79);hud.reposition()
QTest.qWait(950)

def growth(identity,amount,coins=0):
    global projection
    totals['growth']+=amount*100;totals['points']+=amount;totals['coins']+=coins;totals['balance']+=coins
    projection=replace(projection,coins=totals['balance'],collapsed=hud._collapsed,position=hud._position,
        nurture=replace(nurture,stage_points=totals['points'],progress_percent=round(totals['points']*100/1600)))
    hud.update_projection(projection,animate=True)
    hud.present_committed_result(bundle(identity,units=amount*100,coins=coins),applied_growth_units=amount*100)
    update_totals()

def discover():
    totals['finds']+=1
    hud.present_committed_result(bundle('new-prism',RewardHero.ENVIRONMENT_DISCOVERY,'Prism Trellis',rarity='very_rare',ref='prism_trellis'))
    update_totals()

def rare_find():
    totals['finds']+=1
    hud.present_committed_result(bundle('new-lantern',RewardHero.ENVIRONMENT_DISCOVERY,'Firefly Lantern',rarity='rare',ref='firefly_lantern'))
    update_totals()

def reveal_answer():
    global cursor
    host.answer_visible=True;host.update()
    cursor=QPointF(host.width()/2,host.height()-20)

def commit(action):
    global cursor
    cursor=QPointF(host.width()/2+40,host.height()-20)
    action()
    host.card_index+=1;host.answer_visible=False;host.update()

def coin_find():
    global projection
    totals['finds']+=1;totals['coins']+=15;totals['balance']+=15
    projection=replace(projection,coins=totals['balance'],collapsed=hud._collapsed,position=hud._position)
    hud.update_projection(projection,animate=True)
    hud.present_committed_result(bundle('coin-cache',RewardHero.GARDEN_FIND,'Coin Cache',coins=15,rarity='Rare'))
    update_totals()

cursor=QPointF(1588,183);drag=None
def mouse_event(target,kind,global_pos,button,buttons):
    local=target.mapFromGlobal(global_pos.toPoint())
    event=QMouseEvent(kind,QPointF(local),global_pos,button,buttons,Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target,event)

def drag_begin():
    global drag,cursor
    target=hud._collapsed_tab if hud._collapsed else hud._header
    local=QPointF(18,12) if hud._collapsed else QPointF(80,20)
    point=QPointF(target.mapToGlobal(local.toPoint()))
    drag=(target,point,QPointF(hud.pos()),QPointF(target.mapTo(host,local.toPoint())))
    cursor=QPointF(drag[3]);mouse_event(target,QEvent.Type.MouseButtonPress,point,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)

def drag_move(dx,dy):
    global cursor
    if drag is None:return
    target,start,origin,local=drag
    cursor=local+QPointF(dx,dy)
    mouse_event(target,QEvent.Type.MouseMove,start+QPointF(dx,dy),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)

def drag_end():
    global drag
    if drag is not None:
        target,start,origin,local=drag
        end=QPointF(host.mapToGlobal(cursor.toPoint()))
        mouse_event(target,QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    drag=None

def expand():
    global cursor
    cursor=QPointF(hud._collapsed_tab.mapTo(host,QPoint(18,12)))
    QTest.mouseClick(hud._collapsed_tab,Qt.MouseButton.LeftButton,pos=QPoint(18,12))

def collapse():
    global cursor
    cursor=QPointF(hud._collapse_button.mapTo(host,hud._collapse_button.rect().center()))
    QTest.mouseClick(hud._collapse_button,Qt.MouseButton.LeftButton)

def smooth(v):
    v=max(0.,min(1.,v));return v*v*(3-2*v)

W,H=1140,694
pane=QRectF(0,0,W,H)
cover=QImage(W,H,QImage.Format.Format_RGB32)
cover.fill(QColor('#2b2b2b'))

def camera_view(t):
    # The Anki window stays at 1710 x 1041 throughout. Only this camera crop
    # changes: every captured pixel, including the HUD, shares one transform.
    wide_height=host.width()*pane.height()/pane.width()
    wide=QRectF(0,(host.height()-wide_height)/2,host.width(),wide_height)
    compact=QRectF(1240,0,270*pane.width()/pane.height(),270)
    expanded_height=max(620,hud.height()+64)
    expanded_width=expanded_height*pane.width()/pane.height()
    expanded=QRectF(max(0,min(host.width()-expanded_width,hud.x()-expanded_width*.60)),
        max(0,min(host.height()-expanded_height,hud.y()-64)),expanded_width,expanded_height)
    target=compact if t<6.2 else expanded
    if t<5.6:z=smooth((t-2.)/.6)
    elif t<6.2:z=1-smooth((t-5.6)/.6)
    elif t<12.8:z=smooth((t-7.4)/.6)
    else:z=1-smooth((t-12.8)/.6)
    return QRectF(*[a+(b-a)*z for a,b in zip(
        (wide.x(),wide.y(),wide.width(),wide.height()),
        (target.x(),target.y(),target.width(),target.height()))])

def pointer_opacity(t):
    # A small, quiet pointer appears only for dragging, toggling and scrolling.
    for start,end in ((.28,1.98),(6.02,7.50),(10.82,12.76),(13.34,14.34)):
        if start<=t<=end:
            return .8*min(smooth((t-start)/.12),smooth((end-t)/.12))
    return 0.

def render(t):
    # Capture the complete native scene, including its shadows and animations.
    # The pointer is painted in that same logical coordinate system first.
    screen=host.grab().toImage()
    pointer=QPainter(screen);pointer.setRenderHint(QPainter.RenderHint.Antialiasing)
    opacity=pointer_opacity(t)
    if opacity:
        cx,cy=cursor.x(),cursor.y()
        pointer.setOpacity(opacity);pointer.translate(cx,cy);pointer.scale(.6,.6)
        pointer.setPen(QPen(QColor('#151b18'),1.3));pointer.setBrush(QColor('#d2d6d4'))
        pointer.drawPolygon(QPolygonF([QPointF(0,0),QPointF(0,23),QPointF(6,18),QPointF(11,28),QPointF(16,25),QPointF(11,15),QPointF(21,15)]))
    pointer.end();screen.setDevicePixelRatio(1)
    source=camera_view(t);factor=pane.width()/source.width()
    destination=QRectF(pane.x()-source.x()*factor,pane.y()-source.y()*factor,host.width()*factor,host.height()*factor)
    image=cover.copy();p=QPainter(image)
    p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
    p.setClipRect(pane)
    p.drawImage(destination,screen)
    p.end();return image

events={8:drag_begin,38:drag_end,56:lambda:commit(lambda:growth('card-1',17)),70:lambda:commit(lambda:growth('card-2',25)),
        84:lambda:commit(rare_find),124:expand,127:drag_begin,148:drag_end,
        162:lambda:commit(lambda:growth('card-3',28,4)),178:lambda:commit(discover),
        202:lambda:commit(lambda:growth('card-4',32,3)),212:lambda:commit(coin_find),
        270:collapse,273:drag_begin,286:drag_end}
for index in (50,64,78,156,172,196,206):events[index]=reveal_answer
frames=Path('/private/tmp/anki-garden-hud-frames');records=[]
first=None
for i in range(294):
    started=time.monotonic();t=i/20
    if i in events:events[i]()
    if 8<=i<=37:
        if i<=23:
            v=smooth((i-8)/15);drag_move(-350*v,170*v)
        else:
            v=smooth((i-23)/14);drag_move(-350+160*v,170-195*v)
    if 127<=i<=147:
        if i<=137:
            v=smooth((i-127)/10);drag_move(-244*v,-10*v)
        else:
            v=smooth((i-137)/10);drag_move(-244+270*v,-10+5*v)
    if 273<=i<=285:
        v=smooth((i-273)/12);drag_move(164*v,30*v)
    if 218<=i<=252:
        bar=hud._reward_feed.view.verticalScrollBar()
        v=smooth((i-218)/17) if i<235 else 1-smooth((i-235)/17)
        bar.setValue(round(bar.maximum()*v))
        cursor=QPointF(hud._reward_feed.mapTo(host,QPoint(hud._reward_feed.width()-24,max(30,hud._reward_feed.height()//2))))
    if i in (60,74,88,166,182,216,253):cursor=QPointF(hud.x()+hud.width()+24,hud.y()+hud.height()*.68)
    if i>=287:cursor=QPointF(1588,183)
    QTest.qWait(max(1,round(50-(time.monotonic()-started)*1000)))
    # Sample the native status exchange after its brief crossfade, so two
    # overlapping numbers do not survive as a compressed GIF frame.
    feedback=hud._collapsed_feedback
    if hud._collapsed and feedback._motion is not None:
        feedback._motion.setCurrentTime(feedback._motion.duration())
    frame=render(t)
    if first is None:first=frame.copy()
    if i>=288:
        p=QPainter(frame);p.setOpacity(smooth((i-288)/5));p.drawImage(0,0,first);p.end()
    frame.save(str(frames/f'{i:04}.png'),'PNG',100)
    records.append({'frame':i,'seconds':t,'collapsed':hud._collapsed,'hud':[hud.x(),hud.y(),hud.width(),hud.height()],
        'growth':totals['growth'],'plant_growth':totals['points'],'scroll':hud._reward_feed.view.verticalScrollBar().value(),
        'scroll_max':hud._reward_feed.view.verticalScrollBar().maximum(),
        'card_index':host.card_index,'answer_visible':host.answer_visible,
        'reward_pulse':bool(hud.property('rewardPulseActive')),
        'window_logical_size':[host.width(),host.height()],
        'camera_crop':[camera_view(t).x(),camera_view(t).y(),camera_view(t).width(),camera_view(t).height()],
        'uniform_scene_scale':pane.width()/camera_view(t).width(),
        'pointer_opacity':pointer_opacity(t),
        'stage_progress_text':hud._percent.text()})
    if i<40:
        records[-1]['opening_window_logical_size']=[review_capture.width()/2,review_capture.height()/2]
        records[-1]['opening_hud_width_fraction']=hud.width()/(review_capture.width()/2)
    if i in (10,25,56,72,88,100,137,164,182,190,224,236,276):
        frame.save(str(OUT/'source'/f'keyframe-{i:03}.png'))
    if i==190:frame.save(str(OUT/'anki-garden-review-hud-poster.png'))
print(json.dumps({'frames':len(records),'seconds':len(records)/20,'dimensions':[W,H],'dpr':hud.devicePixelRatioF(),
    'growth_start':records[0]['growth'],'growth_end':records[-1]['growth'],'scroll_max':max(r['scroll'] for r in records)}))
(OUT/'source/frame-records.json').write_text(json.dumps(records,indent=2))
hud.dispose()
host.close()
