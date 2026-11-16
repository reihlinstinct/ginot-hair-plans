/* Public points only on disk. Boundaries fetched live by the visitor and kept
 * in this page's memory only. One bounded batch per visible selection. */
(function () {
  'use strict';
  var BASE=window.GINOT_BASE||'';
  function S(key,fallback){var o=window.GINOT_I18N||{};return o[key]||fallback;}
  function TF(key,fallback,o){return S(key,fallback).replace(/\{(\w+)\}/g,function(m,k){return o[k];});}
  var panel=document.getElementById('plan-map-panel');if(!panel)return;
  var items=[],drawn=[],pointsDate='',map,loading=false,polygons,controller,revision=0,timer;
  var permitPositions=new Map(),permitMarkers=[],permitLayer;
  var cache=new Map(),failed=new Set(),manual=new Set(),MAX=20,MIN_ZOOM=11;
  var toggle=document.getElementById('map-boundaries');
  var status=document.getElementById('map-status');
  var colors={deposit:'#e8c31d',review:'#007996',conditions:'#c8a4de',decision:'#ff8c00',process:'#387e6a',approved:'#4c7f24',other:'#dde4f6'};
  function category(s){
    if(s.indexOf('הפקדה')!==-1)return 'deposit';
    if(s.indexOf('בדיקה')!==-1)return 'review';
    if(s.indexOf('תנאים')!==-1)return 'conditions';
    if(s.indexOf('הכרעה')!==-1)return 'decision';
    if(s.indexOf('בהליך')!==-1)return 'process';
    if(s.indexOf('אישור')!==-1)return 'approved';return 'other';
  }
  function color(row){return colors[category(row.station_desc||'')];}
  /* Status also reads by shape (WCAG 1.4.1, #971): color alone split
     process/approved into two near-identical dark greens, and decision
     shared the permit marker's square. Inline SVG so every silhouette keeps
     its outline and halo (clip-path clipped both). Seven distinct shapes:
     deposit circle, review diamond, conditions triangle, decision plus,
     process hexagon, approved star, other dashed ring. */
  var SHAPE_SVG={
    deposit:'<circle cx="7" cy="7" r="5"/>',
    review:'<rect x="3.2" y="3.2" width="7.6" height="7.6" transform="rotate(45 7 7)"/>',
    conditions:'<polygon points="7,2 12.5,12 1.5,12"/>',
    decision:'<path d="M5 1h4v4h4v4H9v4H5V9H1V5h4z"/>',
    process:'<polygon points="4,2 10,2 13,7 10,12 4,12 1,7"/>',
    approved:'<polygon points="7,1.2 8.6,5.1 12.7,5.4 9.5,8.2 10.6,12.3 7,10.1 3.4,12.3 4.5,8.2 1.3,5.4 5.4,5.1"/>',
    other:'<circle cx="7" cy="7" r="5" fill="none" stroke-dasharray="2.5,2"/>'
  };
  var SHAPE_CLASS={deposit:'sh-circle',review:'sh-diamond',conditions:'sh-triangle',decision:'sh-plus',process:'sh-hexagon',approved:'sh-star',other:'sh-outline'};
  function markerHtml(cat,colorValue){
    /* Every marker gets the navy outline; 'other' reads as a dashed navy
       ring with its light fill (a near-white stroke alone was invisible on
       map tiles, WCAG 1.4.11). */
    return '<svg class="'+SHAPE_CLASS[cat]+'" viewBox="0 0 14 14" width="14" height="14" aria-hidden="true"><g fill="'+colorValue+'" stroke="#101f5b" stroke-width="1.5">'+SHAPE_SVG[cat]+'</g></svg>';
  }
  function el(tag,text){var e=document.createElement(tag);if(text)e.textContent=text;return e;}
  function link(text,url){var a=el('a',text);a.href=url;a.target='_blank';a.rel='noopener';return a;}
  function asset(tag,attr,url){return new Promise(function(resolve,reject){var e=document.createElement(tag);e[attr]=url;e.onload=resolve;e.onerror=reject;if(tag==='link')e.rel='stylesheet';document.head.appendChild(e);});}
  function rows(){return Array.from(document.querySelectorAll('#plans tbody tr')).filter(function(r){return r.dataset.mapMatch==='1'&&!r.classList.contains('filtered-out')&&r.getClientRects().length>0&&getComputedStyle(r).visibility!=='hidden';});}
  function selected(){var allowed=new Set(rows().map(function(r){return r.dataset.num;}));return items.filter(function(i){return allowed.has(i.row.pl_number);});}
  function popup(row){
    var box=el('div');box.dir='rtl';box.append(el('strong',S('mapjs.plan_prefix','תכנית ')+row.pl_number),el('p',row.pl_name),el('p',row.station_desc||S('mapjs.status_unknown','סטטוס לא ידוע')));
    var button=el('button',S('mapjs.load_boundary','טען גבול תכנית'));button.type='button';button.onclick=function(){focus(row);};box.append(button);
    var tr=Array.from(document.querySelectorAll('#plans tbody tr')).find(function(r){return r.dataset.num===row.pl_number;});
    var source=tr&&tr.querySelector('td a');
    if(source&&source.href.startsWith('https://mavat.iplan.gov.il/'))box.append(el('p'),link(S('mapjs.mavat','פרטי התכנית במאב"ת'),source.href));
    var review=tr&&tr.querySelector('a.ai-review');if(review)box.append(el('p'),link(S('mapjs.ai_review','סקירת AI'),review.href));return box;
  }
  async function fetchGeometry(numbers,signal){
    numbers=numbers.filter(function(n){return /^\d+-\d+$/.test(n);});if(!numbers.length)return;
    var url=new URL('https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/xplan_without_77_78/MapServer/1/query');
    url.search=new URLSearchParams({f:'geojson',where:'pl_number IN ('+numbers.map(function(n){return "'"+n+"'";}).join(',')+')',outFields:'pl_number',returnGeometry:'true',outSR:'4326'}).toString();
    var response=await fetch(url,{credentials:'omit',signal:signal});if(!response.ok)throw Error('source');
    var data=await response.json();if(data.error||data.exceededTransferLimit||!Array.isArray(data.features))throw Error('source');
    var grouped=new Map();data.features.forEach(function(f){var n=f.properties&&f.properties.pl_number;if(numbers.indexOf(n)!==-1&&f.geometry&&['Polygon','MultiPolygon'].indexOf(f.geometry.type)!==-1){if(!grouped.has(n))grouped.set(n,[]);grouped.get(n).push(f);}});
    numbers.forEach(function(n){cache.set(n,grouped.get(n)||[]);});
  }
  // Hit-test geographic coordinates rather than SVG paint order. Holes do
  // not belong to a plan; MultiPolygon parts may be disconnected.
  function ringContains(ring,p){
    var inside=false;
    for(var i=0,j=ring.length-1;i<ring.length;j=i++){
      var a=ring[i],b=ring[j];
      if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
    }return inside;
  }
  function parts(geometry){return geometry.type==='Polygon'?[geometry.coordinates]:geometry.coordinates;}
  function contains(geometry,p){return parts(geometry).some(function(rings){return ringContains(rings[0],p)&&!rings.slice(1).some(function(r){return ringContains(r,p);});});}
  function ringArea(ring){var sum=0;for(var i=0,j=ring.length-1;i<ring.length;j=i++)sum+=ring[j][0]*ring[i][1]-ring[i][0]*ring[j][1];return Math.abs(sum)/2;}
  function area(geometry){return parts(geometry).reduce(function(total,rings){return total+ringArea(rings[0])-rings.slice(1).reduce(function(n,r){return n+ringArea(r);},0);},0);}
  function nearBoundary(geometry,latlng){
    var p=map.latLngToContainerPoint(latlng);
    return parts(geometry).some(function(rings){return rings.some(function(ring){
      for(var i=1;i<ring.length;i++){
        var a=map.latLngToContainerPoint([ring[i-1][1],ring[i-1][0]]),b=map.latLngToContainerPoint([ring[i][1],ring[i][0]]);
        if(L.LineUtil.pointToSegmentDistance(p,a,b)<=6)return true;
      }return false;
    });});
  }
  function inspectPoint(event){
    var visible=new Set(rows().map(function(r){return r.dataset.num;})),p=[event.latlng.lng,event.latlng.lat];
    var hits=drawn.filter(function(item){return visible.has(item.row.pl_number)&&item.features.some(function(f){return contains(f.geometry,p)||nearBoundary(f.geometry,event.latlng);});});
    // Citywide footprints are context outlines, not useful random-area hits.
    // 0.01 square degrees is roughly100 square km at Jerusalem latitude.
    hits=hits.filter(function(item){return item.area<0.01||item.features.some(function(f){return nearBoundary(f.geometry,event.latlng);});});
    hits.sort(function(a,b){return a.area-b.area||a.row.pl_number.localeCompare(b.row.pl_number);});
    map.closePopup();if(!hits.length)return;
    var box=el('div');box.dir='rtl';
    if(hits.length>1)box.append(el('p',TF('mapjs.overlap','{n} תכניות חופפות בנקודה זו - הקטנה מוצגת ראשונה.',{n:hits.length})));
    box.append(popup(hits[0].row));
    hits.slice(1).forEach(function(item){var detail=el('details');detail.append(el('summary',S('mapjs.plan_prefix','תכנית ')+item.row.pl_number+' - '+item.row.pl_name),popup(item.row));box.append(detail);});
    L.popup({maxWidth:280,maxHeight:300}).setLatLng(event.latlng).setContent(box).openOn(map);
  }
  function permitRows(){return Array.from(document.querySelectorAll('#permits-table tbody tr')).filter(function(r){return !r.classList.contains('filtered-out')&&r.getClientRects().length>0&&getComputedStyle(r).visibility!=='hidden';});}
  function permitPopup(rows){
    var box=el('div');box.dir='rtl';box.append(el('strong',S('mapjs.permits_same_parcel','בקשות היתר באותה חלקה')),el('p',S('mapjs.permit_point_note','נקודה מייצגת בחלקה לפי גוש וחלקה, לא כתובת כניסה.')));
    rows.forEach(function(r){var item=el('p'),a=el('a',r.dataset.tik);a.href='#permits';
      a.onclick=function(){r.scrollIntoView({block:'center'});};
      item.append(a,document.createTextNode(' '+r.cells[1].textContent+' - '+r.dataset.status));box.append(item);});return box;
  }
  function drawPermits(){
    permitLayer.clearLayers();permitMarkers=[];var visible=permitRows(),groups=new Map(),missing=0;
    visible.forEach(function(r){var xy=permitPositions.get(r.dataset.tik);if(!xy){missing++;return;}
      var key=xy.join(',');if(!groups.has(key))groups.set(key,{xy:xy,rows:[]});groups.get(key).rows.push(r);});
    groups.forEach(function(g){var icon=L.divIcon({className:'permit-marker',html:'<span style="display:block;width:14px;height:14px;border:2px solid white;background:#9253c7;box-shadow:0 0 2px #222"></span>',iconSize:[14,14],iconAnchor:[7,7]});
      var title=S('mapjs.permits_title','בקשות היתר: ')+g.rows.map(function(r){return r.dataset.tik;}).join(', ');
      var marker=L.marker([g.xy[1],g.xy[0]],{icon:icon,title:title,alt:title});marker.bindPopup(permitPopup(g.rows),{maxWidth:300,maxHeight:300});marker.addTo(permitLayer);permitMarkers.push(marker);});
    return TF('mapjs.permits_status',' בקשות היתר: {visible} שורות גלויות, {with_loc} עם מיקום בחלקה ({points} נקודות), {missing} אין מיקום.',{visible:visible.length,with_loc:visible.length-missing,points:groups.size,missing:missing});
  }
  function draw(){
    var active=selected(),allowed=rows().length,automatic=toggle.checked&&active.length<=MAX&&map.getZoom()>=MIN_ZOOM;
    polygons.clearLayers();drawn=[];var count=0,points=0;
    items.forEach(function(item){map.removeLayer(item.marker);});
    active.forEach(function(item){var fs=(automatic||manual.has(item.row.pl_number))&&cache.get(item.row.pl_number);
      if(fs&&fs.length){L.geoJSON({type:'FeatureCollection',features:fs},{interactive:false,style:{color:color(item.row),weight:3,fillOpacity:.07}}).addTo(polygons);var footprint=fs.reduce(function(n,f){return n+area(f.geometry);},0);drawn.push({row:item.row,features:fs,area:footprint});count++;}
      else{item.marker.addTo(map);points++;}
    });
    var note=!toggle.checked?S('mapjs.boundaries_off',' הצגת גבולות אוטומטית כבויה; ניתן לטעון גבול מתוך כל נקודה.'):active.length>MAX?S('mapjs.too_many',' יותר מ-20 תכניות: סננו את הטבלה להצגת גבולות.'):map.getZoom()<MIN_ZOOM?S('mapjs.zoom_in',' התקרבו במפה להצגת גבולות.'):'';
    status.textContent=allowed===0?S('mapjs.no_match','אין תכניות התואמות לחיפוש או לסינון.'):TF('mapjs.status_rows','{allowed} שורות גלויות בטבלה: {count} גבולות, {points} נקודות, {noloc} ללא מיקום.{note} תאריך מיקומים: {date}.',{allowed:allowed,count:count,points:points,noloc:allowed-active.length,note:note,date:pointsDate});
    status.textContent+=drawPermits();
    if(failed.size&&automatic)status.textContent+=S('mapjs.some_failed',' חלק מהגבולות לא נטענו; הנקודות נשארות זמינות.');
  }
  async function boundaries(){
    clearTimeout(timer);if(controller)controller.abort();controller=new AbortController();var current=++revision;
    draw();var active=selected();if(!toggle.checked||!active.length||active.length>MAX||map.getZoom()<MIN_ZOOM)return;
    var missing=active.map(function(i){return i.row.pl_number;}).filter(function(n){return !cache.has(n)&&!failed.has(n);});if(!missing.length)return;
    status.textContent+=S('mapjs.loading_boundaries',' טוען גבולות ממינהל התכנון…');
    timer=setTimeout(function(){controller.abort();},20000);
    try{await fetchGeometry(missing,controller.signal);}catch(e){if(current!==revision)return;if(e.name!=='AbortError')missing.forEach(function(n){failed.add(n);});else missing.forEach(function(n){failed.add(n);});}
    finally{if(current===revision){clearTimeout(timer);draw();}}
  }
  async function focus(row){
    if(!selected().some(function(i){return i.row.pl_number===row.pl_number;}))return;
    try{
      if(!cache.has(row.pl_number)||!cache.get(row.pl_number).length){await fetchGeometry([row.pl_number],AbortSignal.timeout(20000));}
      if(!selected().some(function(i){return i.row.pl_number===row.pl_number;}))return;
      var fs=cache.get(row.pl_number);if(!fs||!fs.length)throw Error('missing');
      manual.add(row.pl_number);var layer=L.geoJSON({type:'FeatureCollection',features:fs});map.closePopup();map.fitBounds(layer.getBounds(),{padding:[24,24],maxZoom:17});draw();

    }catch(e){status.textContent=TF('mapjs.boundary_unavailable','גבול תכנית {num} אינו זמין כרגע; הנקודה והקישור למקור נשארים זמינים.',{num:row.pl_number});}
  }
  function syncFilter(){if(!map)return;manual.clear();map.closePopup();var active=selected();drawPermits();var locations=active.map(function(i){return i.marker.getLatLng();}).concat(permitMarkers.map(function(m){return m.getLatLng();}));if(locations.length)map.fitBounds(L.latLngBounds(locations),{padding:[30,30],maxZoom:16,animate:false});boundaries();}
  document.addEventListener('plans-filtered',syncFilter);
  document.addEventListener('permits-filtered',syncFilter);
  toggle.addEventListener('change',function(){manual.clear();if(map)boundaries();});
  document.getElementById('map-legend-toggle').onclick=function(){var box=document.getElementById('map-legend');box.hidden=!box.hidden;this.setAttribute('aria-expanded',String(!box.hidden));};
  async function init(){
    if(map){setTimeout(function(){map.invalidateSize();},0);return;}if(loading)return;loading=true;status.textContent=S('mapjs.loading_map','טוען מפת תכניות…');
    try{
      await Promise.all([asset('link','href',BASE+'vendor/leaflet/leaflet.css'),asset('script','src',BASE+'vendor/leaflet/leaflet.js')]);
      var response=await fetch(BASE+'plan-points.json');if(!response.ok)throw Error('points');var data=await response.json();
      map=L.map('plan-map',{scrollWheelZoom:false}).setView([31.768,35.213],14);polygons=L.layerGroup().addTo(map);permitLayer=L.layerGroup().addTo(map);map.on('click',inspectPoint);map.on('popupopen',function(){map.getContainer().classList.add('has-popup');});map.on('popupclose',function(){map.getContainer().classList.remove('has-popup');});
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,referrerPolicy:'strict-origin-when-cross-origin',attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
      try{var pr=await fetch(BASE+'permit-points.json');if(pr.ok){var pd=await pr.json();(pd.points||[]).forEach(function(r){var xy=r.representative_point;if(Array.isArray(xy)&&xy.length===2&&xy.every(Number.isFinite)&&Math.abs(xy[0])<=180&&Math.abs(xy[1])<=90)permitPositions.set(r.tik_num,xy);});}}catch(e){/* Missing positions stay explicit; no guessed geocodes. */}
      var states=new Set();data.points.forEach(function(row){var xy=row.representative_point;if(!Array.isArray(xy)||xy.length!==2||!xy.every(Number.isFinite))return;
        var s=row.station_desc||S('mapjs.status_unknown','סטטוס לא ידוע');states.add(s);
        var icon=L.divIcon({className:'plan-marker',html:markerHtml(category(row.station_desc||''),color(row)),iconSize:[14,14],iconAnchor:[7,7]});
        var marker=L.marker([xy[1],xy[0]],{icon:icon,title:S('mapjs.plan_prefix','תכנית ')+row.pl_number+' '+row.pl_name+' - '+s,alt:S('mapjs.plan_prefix','תכנית ')+row.pl_number+' '+row.pl_name});marker.bindPopup(popup(row),{maxWidth:240});marker.on('popupopen',function(){if(!rows().some(function(r){return r.dataset.num===row.pl_number;}))map.closePopup();});items.push({marker:marker,row:row});
      });
      var legend=document.getElementById('map-legend');legend.replaceChildren(el('p',S('mapjs.legend_line','קו: גבול תכנית. נקודה: מיקום מייצג כשהגבול אינו זמין או בתצוגה רחבה. הצבע והצורה מסמנים סטטוס, כמו בטבלה.')));
      legend.append(el('p',S('mapjs.legend_permits','ריבוע סגול: בקשות היתר באותה חלקה. נקודה פנימית בחלקה, לא כניסה.')));
      Array.from(states).sort().forEach(function(s){var item=el('div'),swatch=el('span');swatch.className='map-swatch';swatch.innerHTML=markerHtml(category(s),colors[category(s)]);item.append(swatch,document.createTextNode(s));legend.append(item);});
      pointsDate=data.generated;syncFilter();map.on('zoomend',boundaries);
    }catch(e){status.textContent=S('mapjs.map_unavailable','לא ניתן לטעון את המפה כרגע. טבלת התכניות נשארת זמינה.');loading=false;}
  }
  panel.addEventListener('toggle',function(){if(panel.open)init();});
}());
