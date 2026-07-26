/**
 * EcoFlow Power Flow Card
 * -----------------------
 * A self-contained Home Assistant Lovelace custom card. It uses a rendered
 * illustration of a house (solar roof + grid pylon + wall battery) as the
 * background, and overlays glowing amber / teal energy-flow lines with
 * "marching" dots plus live value chips for solar, grid, battery and home.
 *
 * Flow is animated with continuous CSS stroke-dashoffset so it never resets
 * when Home Assistant pushes updates. Plain custom element — no build step.
 *
 * Deploy the artwork to www (e.g. /config/www/ecoflow_house.png) so it is
 * served at /local/ecoflow_house.png (the default `image`).
 *
 * Example config:
 *   type: custom:ecoflow-power-flow-card
 *   title: Live Power Flow
 *   image: /local/ecoflow_house.png
 *   solar: sensor.stream_ultra_x_XXXX_solar_power
 *   battery: sensor.stream_ultra_x_XXXX_battery_power
 *   battery_soc: sensor.stream_ultra_x_XXXX_battery_level_precise
 *   grid: sensor.ecoflow_smart_meter_YYYY_grid_power
 *   home: sensor.stream_ultra_x_XXXX_load_power
 *   invert_battery: true   # device reports discharge as negative
 *   invert_grid: false     # set true if import/export look reversed
 *   watt_threshold: 20
 */

class EcoflowPowerFlowCard extends HTMLElement {
  static getStubConfig() {
    return {
      title: "Live Power Flow",
      image: "/local/ecoflow_house.png",
      solar: "",
      battery: "",
      battery_soc: "",
      grid: "",
      home: "",
    };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = {
      title: config.title ?? "Power Flow",
      image: config.image ?? "/local/ecoflow_house.png",
      solar: config.solar,
      battery: config.battery,
      battery_soc: config.battery_soc,
      grid: config.grid,
      home: config.home,
      invert_battery: config.invert_battery ?? false,
      invert_grid: config.invert_grid ?? false,
      watt_threshold: Number(config.watt_threshold ?? 20),
    };
    this._built = false;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 6;
  }

  // --- helpers ---------------------------------------------------------------

  _num(entityId, invert = false) {
    if (!entityId || !this._hass) return null;
    const st = this._hass.states[entityId];
    if (!st || st.state === "unavailable" || st.state === "unknown") return null;
    const v = Number(st.state);
    if (Number.isNaN(v)) return null;
    return invert ? -v : v;
  }

  _fmtW(w) {
    if (w === null) return "—";
    const a = Math.abs(w);
    if (a >= 1000) return `${(w / 1000).toFixed(2)} kW`;
    return `${Math.round(w)} W`;
  }

  // --- build (once) ----------------------------------------------------------

  _build() {
    const root = document.createElement("ha-card");
    if (this._config.title) root.setAttribute("header", this._config.title);

    const style = document.createElement("style");
    style.textContent = `
      .scene {
        position: relative;
        width: 100%;
        margin: 0 auto;
        aspect-ratio: 1448 / 1086;
        background: #22262b center/cover no-repeat;
        border-radius: 12px;
        overflow: hidden;
      }
      .scene svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }

      /* Persistent white wire with a soft coloured halo (colour = group color) */
      .wire { fill: none; stroke: #ffffff; stroke-linecap: round; stroke-width: 4;
              opacity: .55; filter: drop-shadow(0 0 5px currentColor); }

      /* TRON comet: a bright head with a fading, glowing trail that travels
         along the wire. Three stacked dashes of the SAME total length (160)
         move together — short bright head, longer dimmer tail. Colour comes
         from the group's color (currentColor) so it can change at runtime. */
      .comet { fill: none; stroke: currentColor; stroke-linecap: round;
               animation: ef-march var(--efd, 1.5s) linear infinite;
               animation-direction: var(--efdir, normal); }
      .head { stroke-width: 7;  stroke-dasharray: 12 148; opacity: 1;
              filter: drop-shadow(0 0 6px currentColor); }
      .t2   { stroke-width: 9;  stroke-dasharray: 34 126; opacity: .40;
              filter: drop-shadow(0 0 7px currentColor); }
      .t3   { stroke-width: 11; stroke-dasharray: 66  94; opacity: .16;
              filter: drop-shadow(0 0 9px currentColor); }
      .flow.idle .comet { animation: none; opacity: 0; }
      @keyframes ef-march { to { stroke-dashoffset: -160; } }

      /* Subtle vertical leader from a metric to its energy line */
      .tick { stroke: #aeb6c2; stroke-width: 2; opacity: .5; }

      /* Labels — no boxes, dark halo for legibility */
      text { paint-order: stroke; stroke: rgba(8,10,14,.85); stroke-width: 5px;
             stroke-linejoin: round; }
      .lbl  { font: 700 22px var(--paper-font-body1_-_font-family, sans-serif);
              letter-spacing: 1.5px; fill: #aab3c0; }
      .val  { font: 800 40px var(--paper-font-body1_-_font-family, sans-serif);
              fill: #ffffff; }
      .soc  { font: 700 24px var(--paper-font-body1_-_font-family, sans-serif);
              fill: #bfe8d6; }
    `;    root.appendChild(style);

    const scene = document.createElement("div");
    scene.className = "scene";
    if (this._config.image) scene.style.backgroundImage = `url("${this._config.image}")`;
    scene.innerHTML = this._svgMarkup();
    root.appendChild(scene);

    this.innerHTML = "";
    this.appendChild(root);
    this._scene = scene;
    this._svg = this.querySelector("svg");
    this._built = true;
  }

