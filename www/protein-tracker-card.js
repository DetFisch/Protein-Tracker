const PT_CARD_VERSION = "2.10.0";
const PT_DEFAULT_TITLE = "Protein Tracker";
const PT_PROGRESS_HEIGHT = 42;

class ProteinTrackerCard extends HTMLElement {
  setConfig(config) {
    const entity = config.entity || (config.user_id ? `sensor.${config.user_id}` : null);

    this._config = {
      name: config.name || PT_DEFAULT_TITLE,
      entity,
      goal_entity: config.goal_entity || this._deriveGoalEntity(entity)
    };
  }

  set hass(hass) {
    this._hass = hass;

    if (!this._root) {
      this._renderSkeleton();
      this._attachCardEvents();
      this._renderDialog();
      this._attachDialogEvents();
    }

    this._multipleCandidates = false;
    if (!this._config.entity) {
      const candidates = this._trackerEntities();
      if (candidates.length === 1) {
        this._config.entity = candidates[0];
        if (!this._config.goal_entity) {
          this._config.goal_entity = this._deriveGoalEntity(candidates[0]);
        }
      } else if (candidates.length > 1) {
        this._multipleCandidates = true;
      }
    }

    this._renderState();
  }

  getCardSize() {
    return 2;
  }

  _trackerEntities() {
    if (!this._hass) {
      return [];
    }

    const entities = [];
    for (const [entityId, state] of Object.entries(this._hass.states || {})) {
      if (!entityId.startsWith("sensor.")) {
        continue;
      }
      const userId = state?.attributes?.user_id;
      if (typeof userId === "string" && userId.length > 0) {
        entities.push(entityId);
      }
    }

    return entities;
  }

  _deriveGoalEntity(entity) {
    const legacy = /^sensor\.protein_tracker_([a-z0-9_]+)_today(?:_[0-9]+)?$/i.exec(entity || "");
    if (legacy) {
      return `number.protein_tracker_${legacy[1]}_goal`;
    }

    const simple = /^sensor\.([a-z0-9_]+?)(?:_[0-9]+)?$/i.exec(entity || "");
    if (simple) {
      return `number.${simple[1]}`;
    }

    return null;
  }

  _currentUserId() {
    if (!this._hass || !this._config.entity) {
      return null;
    }

    const state = this._hass.states[this._config.entity];
    const userId = state?.attributes?.user_id;
    if (typeof userId === "string" && userId.length > 0) {
      return userId;
    }
    return null;
  }

  _renderSkeleton() {
    this._root = document.createElement("ha-card");
    this._root.setAttribute("tabindex", "0");
    this._root.innerHTML = `
      <style>
        :host {
          display: block;
        }

        ha-card {
          cursor: pointer;
        }

        .summary-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          margin-bottom: 10px;
        }

        .title {
          font-size: var(--ha-card-header-font-size, var(--ha-font-size-2xl));
          line-height: var(--ha-line-height-expanded);
          font-weight: var(--ha-font-weight-normal);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .value {
          font-size: 1rem;
          font-weight: 500;
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
          margin-top: 8px;
          font-size: 0.85rem;
          color: var(--secondary-text-color);
          gap: 12px;
        }

        .dialog-grid {
          display: grid;
          gap: 12px;
          padding-top: 4px;
        }

        .sensor-row {
          display: block;
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
          grid-template-columns: 1fr auto;
          gap: 10px;
          align-items: end;
        }

        .field-row.double {
          grid-template-columns: 1fr 1fr auto;
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

        @media (max-width: 680px) {
          .field-row,
          .field-row.double {
            grid-template-columns: 1fr;
          }

          .action-btn {
            justify-self: start;
          }
        }
      </style>

      <div class="card-content">
        <div class="summary-row">
          <span id="title" class="title"></span>
          <span id="value" class="value"></span>
        </div>
        <div class="progress-wrap">
          <ha-progress-bar id="progress" value="0"></ha-progress-bar>
          <div id="progress-fallback" class="progress-fallback"><div id="progress-fill" class="progress-fill"></div></div>
        </div>
        <div class="meta">
          <span id="meta-left"></span>
          <span id="meta-right"></span>
        </div>
      </div>
    `;

    this.appendChild(this._root);
  }

