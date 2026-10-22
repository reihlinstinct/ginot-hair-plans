/* Optional map. Only public representative points are stored; selected boundaries
 * are fetched directly by the visitor, never stored in this site. */
(function () {
  'use strict';
  var panel = document.getElementById('plan-map-panel');
  if (!panel) return;
  var markers = [], pointsDate = "";
  var status = document.getElementById('map-status'), map, boundary, loading = false;
  var colors = {deposit:'#e8c31d',review:'#00a8cf',conditions:'#c8a4de',decision:'#ff8c00',process:'#51b89a',approved:'#6db633',other:'#dde4f6'};
  function category(s) {
    if (s.indexOf('הפקדה') !== -1) return 'deposit';
    if (s.indexOf('בדיקה') !== -1) return 'review';
    if (s.indexOf('תנאים') !== -1) return 'conditions';
    if (s.indexOf('הכרעה') !== -1) return 'decision';
    if (s.indexOf('בהליך') !== -1) return 'process';
    if (s.indexOf('אישור') !== -1) return 'approved';
    return 'other';
  }
  function el(tag, text) { var e=document.createElement(tag); if(text) e.textContent=text;return e; }
  function link(text,url) { var a=el('a',text);a.href=url;a.target='_blank';a.rel='noopener';return a; }
  function asset(tag,attr,url) {return new Promise(function(resolve,reject){var e=document.createElement(tag);e[attr]=url;e.onload=resolve;e.onerror=reject;if(tag==='link')e.rel='stylesheet';document.head.appendChild(e);});}
  document.getElementById('map-legend-toggle').onclick=function(){var box=document.getElementById('map-legend');box.hidden=!box.hidden;this.setAttribute('aria-expanded',String(!box.hidden));};
  async function loadBoundary(row) {
    if (!/^\d+-\d+$/.test(row.pl_number)) return;
    status.textContent='טוען גבול תכנית '+row.pl_number+'…';
    var url=new URL('https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/xplan_without_77_78/MapServer/1/query');
    url.search=new URLSearchParams({f:'geojson',where:"pl_number='"+row.pl_number+"'",outFields:'pl_number',returnGeometry:'true',outSR:'4326'}).toString();
    try {
      var response=await fetch(url,{credentials:'omit',signal:AbortSignal.timeout(20000)});
      if(!response.ok)throw Error('source');
      var data=await response.json();
      if(data.error || !Array.isArray(data.features) || !data.features.length)throw Error('missing');
      var current=Array.from(document.querySelectorAll('#plans tbody tr')).find(function(r){return r.dataset.num===row.pl_number;});
      if(!current || current.dataset.mapMatch!=='1')return;
      if(boundary)map.removeLayer(boundary);
      boundary=L.geoJSON(data,{style:{color:colors[category(row.station_desc||'')],weight:4,fillOpacity:.15}}).addTo(map);
      map.fitBounds(boundary.getBounds(),{padding:[20,20],maxZoom:17});
      status.textContent='גבול תכנית '+row.pl_number+' נטען כעת ממינהל התכנון. להמחשה, לא מסמך רשמי.';
    } catch(e) {status.textContent='לא ניתן לטעון את גבול התכנית כרגע. הנקודות והטבלה נשארות זמינות; אפשר לפתוח את המקור הרשמי.';}
  }
  function popup(row, index) {
    var box=el('div');box.dir='rtl';box.append(el('strong',index+'. '+row.pl_number),el('p',row.pl_name),el('p',row.station_desc||'סטטוס לא ידוע'));
    var button=el('button','טען גבול תכנית');button.type='button';button.onclick=function(){loadBoundary(row);};box.append(button);
    var tr=Array.from(document.querySelectorAll('#plans tbody tr')).find(function(r){return r.dataset.num===row.pl_number;});
    var source=tr && tr.querySelector('td a');
    if(source && source.href.startsWith('https://mavat.iplan.gov.il/'))box.append(el('p'),link('פרטי התכנית במאב"ת',source.href));
    var review=tr && tr.querySelector('a.ai-review');if(review)box.append(el('p'),link('סקירת AI',review.href));
    return box;
  }
  function syncFilter() {
    if(!map)return;
    var allowed=new Set(Array.from(document.querySelectorAll('#plans tbody tr')).filter(function(r){return r.dataset.mapMatch==='1';}).map(function(r){return r.dataset.num;}));
    var visible=0, positions=[];
    markers.forEach(function(item){if(allowed.has(item.row.pl_number)){if(!map.hasLayer(item.marker))item.marker.addTo(map);visible++;positions.push(item.marker.getLatLng());}else{map.removeLayer(item.marker);}});
    if(boundary){map.removeLayer(boundary);boundary=null;}
    if(positions.length)map.fitBounds(L.latLngBounds(positions),{padding:[30,30],maxZoom:16,animate:false});
    status.textContent=allowed.size===0?'אין תכניות התואמות לחיפוש או לסינון.':visible+' תכניות מסוננות על המפה; '+(allowed.size-visible)+' ללא מיקום. תאריך מיקומים: '+pointsDate+'.';
  }
  document.addEventListener('plans-filtered',syncFilter);
  async function init() {
    if(map){setTimeout(function(){map.invalidateSize();},0);return;}
    if(loading)return;loading=true;status.textContent='טוען מפת תכניות…';
    try {
      await Promise.all([asset('link','href','vendor/leaflet/leaflet.css'),asset('script','src','vendor/leaflet/leaflet.js')]);
      var response=await fetch('plan-points.json');if(!response.ok)throw Error('points');var data=await response.json();
      map=L.map('plan-map',{scrollWheelZoom:false}).setView([31.768,35.213],14);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,referrerPolicy:'strict-origin-when-cross-origin',attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
      var states=new Set(),count=0;
      data.points.forEach(function(row,i){var xy=row.representative_point;if(!Array.isArray(xy)||xy.length!==2||!xy.every(Number.isFinite))return;
        var s=row.station_desc||'סטטוס לא ידוע';states.add(s);count++;
        var icon=L.divIcon({className:'plan-marker',html:'<span style="background:'+colors[category(s)]+'">'+(i+1)+'</span>',iconSize:[28,28],iconAnchor:[14,14]});
        var marker=L.marker([xy[1],xy[0]],{icon:icon,title:(i+1)+'. '+row.pl_number+' '+row.pl_name+' - '+s,alt:row.pl_number+' '+s}).addTo(map);marker.bindPopup(popup(row,i+1),{maxWidth:240,autoPanPadding:[48,25]});markers.push({marker:marker,row:row});
      });
      var legend=document.getElementById('map-legend');legend.replaceChildren();Array.from(states).sort().forEach(function(s){var item=el('div'),swatch=el('span');swatch.className='map-swatch';swatch.style.background=colors[category(s)];item.append(swatch,document.createTextNode(s));legend.append(item);});
      pointsDate=data.generated; syncFilter();

    } catch(e) {status.textContent='לא ניתן לטעון את המפה כרגע. טבלת התכניות נשארת זמינה.';loading=false;}
  }
  panel.addEventListener('toggle',function(){if(panel.open)init();});
}());
