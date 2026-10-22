/* Public points only on disk. Boundaries fetched live by the visitor and kept
 * in this page's memory only. One bounded batch per visible selection. */
(function () {
  'use strict';
  var panel=document.getElementById('plan-map-panel');if(!panel)return;
  var items=[],drawn=[],pointsDate='',map,loading=false,polygons,controller,revision=0,timer;
  var cache=new Map(),failed=new Set(),manual=new Set(),MAX=20,MIN_ZOOM=11;
  var toggle=document.getElementById('map-boundaries');
  var status=document.getElementById('map-status');
  var colors={deposit:'#e8c31d',review:'#00a8cf',conditions:'#c8a4de',decision:'#ff8c00',process:'#51b89a',approved:'#6db633',other:'#dde4f6'};
  function category(s){
    if(s.indexOf('הפקדה')!==-1)return 'deposit';
    if(s.indexOf('בדיקה')!==-1)return 'review';
    if(s.indexOf('תנאים')!==-1)return 'conditions';
    if(s.indexOf('הכרעה')!==-1)return 'decision';
    if(s.indexOf('בהליך')!==-1)return 'process';
    if(s.indexOf('אישור')!==-1)return 'approved';return 'other';
  }
  function color(row){return colors[category(row.station_desc||'')];}
  function el(tag,text){var e=document.createElement(tag);if(text)e.textContent=text;return e;}
  function link(text,url){var a=el('a',text);a.href=url;a.target='_blank';a.rel='noopener';return a;}
  function asset(tag,attr,url){return new Promise(function(resolve,reject){var e=document.createElement(tag);e[attr]=url;e.onload=resolve;e.onerror=reject;if(tag==='link')e.rel='stylesheet';document.head.appendChild(e);});}
  function rows(){return Array.from(document.querySelectorAll('#plans tbody tr:not(.filtered-out)'));}
  function selected(){var allowed=new Set(rows().map(function(r){return r.dataset.num;}));return items.filter(function(i){return allowed.has(i.row.pl_number);});}
  function popup(row){
    var box=el('div');box.dir='rtl';box.append(el('strong','תכנית '+row.pl_number),el('p',row.pl_name),el('p',row.station_desc||'סטטוס לא ידוע'));
    var button=el('button','טען גבול תכנית');button.type='button';button.onclick=function(){focus(row);};box.append(button);
    var tr=Array.from(document.querySelectorAll('#plans tbody tr')).find(function(r){return r.dataset.num===row.pl_number;});
    var source=tr&&tr.querySelector('td a');
    if(source&&source.href.startsWith('https://mavat.iplan.gov.il/'))box.append(el('p'),link('פרטי התכנית במאב"ת',source.href));
    var review=tr&&tr.querySelector('a.ai-review');if(review)box.append(el('p'),link('סקירת AI',review.href));return box;
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
  function inspectPoint(event){
    var visible=new Set(rows().map(function(r){return r.dataset.num;})),p=[event.latlng.lng,event.latlng.lat];
    var hits=drawn.filter(function(item){return visible.has(item.row.pl_number)&&item.features.some(function(f){return contains(f.geometry,p);});});
    hits.sort(function(a,b){return a.area-b.area||a.row.pl_number.localeCompare(b.row.pl_number);});
    map.closePopup();if(!hits.length)return;
    var box=el('div');box.dir='rtl';
    if(hits.length>1)box.append(el('p',hits.length+' תכניות חופפות בנקודה זו - הקטנה מוצגת ראשונה.'));
    box.append(popup(hits[0].row));
    hits.slice(1).forEach(function(item){var detail=el('details');detail.append(el('summary','תכנית '+item.row.pl_number+' - '+item.row.pl_name),popup(item.row));box.append(detail);});
    L.popup({maxWidth:280,maxHeight:300}).setLatLng(event.latlng).setContent(box).openOn(map);
  }
  function draw(){
    var active=selected(),allowed=rows().length,automatic=toggle.checked&&active.length<=MAX&&map.getZoom()>=MIN_ZOOM;
    polygons.clearLayers();drawn=[];var count=0,points=0;
    items.forEach(function(item){map.removeLayer(item.marker);});
    active.forEach(function(item){var fs=(automatic||manual.has(item.row.pl_number))&&cache.get(item.row.pl_number);
      if(fs&&fs.length){L.geoJSON({type:'FeatureCollection',features:fs},{interactive:false,style:{color:color(item.row),weight:3,fillOpacity:.07}}).addTo(polygons);drawn.push({row:item.row,features:fs,area:fs.reduce(function(n,f){return n+area(f.geometry);},0)});count++;}
      else{item.marker.addTo(map);points++;}
    });
    var note=!toggle.checked?' הצגת גבולות אוטומטית כבויה; ניתן לטעון גבול מתוך כל נקודה.':active.length>MAX?' יותר מ-20 תכניות: סננו את הטבלה להצגת גבולות.':map.getZoom()<MIN_ZOOM?' התקרבו במפה להצגת גבולות.':'';
    status.textContent=allowed===0?'אין תכניות התואמות לחיפוש או לסינון.':allowed+' שורות גלויות בטבלה: '+count+' גבולות, '+points+' נקודות, '+(allowed-active.length)+' ללא מיקום.'+note+' תאריך מיקומים: '+pointsDate+'.';
    if(failed.size&&automatic)status.textContent+=' חלק מהגבולות לא נטענו; הנקודות נשארות זמינות.';
  }
  async function boundaries(){
    clearTimeout(timer);if(controller)controller.abort();controller=new AbortController();var current=++revision;
    draw();var active=selected();if(!toggle.checked||!active.length||active.length>MAX||map.getZoom()<MIN_ZOOM)return;
    var missing=active.map(function(i){return i.row.pl_number;}).filter(function(n){return !cache.has(n)&&!failed.has(n);});if(!missing.length)return;
    status.textContent+=' טוען גבולות ממינהל התכנון…';
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

    }catch(e){status.textContent='גבול תכנית '+row.pl_number+' אינו זמין כרגע; הנקודה והקישור למקור נשארים זמינים.';}
  }
  function syncFilter(){if(!map)return;manual.clear();map.closePopup();var active=selected();if(active.length)map.fitBounds(L.latLngBounds(active.map(function(i){return i.marker.getLatLng();})),{padding:[30,30],maxZoom:16,animate:false});boundaries();}
  document.addEventListener('plans-filtered',syncFilter);
  toggle.addEventListener('change',function(){manual.clear();if(map)boundaries();});
  document.getElementById('map-legend-toggle').onclick=function(){var box=document.getElementById('map-legend');box.hidden=!box.hidden;this.setAttribute('aria-expanded',String(!box.hidden));};
  async function init(){
    if(map){setTimeout(function(){map.invalidateSize();},0);return;}if(loading)return;loading=true;status.textContent='טוען מפת תכניות…';
    try{
      await Promise.all([asset('link','href','vendor/leaflet/leaflet.css'),asset('script','src','vendor/leaflet/leaflet.js')]);
      var response=await fetch('plan-points.json');if(!response.ok)throw Error('points');var data=await response.json();
      map=L.map('plan-map',{scrollWheelZoom:false}).setView([31.768,35.213],14);polygons=L.layerGroup().addTo(map);map.on('click',inspectPoint);map.on('popupopen',function(){map.getContainer().classList.add('has-popup');});map.on('popupclose',function(){map.getContainer().classList.remove('has-popup');});
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,referrerPolicy:'strict-origin-when-cross-origin',attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
      var states=new Set();data.points.forEach(function(row){var xy=row.representative_point;if(!Array.isArray(xy)||xy.length!==2||!xy.every(Number.isFinite))return;
        var s=row.station_desc||'סטטוס לא ידוע';states.add(s);
        var icon=L.divIcon({className:'plan-marker',html:'<span style="background:'+color(row)+'"></span>',iconSize:[14,14],iconAnchor:[7,7]});
        var marker=L.marker([xy[1],xy[0]],{icon:icon,title:'תכנית '+row.pl_number+' '+row.pl_name+' - '+s,alt:'תכנית '+row.pl_number+' '+row.pl_name});marker.bindPopup(popup(row),{maxWidth:240});items.push({marker:marker,row:row});
      });
      var legend=document.getElementById('map-legend');legend.replaceChildren(el('p','קו: גבול תכנית. נקודה: מיקום מייצג כשהגבול אינו זמין או בתצוגה רחבה. הצבע מסמן סטטוס, כמו בטבלה.'));
      Array.from(states).sort().forEach(function(s){var item=el('div'),swatch=el('span');swatch.className='map-swatch';swatch.style.background=colors[category(s)];item.append(swatch,document.createTextNode(s));legend.append(item);});
      pointsDate=data.generated;syncFilter();map.on('zoomend',boundaries);
    }catch(e){status.textContent='לא ניתן לטעון את המפה כרגע. טבלת התכניות נשארת זמינה.';loading=false;}
  }
  panel.addEventListener('toggle',function(){if(panel.open)init();});
}());
