"use client";

import { useEffect } from "react";

import { useStoredState } from "./storage";

// Light by default; dark is a choice stored on the device. THEME_BOOT runs in <head> before the first paint so a dark
// choice never flashes light; the hook keeps <html data-theme> in step afterwards.

export type Theme = "light" | "dark";
export const THEME_KEY = "tp.theme";

export const THEME_BOOT =
  `try{var t=JSON.parse(localStorage.getItem(${JSON.stringify(THEME_KEY)}));` +
  `document.documentElement.dataset.theme=t==="dark"?"dark":"light"}catch(e){}`;

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme, loaded] = useStoredState<Theme>(THEME_KEY, "light");
  useEffect(() => {
    if (loaded) document.documentElement.dataset.theme = theme;
  }, [theme, loaded]);
  return [theme, setTheme];
}
