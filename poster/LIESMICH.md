# Eigenes Posting-Tool (Instagram + Facebook)

Kostenlos, ohne Monatslimit. Läuft alle 15 Minuten auf GitHub und postet
freigegebene Beiträge aus `warteschlange.json` über die offizielle Meta-Schnittstelle.

## Ablauf
1. Marc gibt einen Beitrag frei (Planer-Knopf oder „ok“ im Chat).
2. Claude trägt ihn mit `"status": "freigegeben"` in `warteschlange.json` ein.
3. Zur geplanten Zeit postet das Tool und setzt den Status auf
   `veroeffentlicht` (mit Link) oder `fehler` (mit Meldung).
   Mehr als 6 Stunden verspätete Beiträge werden nicht gepostet (`verpasst`).

## Eintrag
```json
{
  "id": "2026-12-01-kg-honigfleisch",
  "konto": "koenigsglut",
  "netzwerke": ["instagram", "facebook"],
  "zeit": "2026-12-01T18:00:00+01:00",
  "text": "Gemeinsamer Text",
  "instagram_text": "optional eigener IG-Text",
  "facebook_text": "optional eigener FB-Text",
  "media": ["https://raw.githubusercontent.com/.../bild1.jpg"],
  "status": "freigegeben"
}
```
- `konto`: `koenigsglut` oder `nordgrimmsaga`
- `media`: öffentliche Links. Instagram nimmt nur **JPEG** (keine PNG). Ein Video (.mp4) wird ein Reel.
  Mehrere Bilder = Karussell (max. 10).
- Achtung: Das Repository ist öffentlich, die Warteschlange ist also vorab sichtbar.

## Zugänge (GitHub → Settings → Secrets and variables → Actions)
`KG_PAGE_ID`, `KG_PAGE_TOKEN`, `KG_IG_ID` (Königsglut) und
`NG_PAGE_ID`, `NG_PAGE_TOKEN`, `NG_IG_ID` (nordgrimmsaga).
Prüfen: Actions → „Posten“ → Run workflow → Modus `check`.