  _renderDialog() {
    this._dialog = document.createElement("ha-dialog");
    this._dialog.open = false;
    this._dialog.innerHTML = `
      <div class="dialog-grid">
        <div id="sensor-standard" class="sensor-row"></div>

        <section class="dialog-section">
          <h4>Direkt Protein eintragen</h4>
          <div class="field-row">
            <ha-textfield id="input-direct" type="number" step="0.1" min="0" label="Protein (g)"></ha-textfield>
            <ha-button id="btn-direct" class="action-btn" appearance="accent" variant="brand">Eintragen</ha-button>
          </div>
        </section>

        <section class="dialog-section">
          <h4>Protein über Essen berechnen</h4>
          <div class="field-row double">
            <ha-textfield id="input-food" type="number" step="0.1" min="0" label="Essen (g)"></ha-textfield>
            <ha-textfield id="input-p100" type="number" step="0.1" min="0" label="Protein / 100g"></ha-textfield>
            <ha-button id="btn-food" class="action-btn" appearance="accent" variant="brand">Eintragen</ha-button>
          </div>
        </section>

        <section class="dialog-section">
          <h4>Tagesziel</h4>
          <div class="field-row">
            <ha-textfield id="input-goal" type="number" step="1" min="0" label="Ziel (g)"></ha-textfield>
            <ha-button id="btn-goal" class="action-btn" appearance="accent" variant="brand">Speichern</ha-button>
          </div>
        </section>

        <div id="dialog-status" class="status"></div>
      </div>

      <div slot="secondaryAction" class="dialog-footer">
        <ha-button id="btn-reset" appearance="outlined" variant="neutral">Heutige Einträge löschen</ha-button>
        <ha-button id="btn-close" appearance="plain" variant="neutral">Schließen</ha-button>
      </div>
    `;

    this.appendChild(this._dialog);
  }

