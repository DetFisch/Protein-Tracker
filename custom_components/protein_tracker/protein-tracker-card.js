const PT_CARD_VERSION = "2.14.6"
const PT_DEFAULT_TITLE = "Protein Tracker"
const PT_PROGRESS_HEIGHT = 32


const PT_METRICS = {
  protein: {
    label: "Protein",
    unit: "g",
    displayDecimals: 1,
    entitySuffix: "_protein",
    legacySensorPattern: /^sensor\.protein_tracker_([a-z0-9_]+)_today(?:_[0-9]+)?$/i,
    legacyGoalPattern: /^number\.protein_tracker_([a-z0-9_]+)_goal(?:_[0-9]+)?$/i,
    directService: "add_protein",
    directField: "grams",
    foodService: "add_food",
    foodField: "protein_per_100g",
    goalService: "set_goal",
    goalField: "goal_grams",
    resetService: "reset_user",
    undoService: "undo_last"
  },
  calories: {
    label: "Kalorien",
    unit: "kcal",
    displayDecimals: 0,
    entitySuffix: "_calories",
    legacySensorPattern: /^sensor\.protein_tracker_([a-z0-9_]+)_calories(?:_[0-9]+)?$/i,
    legacyGoalPattern: /^number\.protein_tracker_([a-z0-9_]+)_(?:calorie_goal|calories_goal|calories)(?:_[0-9]+)?$/i,
    directService: "add_calories",
    directField: "calories",
    foodService: "add_calorie_food",
    foodField: "calories_per_100g",
    goalService: "set_calorie_goal",
    goalField: "goal_calories",
    resetService: "reset_calories",
    undoService: "undo_last"
  }
}

class ProteinTrackerCard extends HTMLElement {
  setConfig(config) {
    const baseEntity = config.entity || config.protein_entity || this._defaultProteinEntity(config.user_id)
    const normalized = this._normalizeEntities(baseEntity, config.calorie_entity)

    this._config = {
      name: config.name || PT_DEFAULT_TITLE,
      entity: normalized.protein,
      calorie_entity: normalized.calories,
      goal_entity: config.goal_entity || this._deriveGoalEntity(normalized.protein, "protein"),
      calorie_goal_entity: config.calorie_goal_entity || this._deriveGoalEntity(normalized.calories, "calories"),
      goal_entity_explicit: Boolean(config.goal_entity),
      calorie_goal_entity_explicit: Boolean(config.calorie_goal_entity)
    }
  }

  set hass(hass) {
    this._hass = hass

    if (!this._root) {
      this._renderSkeleton()
      this._attachCardEvents()
      this._renderDialog()
      this._attachDialogEvents()
    }

    this._multipleCandidates = false
    if (!this._config.entity) {
      const candidates = this._trackerEntities()
      if (candidates.length === 1) {
        this._config.entity = candidates[0]
      } else if (candidates.length > 1) {
        this._multipleCandidates = true
      }
    }

    this._syncConfiguredEntities()
    this._renderState()
  }

  getCardSize() {
    return 4
  }

  _defaultProteinEntity(userId) {
    if (!userId) {
      return null
    }

    return `sensor.${userId}_protein`
  }

  _normalizeEntities(baseEntity, calorieEntity) {
    if (baseEntity && this._hasEntitySuffix(baseEntity, PT_METRICS.calories.entitySuffix)) {
      return {
        protein: this._deriveSiblingEntity(baseEntity, "protein"),
        calories: calorieEntity || baseEntity
      }
    }

    return {
      protein: baseEntity,
      calories: calorieEntity || this._deriveSiblingEntity(baseEntity, "calories")
    }
  }

