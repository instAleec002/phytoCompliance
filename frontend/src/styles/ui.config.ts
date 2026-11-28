// Interface switches: what the frame shows. Write "on" or "off" and rebuild; nothing else needs editing.
// Colors, fonts and shapes live next to this file, in theme.css.

type Switch = "on" | "off";

export const UI = {
  // Sidebar and page titles ---------------------------------------------------------------------------------------
  /** Glossy section icons in the sidebar and next to each page title. */
  icons: "off",
  /** Each page's reference number (01, 02, …) in the sidebar and above the page title. */
  numbers: "off",

  // Top bar -------------------------------------------------------------------------------------------------------
  /** The dot that says whether the API answers (green connected, amber connecting, red no connection). */
  connectionDot: "off",
  /** The API address next to the dot (localhost:8000 today; the cloud or desktop address later). Also in Ajustes. */
  apiAddress: "off",
  /** Since when each market can answer (EU full history; US and Codex only from their download). Also in Estado de
   *  datos. Shown only on screens wider than 1500 px. */
  marketFreshness: "off",
  /** The evaluation date picker. Off: every limit, validation and alert is computed for today, with no way to move it. */
  evaluationDate: "on",
} satisfies Record<string, Switch>;

const on = (s: Switch) => s === "on";

export const showIcons = on(UI.icons);
export const showNumbers = on(UI.numbers);
export const showConnectionDot = on(UI.connectionDot);
export const showApiAddress = on(UI.apiAddress);
export const showMarketFreshness = on(UI.marketFreshness);
export const showEvaluationDate = on(UI.evaluationDate);
