# Protein Tracker (Home Assistant Custom Integration + Bundled Card)

Diese Lösung erstellt unabhängige Tracker-Instanzen (z. B. je Dashboard/Person) mit:

- Protein-Tracking inklusive editierbarem Tagesziel
- Kalorien-Tracking inklusive editierbarem Tagesziel
- Laufenden Tageswerten mit täglichem Reset um 00:00
- Zwei Eingabewegen je Bereich:
  - direkte Eingabe
  - Lebensmittelmenge + Nährwert pro 100g
- Paralleler Nutzung für mehrere Instanzen

Hinweis: Die Card zeigt den aktuellen Fortschritt fuer Protein und Kalorien. Den normalen Verlauf nutzt du ueber die Sensoren in Home Assistant (History/Verlauf-Ansicht).

## HACS

Das Repository ist jetzt als HACS-Integration aufgebaut:

- `hacs.json` liegt im Repo-Root
- alle Laufzeitdateien liegen innerhalb von `custom_components/protein_tracker/`
- die Lovelace-Card wird direkt aus der Integration unter `/protein_tracker/protein-tracker-card.js` ausgeliefert

## Struktur

- `custom_components/protein_tracker/` - Integration, Services, Entities, Persistenz und gebuendelte Card-Datei
- `custom_components/protein_tracker/protein-tracker-card.js` - kombinierte Protein- und Kalorien-Card
- `custom_components/protein_tracker/brand/` - Integrations-Branding-Assets

## Installation

1. Repository per HACS als `Integration` installieren oder `custom_components/protein_tracker` manuell nach `<HA_CONFIG>/custom_components/protein_tracker` kopieren.
2. Lovelace Resource hinzufügen:
   - URL: `/protein_tracker/protein-tracker-card.js?v=2.14.0`
   - Typ: `module`
3. Home Assistant neu starten.
4. Browser Hard-Reload (`Ctrl+F5`).

## Card-Konfiguration

Minimal (automatische Entity-Erkennung):

```yaml
type: custom:protein-tracker-card
name: Protein Tracker
```

Empfohlen (explizit pro Dashboard):

```yaml
type: custom:protein-tracker-card
entity: sensor.dashboard1_protein
name: Protein Tracker - Dashboard 1
```

Zweite unabhängige Instanz:

```yaml
type: custom:protein-tracker-card
entity: sensor.dashboard2_protein
name: Protein Tracker - Dashboard 2
```

Wichtig:
- Die Card schreibt ueber denselben Dialog in beide Tracker
- Protein nutzt `sensor.<id>_protein` und `number.<id>_protein`
- Kalorien nutzt `sensor.<id>_calories` und `number.<id>_calories`
- Zwei Instanzen sind nur dann unabhängig, wenn sie unterschiedliche `<id>` nutzen

## Services

Jeder Service akzeptiert:
- empfohlen: `entity_id` (z. B. `sensor.dashboard1_protein`)
- optional fallback: `user_id`

Services:
- `protein_tracker.add_protein` (`grams`)
- `protein_tracker.add_food` (`food_grams`, `protein_per_100g`)
- `protein_tracker.set_goal` (`goal_grams`)
- `protein_tracker.reset_user`
- `protein_tracker.undo_last`
- `protein_tracker.add_calories` (`calories`)
- `protein_tracker.add_calorie_food` (`food_grams`, `calories_per_100g`)
- `protein_tracker.set_calorie_goal` (`goal_calories`)
- `protein_tracker.reset_calories`

## Optional: YAML-Import

Falls du lieber per `configuration.yaml` definierst, werden Einträge beim Start als Config Entries importiert:

```yaml
protein_tracker:
  users:
    - id: dashboard1
      name: Jon
      goal: 160
      calorie_goal: 2200
    - id: dashboard2
      name: Alex
      goal: 140
      calorie_goal: 2500
```

`name` ist dabei nur der Basisname. Die Integration ergänzt die Anzeigenamen automatisch
(z. B. `Jon Protein Tracker`, `Jon Protein Ziel`, `Jon Kalorien Tracker`, `Jon Kalorien Ziel`).