  _syncConfiguredEntities() {
    this._config.entity = this._migrateEntityId(this._config.entity, "protein")
    this._config.calorie_entity = this._migrateEntityId(
      this._config.calorie_entity || this._deriveSiblingEntity(this._config.entity, "calories"),
      "calories"
    )

    if (!this._config.goal_entity_explicit) {
      this._config.goal_entity = this._deriveGoalEntity(this._config.entity, "protein")
    } else {
      this._config.goal_entity = this._migrateGoalEntityId(this._config.goal_entity, "protein")
    }

    if (!this._config.calorie_goal_entity_explicit) {
      this._config.calorie_goal_entity = this._deriveGoalEntity(this._config.calorie_entity, "calories")
    } else {
      this._config.calorie_goal_entity = this._migrateGoalEntityId(this._config.calorie_goal_entity, "calories")
    }
  }

  _migrateEntityId(entity, metricKey) {
    if (!entity) {
      return entity
    }

    if (this._hass?.states?.[entity]) {
      return entity
    }

    const metric = PT_METRICS[metricKey]
    const legacyMatch = metric.legacySensorPattern.exec(entity)
    if (legacyMatch) {
      const migrated = `sensor.${legacyMatch[1]}${metric.entitySuffix}`
      if (!this._hass || this._hass.states[migrated]) {
        return migrated
      }
    }

    const simple = /^sensor\.([a-z0-9_]+?)(?:_(?:protein|calories))?(?:_[0-9]+)?$/i.exec(entity)
    if (simple) {
      const migrated = `sensor.${simple[1]}${metric.entitySuffix}`
      if (!this._hass || this._hass.states[migrated]) {
        return migrated
      }
    }

    return entity
  }

  _migrateGoalEntityId(entity, metricKey) {
    if (!entity) {
      return entity
    }

    if (this._hass?.states?.[entity]) {
      return entity
    }

    const metric = PT_METRICS[metricKey]
    const legacyMatch = metric.legacyGoalPattern.exec(entity)
    if (legacyMatch) {
      const migrated = `number.${legacyMatch[1]}${metric.entitySuffix}`
      if (!this._hass || this._hass.states[migrated]) {
        return migrated
      }
    }

    const simple = /^number\.([a-z0-9_]+?)(?:_(?:protein|calories|goal|protein_goal|calorie_goal|calories_goal))?(?:_[0-9]+)?$/i.exec(entity)
    if (simple && !this._hasEntitySuffix(entity, PT_METRICS.protein.entitySuffix) && !this._hasEntitySuffix(entity, PT_METRICS.calories.entitySuffix)) {
      const migrated = `number.${simple[1]}${metric.entitySuffix}`
      if (!this._hass || this._hass.states[migrated]) {
        return migrated
      }
    }

    return entity
  }

  _trackerEntities() {
    if (!this._hass) {
      return []
    }

    const entities = []
    for (const [entityId, state] of Object.entries(this._hass.states || {})) {
      if (!entityId.startsWith("sensor.")) {
        continue
      }

      const userId = state?.attributes?.user_id
      if (typeof userId !== "string" || userId.length === 0) {
        continue
      }

      const trackerType = state?.attributes?.tracker_type
      if (trackerType === "calories" || this._hasEntitySuffix(entityId, PT_METRICS.calories.entitySuffix)) {
        continue
      }

      entities.push(this._migrateEntityId(entityId, "protein"))
    }

    return [...new Set(entities)]
  }

  _deriveSiblingEntity(entity, metricKey) {
    if (!entity) {
      return null
    }

    const metric = PT_METRICS[metricKey]
    const legacyMatch = metric.legacySensorPattern.exec(entity)
    if (legacyMatch) {
      return `sensor.${legacyMatch[1]}${metric.entitySuffix}`
    }

    const proteinLegacy = PT_METRICS.protein.legacySensorPattern.exec(entity)
    if (proteinLegacy) {
      return `sensor.${proteinLegacy[1]}${metric.entitySuffix}`
    }

    const caloriesLegacy = PT_METRICS.calories.legacySensorPattern.exec(entity)
    if (caloriesLegacy) {
      return `sensor.${caloriesLegacy[1]}${metric.entitySuffix}`
    }

    const simple = /^sensor\.([a-z0-9_]+?)(?:_(?:protein|calories))?(?:_[0-9]+)?$/i.exec(entity)
    if (!simple) {
      return null
    }

    return `sensor.${simple[1]}${metric.entitySuffix}`
  }