  _svgMarkup() {
    // White wires with a coloured comet running through them. The comet colour
    // comes from each group's `color` and can change at runtime (e.g. the
    // battery flow turns amber when charged from solar, cyan when from grid).
    const AMBER = "#f6a93b", CYAN = "#24d0e0";

    // Coordinates are in the 1448x1086 image space (matches house.png).
    const flow = (id, colour, d) => `
      <g id="flow-${id}" class="flow idle" style="color:${colour}">
        <path class="wire" d="${d}"/>
        <path class="comet t3"   d="${d}"/>
        <path class="comet t2"   d="${d}"/>
        <path class="comet head" d="${d}"/>
      </g>`;

    return `
    <svg viewBox="0 0 1448 1086" preserveAspectRatio="xMidYMid slice">
      <!-- ===== SOLAR: down the panel slope to the front eave ===== -->
      ${flow("solar", AMBER, "M825,300 L900,410")}

      <!-- ===== GRID: pylon base down to the house near-left ground corner ===== -->
      ${flow("grid", CYAN, "M170,550 L295,586")}

      <!-- ===== BATTERY: from the units across to the house right base ===== -->
      ${flow("batt", CYAN, "M1250,849 L1147,819")}

      <!-- ===================== METRIC CALLOUTS ===================== -->
      <!-- Two aligned rows: SOLAR + BATTERY above, GRID + HOME below.
           Each vertical leader runs from its energy line to the far edge of
           the label (top of the upper labels / bottom of the lower ones). -->

      <!-- SOLAR (top row) — leader up from the roof line top (825,300) -->
      <g>
        <line class="tick" x1="825" y1="300" x2="825" y2="128"/>
        <text class="lbl" x="837" y="150">SOLAR</text>
        <text class="val" x="837" y="190" id="ef-val-solar">—</text>
      </g>

      <!-- BATTERY (top row) — leader up, centred between battery & house (1180,839) -->
      <g>
        <line class="tick" x1="1180" y1="839" x2="1180" y2="128"/>
        <text class="lbl" x="1192" y="150" id="ef-lbl-batt">BATTERY</text>
        <text class="val" x="1192" y="190" id="ef-val-batt">—</text>
        <text class="soc" x="1192" y="222" id="ef-val-soc">—</text>
      </g>

      <!-- GRID (bottom row) — leader down, centred between pylon & house (240,570) -->
      <g>
        <line class="tick" x1="240" y1="570" x2="240" y2="1030"/>
        <text class="lbl" x="252" y="978" id="ef-lbl-grid">GRID</text>
        <text class="val" x="252" y="1018" id="ef-val-grid">—</text>
      </g>

      <!-- HOME (bottom row) — leader down from the house base (815,880) -->
      <g>
        <line class="tick" x1="815" y1="880" x2="815" y2="1030"/>
        <text class="lbl" x="827" y="978">HOME</text>
        <text class="val" x="827" y="1018" id="ef-val-home">—</text>
      </g>
    </svg>`;
  }