  _attachCardEvents() {
    this._root.addEventListener("click", () => this._openDialog());

    this._root.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        this._openDialog();
      }
    });
  }

  _attachDialogEvents() {
    this._dialog.querySelector("#btn-direct").addEventListener("click", () => this._handleAddDirect());
    this._dialog.querySelector("#btn-food").addEventListener("click", () => this._handleAddFood());
    this._dialog.querySelector("#btn-goal").addEventListener("click", () => this._handleSetGoal());
    this._dialog.querySelector("#btn-reset").addEventListener("click", () => this._handleResetToday());
    this._dialog.querySelector("#btn-close").addEventListener("click", () => {
      this._dialog.open = false;
    });
  }

  _openDialog() {
    if (!this._config.entity) {
      return;
    }

    this._dialog.heading = this._config.name || PT_DEFAULT_TITLE;
    this._dialog.open = true;
    this._syncDialogFields();
    this._setDialogStatus("", false);
  }

  _setProgress(percent) {
    const progressEl = this._root.querySelector("#progress");
    const progressFallback = this._root.querySelector("#progress-fallback");
    const progressFill = this._root.querySelector("#progress-fill");

    const normalized = Number.isFinite(percent) ? Math.max(0, Math.min(percent, 100)) : 0;

    if (customElements.get("ha-progress-bar")) {
      progressEl.value = normalized;
    }

    progressEl.style.display = "none";
    progressFallback.style.display = "block";
    progressFill.style.width = `${normalized}%`;
  }

  _updateSensorPreview() {
    if (!this._dialog) {
      return;
    }

    const host = this._dialog.querySelector("#sensor-standard");
    if (!host) {
      return;
    }

    if (!this._config.entity) {
      this._sensorPreview = null;
      host.innerHTML = '<div class="sensor-fallback">Keine Tracker-Entity ausgewählt.</div>';
      return;
    }

    const SensorRow = customElements.get("hui-sensor-entity-row");
    if (SensorRow) {
      if (!this._sensorPreview || this._sensorPreview.tagName.toLowerCase() !== "hui-sensor-entity-row") {
        host.innerHTML = "";
        this._sensorPreview = document.createElement("hui-sensor-entity-row");
        host.appendChild(this._sensorPreview);
        this._sensorPreviewEntity = "";
      }

      if (this._sensorPreviewEntity !== this._config.entity) {
        this._sensorPreview.setConfig({ entity: this._config.entity });
        this._sensorPreviewEntity = this._config.entity;
      }

      this._sensorPreview.hass = this._hass;
      return;
    }

    const EntitiesCard = customElements.get("hui-entities-card");
    if (EntitiesCard) {
      if (!this._sensorPreview || this._sensorPreview.tagName.toLowerCase() !== "hui-entities-card") {
        host.innerHTML = "";
        this._sensorPreview = document.createElement("hui-entities-card");
        host.appendChild(this._sensorPreview);
        this._sensorPreviewEntity = "";
      }

      if (this._sensorPreviewEntity !== this._config.entity) {
        this._sensorPreview.setConfig({
          type: "entities",
          entities: [{ entity: this._config.entity }],
          show_header_toggle: false,
          state_color: true
        });
        this._sensorPreviewEntity = this._config.entity;
      }

      this._sensorPreview.hass = this._hass;
      return;
    }

    this._sensorPreview = null;
    host.innerHTML = `<div class="sensor-fallback">${this._config.entity}</div>`;
  }

  _renderState() {
    const titleEl = this._root.querySelector("#title");
    const valueEl = this._root.querySelector("#value");
    const metaLeft = this._root.querySelector("#meta-left");
    const metaRight = this._root.querySelector("#meta-right");

    titleEl.textContent = this._config.name || PT_DEFAULT_TITLE;

    if (!this._config.entity) {
      valueEl.textContent = "-";
      this._setProgress(0);
      metaLeft.textContent = this._multipleCandidates
        ? "Mehrere Tracker gefunden, bitte entity in der Card setzen"
        : "Bitte Integration anlegen";
      metaRight.textContent = "";
      return;
    }

    const state = this._hass.states[this._config.entity];
    if (!state) {
      valueEl.textContent = "-";
      this._setProgress(0);
      metaLeft.textContent = "Entity nicht gefunden";
      metaRight.textContent = this._config.entity;
      return;
    }

    const attrs = state.attributes || {};
    const today = Number.parseFloat(state.state) || 0;

    if (!this._config.goal_entity) {
      this._config.goal_entity = this._deriveGoalEntity(this._config.entity);
    }

    const goalState = this._config.goal_entity ? this._hass.states[this._config.goal_entity] : null;
    const goal = goalState ? Number.parseFloat(goalState.state) || 0 : Number.parseFloat(attrs.goal) || 0;
    const remainingAttr = Number.parseFloat(attrs.remaining);
    const remaining = Number.isFinite(remainingAttr) ? remainingAttr : Math.max(goal - today, 0);
    const percent = goal > 0 ? Math.min((today / goal) * 100, 100) : 0;

    valueEl.textContent = `${today.toFixed(1)} g`;
    this._setProgress(percent);
    metaLeft.textContent = `${today.toFixed(1)} / ${goal.toFixed(1)} g (${percent.toFixed(0)}%)`;
    metaRight.textContent = `Rest: ${remaining.toFixed(1)} g`;

    this._syncDialogFields();
  }

  _syncDialogFields() {
    if (!this._dialog) {
      return;
    }

    this._updateSensorPreview();

    const goalInput = this._dialog.querySelector("#input-goal");
    if (!this._config.entity) {
      return;
    }

    const state = this._hass.states[this._config.entity];
    if (!state) {
      return;
    }

    const attrs = state.attributes || {};
    const goalState = this._config.goal_entity ? this._hass.states[this._config.goal_entity] : null;
    const goal = goalState ? Number.parseFloat(goalState.state) || 0 : Number.parseFloat(attrs.goal) || 0;

    if (!goalInput.matches(":focus")) {
      goalInput.value = String(Math.round(goal));
    }
  }

  async _handleAddDirect() {
    const input = this._dialog.querySelector("#input-direct");
    const grams = Number.parseFloat(input.value);

    if (!Number.isFinite(grams) || grams <= 0) {
      this._setDialogStatus("Bitte gültige Proteinmenge eingeben.", true);
      return;
    }

    await this._callService("add_protein", { grams });
    input.value = "";
  }

  async _handleAddFood() {
    const foodInput = this._dialog.querySelector("#input-food");
    const p100Input = this._dialog.querySelector("#input-p100");

    const food_grams = Number.parseFloat(foodInput.value);
    const protein_per_100g = Number.parseFloat(p100Input.value);

    if (!Number.isFinite(food_grams) || food_grams <= 0 || !Number.isFinite(protein_per_100g) || protein_per_100g <= 0) {
      this._setDialogStatus("Bitte beide Werte > 0 eingeben.", true);
      return;
    }

    await this._callService("add_food", { food_grams, protein_per_100g });
    foodInput.value = "";
    p100Input.value = "";
  }

  async _handleSetGoal() {
    const input = this._dialog.querySelector("#input-goal");
    const goal_grams = Number.parseFloat(input.value);

    if (!Number.isFinite(goal_grams) || goal_grams < 0) {
      this._setDialogStatus("Bitte gültiges Ziel (>= 0) eingeben.", true);
      return;
    }

    await this._callService("set_goal", { goal_grams });
  }

  async _handleResetToday() {
    await this._callService("reset_user", {});
  }

  async _callService(service, payload) {
    if (!this._config.entity) {
      this._setDialogStatus("Keine Tracker-Entity konfiguriert.", true);
      return;
    }

    const data = {
      entity_id: this._config.entity,
      ...payload
    };

    const userId = this._currentUserId();
    if (userId) {
      data.user_id = userId;
    }

    try {
      await this._hass.callService("protein_tracker", service, data);
      this._setDialogStatus("", false);
    } catch (error) {
      this._setDialogStatus(`Fehler: ${error?.message || error}`, true);
    }
  }

  _setDialogStatus(message, isError) {
    const status = this._dialog.querySelector("#dialog-status");
    status.textContent = message || "";
    status.classList.toggle("error", Boolean(isError));

    window.clearTimeout(this._statusTimer);
    if (!message || !isError) {
      return;
    }

    this._statusTimer = window.setTimeout(() => {
      status.textContent = "";
      status.classList.remove("error");
    }, 2500);
  }
}

if (!customElements.get("protein-tracker-card")) {
  customElements.define("protein-tracker-card", ProteinTrackerCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "protein-tracker-card",
  name: "Protein Tracker Card",
  description: `Protein summary card with modal input (${PT_CARD_VERSION})`
});