  _deriveGoalEntity(entity, metricKey) {
    if (!entity) {
      return null
    }

    const metric = PT_METRICS[metricKey]
    const legacyMatch = metric.legacySensorPattern.exec(entity)
    if (legacyMatch) {
      return `number.${legacyMatch[1]}${metric.entitySuffix}`
    }

    const simple = /^sensor\.([a-z0-9_]+?)(?:_(?:protein|calories))?(?:_[0-9]+)?$/i.exec(entity)
    if (!simple) {
      return null
    }

    return `number.${simple[1]}${metric.entitySuffix}`
  }

  _hasEntitySuffix(entity, suffix) {
    return new RegExp(`${suffix}(?:_[0-9]+)?$`).test(entity || "")
  }

  _currentUserId() {
    const entities = [this._config.entity, this._config.calorie_entity]
    for (const entity of entities) {
      if (!entity) {
        continue
      }
      const userId = this._hass?.states?.[entity]?.attributes?.user_id
      if (typeof userId === "string" && userId.length > 0) {
        return userId
      }
    }
    return null
  }

  _formatValue(value, metricKey) {
    const metric = PT_METRICS[metricKey]
    const safeValue = Number.isFinite(value) ? value : 0
    return safeValue.toFixed(metric.displayDecimals)
  }