  // --- per-update render -----------------------------------------------------

  _render() {
    if (!this._config || !this._hass) return;
    if (!this._built) this._build();

    const c = this._config;
    const solar = this._num(c.solar);
    const grid = this._num(c.grid, c.invert_grid);
    const batt = this._num(c.battery, c.invert_battery);
    const home = this._num(c.home);
    const soc = this._num(c.battery_soc);

    this._setText("ef-val-solar", this._fmtW(solar));
    // Grid & battery show magnitude; the IMPORT/EXPORT & CHARGE/DISCHARGE
    // labels carry the direction (matches the EcoFlow app, avoids a stray "-").
    this._setText("ef-val-grid", this._fmtW(grid === null ? null : Math.abs(grid)));
    this._setText("ef-val-batt", this._fmtW(batt === null ? null : Math.abs(batt)));
    this._setText("ef-val-home", this._fmtW(home));
    this._setText("ef-val-soc", soc === null ? "" : `${soc.toFixed(0)}%`);

    const thr = c.watt_threshold;
    this._setText("ef-lbl-grid", grid === null ? "GRID" : grid > thr ? "IMPORT" : grid < -thr ? "EXPORT" : "GRID");
    this._setText("ef-lbl-batt", batt === null ? "BATTERY" : batt > thr ? "DISCHARGE" : batt < -thr ? "CHARGE" : "BATTERY");

    const AMBER = "#f6a93b", CYAN = "#24d0e0";

    // Battery comet colour = charge source: solar-charged => amber, grid-charged
    // => cyan. When charging (batt < -thr) and the grid is importing, credit the
    // grid; otherwise (surplus solar) credit solar. Discharging stays cyan.
    let battColour = CYAN;
    if (batt !== null && batt < -thr) {
      battColour = (grid !== null && grid > thr) ? CYAN : AMBER;
    }

    // Flow direction: 1 = source -> home, -1 = home -> source, 0 = idle.
    this._flow("flow-solar", solar, solar !== null && solar > thr ? 1 : 0);
    this._flow("flow-grid", grid, grid === null ? 0 : grid > thr ? 1 : grid < -thr ? -1 : 0);
    this._flow("flow-batt", batt, batt === null ? 0 : batt > thr ? 1 : batt < -thr ? -1 : 0, battColour);
  }

  _setText(id, text) {
    const el = this._svg?.getElementById(id);
    if (el) el.textContent = text;
  }

  /**
   * Drive a flow's TRON comet. All three trail layers share the group's
   * --efd (duration) and --efdir (direction) CSS variables, so they move
   * together. Continuous stroke-dashoffset animation => no jump-back on
   * Home Assistant re-renders.
   *  dir: 1 = forward (source -> home), -1 = reverse, 0 = idle.
   *  colour: optional comet colour (e.g. battery charge source).
   */
  _flow(id, value, dir, colour) {
    const el = this._svg?.getElementById(id);
    if (!el) return;
    if (colour) el.style.color = colour;
    if (dir === 0) {
      el.classList.add("idle");
      return;
    }
    el.classList.remove("idle");
    // Speed: faster with more power (0.9s fast .. 2.4s slow).
    const mag = Math.abs(value ?? 0);
    const dur = Math.max(0.9, 2.4 - Math.min(3, mag / 1000) * 0.5);
    el.style.setProperty("--efd", `${dur}s`);
    el.style.setProperty("--efdir", dir === -1 ? "reverse" : "normal");
  }
}

customElements.define("ecoflow-power-flow-card", EcoflowPowerFlowCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ecoflow-power-flow-card",
  name: "EcoFlow Power Flow Card",
  description: "Illustrated house power-flow scene with animated solar/grid/battery energy flows.",
  preview: false,
});

console.info("%c ECOFLOW-POWER-FLOW-CARD %c loaded ", "background:#f6a93b;color:#000;border-radius:3px 0 0 3px", "background:#333;color:#fff;border-radius:0 3px 3px 0");
