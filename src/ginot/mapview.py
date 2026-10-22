"""Optional map markup; real boundaries are fetched in the visitor browser only."""
PANEL = '''<details id="plan-map-panel" class="plan-map-panel">
<summary>מפת התכניות - נקודות וגבולות</summary>
<p>המפה מציגה רק את השורות הגלויות בטבלת התכניות. קווים: גבולות תכנית. נקודה קטנה: מיקום מייצג בלבד, לא כתובת כניסה. המפה אינה מסמך רשמי.</p>
<label class="map-boundary-control"><input id="map-boundaries" type="checkbox" checked> הצג גבולות לכל התכניות המוצגות</label>
<button id="map-legend-toggle" type="button" aria-expanded="false" aria-controls="map-legend">מקרא צבעי המפה</button>
<div id="map-legend" hidden></div>
<p id="map-status" role="status">פתחו את המפה לטעינת הנקודות.</p>
<div id="plan-map" aria-label="מפת מיקומי תכניות" tabindex="0"></div>
<p>גבולות נטענים אוטומטית לעד 20 תכניות; בתצוגה רחבה מאוד מוצגות נקודות. לחצו על קו או נקודה לשם התכנית ומספרה. הגבול נטען ישירות משירות מינהל התכנון לדפדפן, ואינו נשמר באתר.</p>
<p><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a> · מקור מיקומים וגבולות: מינהל התכנון. הזמינות והעדכניות אינן מובטחות.</p>
</details>
<script src="plan-map.js" defer></script>'''
