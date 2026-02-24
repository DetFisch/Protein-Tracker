# Protein Tracker (Home Assistant Custom Integration + Custom Card)

Diese Lösung erstellt unabhängige Protein-Tracker-Instanzen (z. B. je Dashboard/Person) mit:

- Tagesziel pro Instanz (editierbar)
- Laufender Tagesmenge
- Täglichem Reset um 00:00
- Zwei Eingabewegen im Dialog:
  - direkte Proteinmenge in Gramm
  - Lebensmittelmenge + Protein pro 100g
- Parallel/individuell für mehrere Instanzen

Hinweis: Die Card zeigt nur den aktuellen Fortschritt. Den normalen Verlauf nutzt du über den Sensor in Home Assistant (History/Verlauf-Ansicht).

## Struktur

- `custom_components/protein_tracker/` - Custom Integration (Config Flow + Entities + Services + Persistenz)
- `www/protein-tracker-card.js` - eine einzige Protein-Tracker-Card
- `custom_components/protein_tracker/icon.png` / `logo.png` - Integrations-Branding-Assets (Best-Effort)

## Installation

1. `custom_components/protein_tracker` nach `<HA_CONFIG>/custom_components/protein_tracker` kopieren.
2. `www/protein-tracker-card.js` nach `<HA_CONFIG>/www/protein-tracker-card.js` kopieren.
3. Lovelace Resource hinzufügen:
   - URL: `/local/protein-tracker-card.js?v=2.10.0`
   - Typ: `module`
4. Home Assistant neu starten.
5. Browser Hard-Reload (`Ctrl+F5`).

## Card-Konfiguration

Minimal (automatische Entity-Erkennung):

```yaml
type: custom:protein-tracker-card
name: Protein Tracker
```

Empfohlen (explizit pro Dashboard):

```yaml
type: custom:protein-tracker-card
entity: sensor.dashboard1
name: Protein Tracker - Dashboard 1
```

Zweite unabhängige Card:

```yaml
type: custom:protein-tracker-card
entity: sensor.dashboard2
name: Protein Tracker - Dashboard 2
```

Wichtig: Zwei Cards sind nur dann unabhängig, wenn sie unterschiedliche `entity` nutzen.

## Services

Jeder Service akzeptiert:
- empfohlen: `entity_id` (z. B. `sensor.dashboard1`)
- optional fallback: `user_id`

Services:
- `protein_tracker.add_protein` (`grams`)
- `protein_tracker.add_food` (`food_grams`, `protein_per_100g`)
- `protein_tracker.set_goal` (`goal_grams`)
- `protein_tracker.reset_user`

## Optional: YAML-Import

Falls du lieber per `configuration.yaml` definierst, werden Einträge beim Start als Config Entries importiert:

```yaml
protein_tracker:
  users:
    - id: dashboard1
      name: Detjon
      goal: 160
    - id: dashboard2
      name: Alex
      goal: 140
```

`name` ist dabei nur der Basisname. Die Integration ergänzt die Anzeigenamen automatisch
(z. B. `Detjon Protein Tracker`, `Detjon Protein Ziel`).
