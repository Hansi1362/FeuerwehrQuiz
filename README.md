# Quiz-Spiel (lokal, wie Kahoot)

Läuft komplett offline im WLAN/LAN. Nur Python 3.8+ nötig – **keine Installation von Paketen**.

## Starten

```
python3 server.py
```

Der Browser öffnet sich automatisch mit dem **Spielbildschirm** (`/host`).
Dort steht der **QR-Code** – Handys im selben WLAN scannen ihn und landen auf `/play`.

| Seite | Adresse | Wofür |
|---|---|---|
| Spielbildschirm | `http://localhost:8000/host` | am PC/Beamer: QR-Code, Fragen, Punkte, Sieger |
| Handy | `http://<PC-IP>:8000/play` | Namen eingeben, Antworten antippen |
| Admin | `http://localhost:8000/admin` | Fragerunden erstellen/bearbeiten/starten, Pause, Abbrechen |

Optionen: `--port 8080`, `--no-browser`, `--db ordner`, `--admin-remote`.
`/admin` und die Steuerung (Start/Pause/Abbrechen/Fragen ändern) sind standardmäßig **nur am Spiel-PC** erreichbar,
damit Mitspieler nicht in die Fragen (inkl. Lösungen) schauen können. Mit `--admin-remote` geht es auch von anderen Geräten.

Falls der PC mehrere Netzwerke hat und im QR-Code die falsche IP steht: Adresse im Spielbildschirm prüfen
bzw. Firewall-Freigabe für Port 8000 erlauben.

## Spielablauf

1. Admin: Fragerunde anlegen (oder die Beispielrunde nutzen), im Spielbildschirm auswählen.
2. Spieler scannen den QR-Code und geben ihren Namen ein.
3. **Spiel starten** → pro Frage: kurze Lesezeit → Antwortphase (Zeitbalken) → Auflösung mit Punkten → Zwischenstand → nächste Frage, automatisch.
   Die Antwortphase endet früher, wenn alle geantwortet haben.
4. Oben rechts im Spielbildschirm: **Anhalten / Weiter (überspringen) / Abbrechen**.
5. Am Ende: Sieger + Podest. „Neues Spiel“ löscht Spieler, Punkte und Antworten.

**Punkte:** Wer als Erstes richtig antwortet, bekommt 1000, der Zweite 900, … mindestens 100.
Bei Fragen mit mehreren richtigen Antworten zählt nur die vollständig richtige Auswahl.

## Fragenersteller (eigenständig) und Import

Im Ordner `Fragenersteller/` liegt die Datei **`fragenersteller.html`**. Sie läuft komplett für sich:
per Doppelklick im Browser öffnen – kein Server, kein Python, keine Internetverbindung nötig.
Man kann sie per E-Mail/USB an andere weitergeben, die dann Fragen vorbereiten.

1. Im Fragenersteller Runde anlegen (gleicher Editor wie im Admin). Der Entwurf wird automatisch im Browser gespeichert.
2. **Exportieren** → es entsteht eine Datei `name.quizrunde.json`.
3. Im Quiz-Admin (`/admin`) auf **⬆ Importieren** klicken und die Datei(en) wählen (mehrere gleichzeitig möglich).
   Gleiche Namen werden nicht überschrieben, sondern als „Name (2)“ angelegt.
4. Umgekehrt: Im Admin gibt es pro Runde **⬇ Export**, und im Fragenersteller lädt **⬆ Datei laden** eine Datei zum Weiterbearbeiten.

Wichtig: Der Import ist nur am Spiel-PC möglich (wie das ganze Admin).

## Feuerwehr-Design anpassen

* **Name der Wehr:** in `DB/settings.json` bei `"title"` eintragen, z. B. `"FF Musterstadt – Quiz"`.
* **Wappen/Logo:** Bilddatei als `web/logo.png` ablegen (am besten transparenter Hintergrund). Es erscheint im Spielbildschirm und am Handy. Ohne Datei wird nichts angezeigt.
* **Farben:** am Anfang von `web/style.css` (`--accent` = Feuerwehrrot, `--yellow` = Warngelb).
* Die Überschriften nutzen die Schrift „Impact“ (auf Windows vorhanden).
* Mitgeliefert: die Runde „Feuerwehr-Grundlagen“ (5 Fragen) und die Beispielrunde.

## Fragetypen

* **Ja / Nein**
* **4 Antworten** – eine oder mehrere können richtig sein (am Handy dann: auswählen + „Antwort senden“)

## Daten (Ordner `DB/`)

| Datei | Inhalt |
|---|---|
| `quizzes.json` | alle Fragerunden (bleiben dauerhaft erhalten) |
| `settings.json` | Zeiten und Punkte (Lesezeit, Auflösung, Zwischenstand, Punkte erster Platz, Abstufung, Minimum) |
| `session.json` | laufendes Spiel: Spieler, Punkte, Antworten – wird bei „Neues Spiel“/Abbrechen/Serverstart geleert |

## Dateien

* `server.py` – Webserver, Spiellogik, JSON-Speicher
* `qr.py` – QR-Code-Generator (ohne Zusatzpakete)
* `web/` – Oberflächen (`host`, `play`, `admin`)
* `Fragenersteller/fragenersteller.html` – eigenständiges Tool zum Erstellen von Fragerunden