  _renderSkeleton() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
        }

        ha-card {
          cursor: pointer;
        }

        .title {
          display: none;
        }

        .summary-grid {
          display: grid;
          gap: 14px;
        }

        .metric-block {
          display: grid;
          gap: 8px;
        }

        .summary-row {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 12px;
        }

        .metric-label {
          font-size: 1.3rem;
          font-weight: var(--ha-font-weight-normal, 400);
          color: var(--primary-text-color);
        }

        .value {
          font-size: 1.3rem;
          font-weight: var(--ha-font-weight-normal, 400);
          color: var(--primary-text-color);
          white-space: nowrap;
        }

        .progress-wrap {
          width: 100%;
        }

        ha-progress-bar {
          width: 100%;
          height: ${PT_PROGRESS_HEIGHT}px;
          --progress-color: var(--primary-color);
          --mdc-linear-progress-track-height: ${PT_PROGRESS_HEIGHT}px;
          --mdc-linear-progress-active-indicator-height: ${PT_PROGRESS_HEIGHT}px;
          --paper-progress-height: ${PT_PROGRESS_HEIGHT}px;
          --ha-progress-bar-height: ${PT_PROGRESS_HEIGHT}px;
          border-radius: var(--ha-border-radius-pill, 999px);
          overflow: hidden;
        }

        ha-dialog {
          --mdc-dialog-min-width: 800px !important;
          --mdc-dialog-max-width: none !important;
          --mdc-dialog-shape-radius: var(--ha-card-border-radius, 12px);
        }

        @media (max-width: 820px) {
          ha-dialog {
            --mdc-dialog-min-width: 95vw !important;
          }
        }

        .progress-fallback {
          width: 100%;
          height: ${PT_PROGRESS_HEIGHT}px;
          background: var(--divider-color);
          border-radius: var(--ha-border-radius-pill, 999px);
          overflow: hidden;
          display: none;
        }

        .progress-fill {
          height: 100%;
          width: 0%;
          background: var(--primary-color);
          transition: width 150ms ease;
        }

        .meta {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          font-size: 0.85rem;
          color: var(--secondary-text-color);
        }

        .dialog-grid {
          display: grid;
          gap: 14px;
          padding-top: 4px;
          width: 100%;
          box-sizing: border-box;
        }

        .sensor-row > * {
          display: block;
          width: 100%;
        }

        .dialog-section {
          border: 1px solid var(--divider-color);
          border-radius: var(--ha-card-border-radius, 12px);
          padding: 10px;
          display: grid;
          gap: 10px;
          background: var(--card-background-color);
        }

        .dialog-section h4 {
          margin: 0;
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--primary-text-color);
        }

        .sensor-fallback {
          font-size: 0.85rem;
          color: var(--secondary-text-color);
        }

        .field-row {
          display: grid;
          gap: 10px;
          align-items: end;
        }

        .field-row.double {
          grid-template-columns: 1fr 1fr auto;
        }

        .field-row.triple {
          grid-template-columns: 1.2fr 1.2fr 1.2fr auto;
        }

        .action-btn {
          justify-self: end;
        }

        .dialog-footer {
          display: flex;
          gap: var(--ha-space-2, 8px);
          align-items: center;
          flex-wrap: wrap;
        }

        .status {
          min-height: 1.2em;
          font-size: 0.85rem;
          color: var(--secondary-text-color);
        }

        .status.error {
          color: var(--error-color);
        }

        @media (max-width: 760px) {
          .field-row.double,
          .field-row.triple {
            grid-template-columns: 1fr;
          }

          .action-btn {
            justify-self: start;
          }

          .meta {
            flex-direction: column;
            gap: 4px;
          }
        }
      </style>

      <ha-card id="protein-tracker-root" tabindex="0">
        <div class="card-content">
          <div id="title" class="title"></div>

          <div class="summary-grid">
            <section class="metric-block">
              <div class="summary-row">
                <span class="metric-label">Protein</span>
                <span id="protein-value" class="value"></span>
              </div>
              <div class="progress-wrap">
                <ha-progress-bar id="protein-progress" value="0"></ha-progress-bar>
                <div id="protein-progress-fallback" class="progress-fallback">
                  <div id="protein-progress-fill" class="progress-fill"></div>
                </div>
              </div>
              <div class="meta">
                <span id="protein-meta-left"></span>
                <span id="protein-meta-right"></span>
              </div>
            </section>

            <section class="metric-block">
              <div class="summary-row">
                <span class="metric-label">Kalorien</span>
                <span id="calories-value" class="value"></span>
              </div>
              <div class="progress-wrap">
                <ha-progress-bar id="calories-progress" value="0"></ha-progress-bar>
                <div id="calories-progress-fallback" class="progress-fallback">
                  <div id="calories-progress-fill" class="progress-fill"></div>
                </div>
              </div>
              <div class="meta">
                <span id="calories-meta-left"></span>
                <span id="calories-meta-right"></span>
              </div>
            </section>
          </div>
        </div>
      </ha-card>
    `

    this._root = this.querySelector("#protein-tracker-root")
  }

  _renderDialog() {
    this._dialog = document.createElement("ha-dialog")
    this._dialog.open = false
    this._dialog.innerHTML = `
      <div class="dialog-grid">
        <div id="sensor-standard" class="sensor-row"></div>

        <section class="dialog-section">
          <h4>Direkt eintragen</h4>
          <div class="field-row double">
            <ha-textfield id="input-direct-protein" type="number" step="0.1" min="0" label="Protein (g)"></ha-textfield>
            <ha-textfield id="input-direct-calories" type="number" step="0.1" min="0" label="Kalorien (kcal)"></ha-textfield>
            <ha-button id="btn-direct" class="action-btn" appearance="accent" variant="brand">Eintragen</ha-button>
          </div>
        </section>

        <section class="dialog-section">
          <h4>Über Essen berechnen</h4>
          <div class="field-row triple">
            <ha-textfield id="input-p100" type="number" step="0.1" min="0" label="Protein / 100g"></ha-textfield>
            <ha-textfield id="input-c100" type="number" step="0.1" min="0" label="Kcal / 100g"></ha-textfield>
            <ha-textfield id="input-food" type="number" step="0.1" min="0" label="Essen (g)"></ha-textfield>
            <ha-button id="btn-food" class="action-btn" appearance="accent" variant="brand">Eintragen</ha-button>
          </div>
        </section>

        <section class="dialog-section">
          <h4>Tagesziele</h4>
          <div class="field-row double">
            <ha-textfield id="input-goal-protein" type="number" step="1" min="0" label="Protein-Ziel (g)"></ha-textfield>
            <ha-textfield id="input-goal-calories" type="number" step="1" min="0" label="Kalorien-Ziel (kcal)"></ha-textfield>
            <ha-button id="btn-goal" class="action-btn" appearance="accent" variant="brand">Speichern</ha-button>
          </div>
        </section>

        <section class="dialog-section">
          <h4>Verwaltung</h4>
          <div class="dialog-footer">
            <ha-button id="btn-undo" appearance="outlined" variant="neutral">Letzten Eintrag löschen</ha-button>
            <ha-button id="btn-reset" appearance="outlined" variant="danger">Heutige Einträge zurücksetzen</ha-button>
          </div>
        </section>

        <div id="dialog-status" class="status"></div>
      </div>

      <div slot="secondaryAction">
        <ha-button id="btn-close" appearance="plain" variant="neutral">Schließen</ha-button>
      </div>
    `

    this.appendChild(this._dialog)
  }

  _attachCardEvents() {
    this._root.addEventListener("click", (ev) => {
      ev.stopPropagation()
      this._openDialog()
    })

    this._root.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault()
        ev.stopPropagation()
        this._openDialog()
      }
    })
  }

  _attachDialogEvents() {
    this._dialog.querySelector("#btn-direct").addEventListener("click", () => this._handleAddDirect())
    this._dialog.querySelector("#btn-food").addEventListener("click", () => this._handleAddFood())
    this._dialog.querySelector("#btn-goal").addEventListener("click", () => this._handleSetGoals())
    this._dialog.querySelector("#btn-undo").addEventListener("click", () => this._handleUndo())
    this._dialog.querySelector("#btn-reset").addEventListener("click", () => this._handleResetToday())
    
    this._dialog.querySelector("#btn-close").addEventListener("click", (ev) => {
      ev.stopPropagation()
      this._dialog.open = false
    })

    this._dialog.addEventListener("closed", (ev) => {
      ev.stopPropagation()
      this._dialog.open = false
    })
  }

  _openDialog() {
    if (!this._config.entity && !this._config.calorie_entity) {
      return
    }

    this._dialog.heading = this._config.name || PT_DEFAULT_TITLE
    this._syncDialogFields()
    this._setDialogStatus("", false)

    // Force style properties directly on the element
    this._dialog.style.setProperty("--mdc-dialog-min-width", "800px", "important");
    this._dialog.style.setProperty("--mdc-dialog-max-width", "none", "important");

    // Force closed state first to ensure clean open
    this._dialog.open = false
    setTimeout(() => {
      this._dialog.open = true
    }, 10)
  }

  _setProgress(metricKey, percent) {
    const progressEl = this._root.querySelector(`#${metricKey}-progress`)
    const progressFallback = this._root.querySelector(`#${metricKey}-progress-fallback`)
    const progressFill = this._root.querySelector(`#${metricKey}-progress-fill`)

    const normalized = Number.isFinite(percent) ? Math.max(0, Math.min(percent, 100)) : 0

    if (customElements.get("ha-progress-bar")) {
      progressEl.value = normalized
    }

    progressEl.style.display = "none"
    progressFallback.style.display = "block"
    progressFill.style.width = `${normalized}%`
  }

  _updateSensorPreview() {
    if (!this._dialog) {
      return
    }

    const host = this._dialog.querySelector("#sensor-standard")
    if (!host) {
      return
    }

    const entities = [this._config.entity, this._config.calorie_entity].filter(Boolean)
    if (entities.length === 0) {
      host.innerHTML = '<div class="sensor-fallback">Keine Tracker-Entity ausgewählt.</div>'
      return
    }

    const EntitiesCard = customElements.get("hui-entities-card")
    if (EntitiesCard) {
      if (!this._sensorPreview || this._sensorPreview.tagName.toLowerCase() !== "hui-entities-card") {
        host.innerHTML = ""
        this._sensorPreview = document.createElement("hui-entities-card")
        host.appendChild(this._sensorPreview)
        this._sensorPreviewKey = ""
      }

      const previewKey = entities.join("|")
      if (this._sensorPreviewKey !== previewKey) {
        this._sensorPreview.setConfig({
          type: "entities",
          entities: entities.map((entity) => ({ entity })),
          show_header_toggle: false,
          state_color: true
        })
        this._sensorPreviewKey = previewKey
      }

      this._sensorPreview.hass = this._hass
      return
    }

    host.innerHTML = `<div class="sensor-fallback">${entities.join(" | ")}</div>`
  }

  _metricState(metricKey) {
    const metric = PT_METRICS[metricKey]
    const entity = metricKey === "protein" ? this._config.entity : this._config.calorie_entity
    const goalEntity = metricKey === "protein" ? this._config.goal_entity : this._config.calorie_goal_entity

    if (!entity) {
      return { missing: true, entity, goalEntity, reason: this._multipleCandidates ? "multiple" : "setup" }
    }

    const state = this._hass?.states?.[entity]
    if (!state) {
      return { missing: true, entity, goalEntity, reason: "entity_missing" }
    }

    const attrs = state.attributes || {}
    const today = Number.parseFloat(state.state) || 0
    const goalState = goalEntity ? this._hass.states[goalEntity] : null
    const goal = goalState ? Number.parseFloat(goalState.state) || 0 : Number.parseFloat(attrs.goal) || 0
    const remainingAttr = Number.parseFloat(attrs.remaining)
    const remaining = Number.isFinite(remainingAttr) ? remainingAttr : Math.max(goal - today, 0)
    const percent = goal > 0 ? Math.min((today / goal) * 100, 100) : 0

    return {
      missing: false,
      entity,
      goalEntity,
      today,
      goal,
      remaining,
      percent,
      metric
    }
  }

  _renderMetric(metricKey, metricState) {
    const valueEl = this._root.querySelector(`#${metricKey}-value`)
    const metaLeft = this._root.querySelector(`#${metricKey}-meta-left`)
    const metaRight = this._root.querySelector(`#${metricKey}-meta-right`)
    const metric = PT_METRICS[metricKey]

    if (metricState.missing) {
      valueEl.textContent = "-"
      this._setProgress(metricKey, 0)

      if (metricState.reason === "multiple") {
        metaLeft.textContent = "Mehrere Tracker gefunden, bitte entity in der Card setzen"
        metaRight.textContent = ""
        return
      }

      if (metricState.reason === "setup") {
        metaLeft.textContent = "Bitte Integration anlegen"
        metaRight.textContent = ""
        return
      }

      metaLeft.textContent = "Entity nicht gefunden"
      metaRight.textContent = metricState.entity || ""
      return
    }

    valueEl.textContent = `${this._formatValue(metricState.today, metricKey)} ${metric.unit}`
    this._setProgress(metricKey, metricState.percent)
    metaLeft.textContent = `${this._formatValue(metricState.today, metricKey)} / ${this._formatValue(metricState.goal, metricKey)} ${metric.unit} (${metricState.percent.toFixed(0)}%)`
    metaRight.textContent = `Rest: ${this._formatValue(metricState.remaining, metricKey)} ${metric.unit}`
  }

  _renderState() {
    this._root.querySelector("#title").textContent = this._config.name || PT_DEFAULT_TITLE
    this._renderMetric("protein", this._metricState("protein"))
    this._renderMetric("calories", this._metricState("calories"))
    this._syncDialogFields()
  }

  _syncDialogFields() {
    if (!this._dialog) {
      return
    }

    this._updateSensorPreview()

    const proteinGoalState = this._metricState("protein")
    const calorieGoalState = this._metricState("calories")
    const proteinGoalInput = this._dialog.querySelector("#input-goal-protein")
    const calorieGoalInput = this._dialog.querySelector("#input-goal-calories")

    if (!proteinGoalInput.matches(":focus") && !proteinGoalState.missing) {
      proteinGoalInput.value = String(Math.round(proteinGoalState.goal))
    }

    if (!calorieGoalInput.matches(":focus") && !calorieGoalState.missing) {
      calorieGoalInput.value = String(Math.round(calorieGoalState.goal))
    }
  }

  _readOptionalNumber(input, { allowZero = false } = {}) {
    const raw = String(input.value || "").trim()
    if (!raw) {
      return { provided: false, valid: true, value: null }
    }

    const value = Number.parseFloat(raw)
    const valid = Number.isFinite(value) && (allowZero ? value >= 0 : value > 0)
    return { provided: true, valid, value }
  }

  async _callServiceRaw(metricKey, service, payload) {
    const data = { ...payload }
    const entity = metricKey === "protein" ? this._config.entity : this._config.calorie_entity

    if (entity) {
      data.entity_id = entity
    }

    const userId = this._currentUserId()
    if (userId) {
      data.user_id = userId
    }

    if (!data.entity_id && !data.user_id) {
      throw new Error("Keine Tracker-Entity konfiguriert.")
    }

    await this._hass.callService("protein_tracker", service, data)
  }

  async _runActions(actions) {
    if (actions.length === 0) {
      throw new Error("Keine Werte eingetragen.")
    }

    for (const action of actions) {
      await this._callServiceRaw(action.metricKey, action.service, action.payload)
    }
  }

  async _handleAddDirect() {
    const protein = this._readOptionalNumber(this._dialog.querySelector("#input-direct-protein"))
    const calories = this._readOptionalNumber(this._dialog.querySelector("#input-direct-calories"))

    if (!protein.provided && !calories.provided) {
      this._setDialogStatus("Bitte Protein oder Kalorien eintragen.", true)
      return
    }

    if ((protein.provided && !protein.valid) || (calories.provided && !calories.valid)) {
      this._setDialogStatus("Bitte nur Werte > 0 eingeben.", true)
      return
    }

    try {
      await this._runActions([
        protein.provided
          ? { metricKey: "protein", service: PT_METRICS.protein.directService, payload: { [PT_METRICS.protein.directField]: protein.value } }
          : null,
        calories.provided
          ? { metricKey: "calories", service: PT_METRICS.calories.directService, payload: { [PT_METRICS.calories.directField]: calories.value } }
          : null
      ].filter(Boolean))

      this._dialog.querySelector("#input-direct-protein").value = ""
      this._dialog.querySelector("#input-direct-calories").value = ""
      this._setDialogStatus("", false)
    } catch (error) {
      this._setDialogStatus(`Fehler: ${error?.message || error}`, true)
    }
  }

  async _handleAddFood() {
    const food = this._readOptionalNumber(this._dialog.querySelector("#input-food"))
    const proteinPer100 = this._readOptionalNumber(this._dialog.querySelector("#input-p100"))
    const caloriesPer100 = this._readOptionalNumber(this._dialog.querySelector("#input-c100"))

    if (!food.provided || !food.valid) {
      this._setDialogStatus("Bitte eine gültige Essensmenge > 0 eingeben.", true)
      return
    }

    if (!proteinPer100.provided && !caloriesPer100.provided) {
      this._setDialogStatus("Bitte Protein / 100g oder Kcal / 100g eingeben.", true)
      return
    }

    if ((proteinPer100.provided && !proteinPer100.valid) || (caloriesPer100.provided && !caloriesPer100.valid)) {
      this._setDialogStatus("Bitte nur Werte > 0 eingeben.", true)
      return
    }

    try {
      await this._runActions([
        proteinPer100.provided
          ? {
              metricKey: "protein",
              service: PT_METRICS.protein.foodService,
              payload: {
                food_grams: food.value,
                [PT_METRICS.protein.foodField]: proteinPer100.value
              }
            }
          : null,
        caloriesPer100.provided
          ? {
              metricKey: "calories",
              service: PT_METRICS.calories.foodService,
              payload: {
                food_grams: food.value,
                [PT_METRICS.calories.foodField]: caloriesPer100.value
              }
            }
          : null
      ].filter(Boolean))

      this._dialog.querySelector("#input-food").value = ""
      this._dialog.querySelector("#input-p100").value = ""
      this._dialog.querySelector("#input-c100").value = ""
      this._setDialogStatus("", false)
    } catch (error) {
      this._setDialogStatus(`Fehler: ${error?.message || error}`, true)
    }
  }

  async _handleSetGoals() {
    const proteinGoal = this._readOptionalNumber(this._dialog.querySelector("#input-goal-protein"), { allowZero: true })
    const calorieGoal = this._readOptionalNumber(this._dialog.querySelector("#input-goal-calories"), { allowZero: true })

    if (!proteinGoal.provided && !calorieGoal.provided) {
      this._setDialogStatus("Bitte mindestens ein Ziel eingeben.", true)
      return
    }

    if ((proteinGoal.provided && !proteinGoal.valid) || (calorieGoal.provided && !calorieGoal.valid)) {
      this._setDialogStatus("Bitte gültige Ziele (>= 0) eingeben.", true)
      return
    }

    try {
      await this._runActions([
        proteinGoal.provided
          ? { metricKey: "protein", service: PT_METRICS.protein.goalService, payload: { [PT_METRICS.protein.goalField]: proteinGoal.value } }
          : null,
        calorieGoal.provided
          ? { metricKey: "calories", service: PT_METRICS.calories.goalService, payload: { [PT_METRICS.calories.goalField]: calorieGoal.value } }
          : null
      ].filter(Boolean))

      this._setDialogStatus("", false)
    } catch (error) {
      this._setDialogStatus(`Fehler: ${error?.message || error}`, true)
    }
  }

  async _handleUndo() {
    try {
      const metricKey = this._config.entity ? "protein" : "calories"
      const metric = PT_METRICS[metricKey]
      await this._callServiceRaw(metricKey, metric.undoService, {})
      this._setDialogStatus("Letzter Eintrag gelöscht.", false)
    } catch (error) {
      this._setDialogStatus(`Fehler: ${error?.message || error}`, true)
    }
  }

  async _handleResetToday() {
    try {
      await this._runActions([
        { metricKey: "protein", service: PT_METRICS.protein.resetService, payload: {} },
        { metricKey: "calories", service: PT_METRICS.calories.resetService, payload: {} }
      ])
      this._setDialogStatus("", false)
    } catch (error) {
      this._setDialogStatus(`Fehler: ${error?.message || error}`, true)
    }
  }

  _setDialogStatus(message, isError) {
    const status = this._dialog.querySelector("#dialog-status")
    status.textContent = message || ""
    status.classList.toggle("error", Boolean(isError))

    window.clearTimeout(this._statusTimer)
    if (!message || !isError) {
      return
    }

    this._statusTimer = window.setTimeout(() => {
      status.textContent = ""
      status.classList.remove("error")
    }, 2500)
  }
}

class CalorieTrackerCard extends ProteinTrackerCard {}

if (!customElements.get("protein-tracker-card")) {
  customElements.define("protein-tracker-card", ProteinTrackerCard)
}

if (!customElements.get("calorie-tracker-card")) {
  customElements.define("calorie-tracker-card", CalorieTrackerCard)
}

window.customCards = window.customCards || []

if (!window.customCards.some((card) => card.type === "protein-tracker-card")) {
  window.customCards.push({
    type: "protein-tracker-card",
    name: "Protein Tracker Card",
    description: `Combined protein and calorie tracker card (${PT_CARD_VERSION})`
  })
}
