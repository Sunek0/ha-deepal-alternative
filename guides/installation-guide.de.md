# Vollständige Anleitung: Zweitkonto und Installation von Deepal Alternative

Schritt-für-Schritt-Anleitung, um dein Changan/Deepal-Auto mit der Integration
**Deepal Alternative** in Home Assistant einzubinden. Sie deckt den gesamten Prozess ab: von der
Erstellung des Zweitkontos in der My Changan App bis zur Installation der Integration mit HACS und
ihrer Konfiguration.

## Inhalt

1. [Warum ein Zweitkonto verwenden](#warum-ein-zweitkonto-verwenden)
2. [Voraussetzungen](#voraussetzungen)
3. [Teil 1: Zweitkonto in My Changan](#teil-1-zweitkonto-in-my-changan)
4. [Teil 2: Installation der Integration](#teil-2-installation-der-integration)
5. [Hinweise und Fehlerbehebung](#hinweise-und-fehlerbehebung)

## Warum ein Zweitkonto verwenden

Die Integration meldet sich bei der offiziellen My Changan Plattform an. Ein einzelnes Konto kann
nicht zwei aktive Sitzungen gleichzeitig halten: Wenn sich Home Assistant mit deinem Hauptkonto
anmeldet, kann die App am Handy abgemeldet werden, und wenn du dich wieder in der App anmeldest,
wird die Home-Assistant-Sitzung ungültig.

Die empfohlene Lösung ist, ein **Zweitkonto** zu erstellen, das Auto vom Hauptkonto zu teilen und in
Home Assistant nur das Zweitkonto zu verwenden. So funktioniert dein Hauptkonto am Handy weiterhin
normal.

## Voraussetzungen

- Ein kompatibles Deepal-Fahrzeug (S05, S07), das mit einem My Changan Konto verknüpft ist.
- Zugriff auf die **My Changan** App mit dem Hauptkonto.
- Eine andere E-Mail-Adresse oder Telefonnummer für das Zweitkonto.
- Home Assistant 2026.3.0 oder neuer.
- Installiertes [HACS](https://hacs.xyz/docs/use/download/download/). Falls noch nicht vorhanden,
  folge der offiziellen Installationsanleitung unter
  <https://hacs.xyz/docs/use/download/download/>.

## Teil 1: Zweitkonto in My Changan

### 1. Das Zweitkonto erstellen

1. Öffne die **My Changan** App und erstelle ein neues Konto mit einer anderen E-Mail-Adresse oder
   Telefonnummer als bei deinem Hauptkonto.
2. Notiere die Zugangsdaten (E-Mail/Telefon und Zugangscode): Diese verwendest du in Home Assistant.

### 2. Das Fahrzeug vom Hauptkonto teilen

1. Melde dich vom Zweitkonto ab und in der App mit dem **Hauptkonto** an.
2. Tippe auf die **Teilen**-Schaltfläche auf dem Hauptbildschirm.
3. Lade das soeben erstellte Zweitkonto ein und gib einen dauerhaften Gültigkeitszeitraum an.

### 3. Den Zugriff annehmen und das Steuerpasswort erstellen

1. Melde dich vom **Hauptkonto** in der App ab und mit dem **Zweitkonto** an.
2. Nimm den Zugriff auf das geteilte Auto an.
3. Gehe zum **persönlichen Bereich** (Profil) und tippe auf **Mein Fahrzeug**.
4. Wähle das geteilte Auto aus.
5. Tippe auf **Fahrzeug-Steuerpasswort** und erstelle ein Passwort (PIN). Notiere es: Dies ist die
   PIN, die Home Assistant für die Befehle für Türen, Fenster und Kofferraum abfragt.

> Wenn du diese Option in deiner App-Version nicht findest, versuche, die Fenster über die App zu
> senken: Sie fordert dich auf, die Steuer-PIN zu erstellen. Erstelle sie und prüfe, ob der Befehl
> funktioniert.

### 4. Zurück zum Hauptkonto

1. Melde dich vom Zweitkonto ab und am Handy wieder mit dem **Hauptkonto** an.
2. Das Hauptkonto bleibt Eigentümer des Fahrzeugs; das Zweitkonto wird nur in Home Assistant
   verwendet.

## Teil 2: Installation der Integration

### 5. HACS installieren (falls noch nicht vorhanden)

HACS ist der Verwalter für benutzerdefinierte Integrationen in Home Assistant. Falls du es noch
nicht installiert hast, folge der offiziellen Anleitung:
<https://hacs.xyz/docs/use/download/download/>. Nach der Installation erscheint der Tab **HACS** in
der Seitenleiste von Home Assistant.

### 6. Das Repository zu HACS hinzufügen

1. Öffne in Home Assistant den Tab **HACS**.
2. Öffne das Drei-Punkte-Menü (⋮) oben rechts und wähle **Benutzerdefinierte Repositories**.
3. Füge die Repository-URL ein:
   `https://github.com/Sunek0/ha-deepal-alternative`
4. Wähle unter **Kategorie** die Option **Integration** und drücke **Hinzufügen**.

### 7. Deepal Alternative installieren und neu starten

1. Suche in HACS nach **Deepal Alternative** (nutze die Suche im Tab oder die Kategorie
   **Integrationen**).
2. Öffne den Eintrag und drücke **Herunterladen**.
3. **Starte Home Assistant neu**, um die neue Integration zu laden.

### 8. Die Integration hinzufügen

1. Gehe zu **Einstellungen → Geräte & Dienste**.
2. Drücke **Integration hinzufügen** und suche **Deepal Alternative**.
3. Wähle unter **Plattform** die Option **International (Europe)** (die Option SDA (China) ist nur
   für Konten aus dem chinesischen Festland mit Access Token).
4. Wähle unter **Anmeldemethode**, wie sich dein Zweitkonto anmeldet:
   - **Email code**: Ein Bestätigungscode wird an die E-Mail-Adresse gesendet.
   - **Phone/SMS code**: Ein Bestätigungscode wird per SMS an das Handy gesendet.
5. Fülle die Formularfelder aus:
   - **Verkaufsland**: das in deinem My Changan Konto registrierte Land (zum Beispiel Spanien).
   - **E-Mail** oder **Mobilnummer** (ohne Ländervorwahl) des **Zweitkontos**.
6. Warte auf den Bestätigungscode (E-Mail oder SMS) und gib ihn unter **Bestätigungscode** ein.
7. Die Integration prüft das Konto und erstellt ein Gerät pro Fahrzeug. Fertig.

### 9. Die Fernsteuerungs-PIN speichern

Dieser Schritt ist **nur nötig**, um die signierten Befehle (Türverriegelung, Fenster und
Kofferraum) zu verwenden und damit Home Assistant deren Entitäten erstellt:

1. Gehe zu **Einstellungen → Geräte & Dienste → Deepal Alternative**.
2. Drücke **Konfigurieren**.
3. Gib unter **Fernsteuerungs-PIN** das Passwort ein, das du in Schritt 3 mit dem Zweitkonto
   erstellt hast.
4. Speichere. Die Entitäten für Türen, Fenster und Kofferraum erscheinen am Gerät des Autos.

### 10. Prüfen, ob es funktioniert

- Öffne die Geräteseite des Fahrzeugs: Du solltest die Sensoren für Batterie, Reichweite, Laden und
  weitere Telemetrie sehen.
- Teste einen sicheren Befehl (zum Beispiel Licht oder Klima einschalten) und prüfe, ob das Auto
  reagiert.
- Die Befehle, die von der PIN abhängen (Türen, Fenster, Kofferraum), werden mit der PIN signiert,
  die du mit dem Zweitkonto erstellt hast; wenn sie fehlschlagen, prüfe Schritt 9 erneut.

## Hinweise und Fehlerbehebung

- **Ich kann nichts steuern**: Prüfe zuerst, ob die offizielle App es mit demselben Konto kann. Das
  Auto lehnt Fernbefehle manchmal ab, bis es ein paar Minuten gefahren wurde.
- **"Remote control PIN is not set", obwohl ich die PIN gespeichert habe**: Die PIN wurde nicht mit
  dem Konto erstellt, das Home Assistant verwendet. Melde dich in der App mit dem Zweitkonto an,
  erstelle die PIN (Schritt 3) und speichere sie erneut in den Optionen der Integration.
- **Home Assistant verlangt eine erneute Anmeldung**: Die Sitzung wurde von der App oder einem
  anderen Gerät ungültig gemacht. Melde dich erneut an; mit dem Zweitkonto ist das viel seltener.
- **Die Werte scheinen veraltet**: Das Auto meldet Telemetrie nur, wenn es wach ist; die Integration
  zeigt den letzten bekannten Wert, bis es wieder meldet.
- **Hinweis**: Inoffizielles Projekt, ohne Verbindung zu Changan Automobile. Die Fernbefehle wirken
  auf das echte Auto: Stelle sicher, dass es sicher ist, bevor du Verriegelung, Fenster, Kofferraum,
  Klima, Licht oder Hupe verwendest.
