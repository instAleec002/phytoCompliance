"use client";

import { useEffect, useState } from "react";

// Per-device convenience storage. localStorage can be missing or throw (private windows, blocked site data), so every
// access is guarded and the interface works without it.

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable: the value lives only in memory for this session
  }
}

/** State mirrored to localStorage; reads after mount so the static export renders the same on server and client. */
export function useStoredState<T>(key: string, fallback: T): [T, (value: T | ((prev: T) => T)) => void, boolean] {
  const [value, setValue] = useState<T>(fallback);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    setValue(readStored(key, fallback));
    setLoaded(true);
  }, [key]);
  useEffect(() => {
    if (loaded) writeStored(key, value);
  }, [key, value, loaded]);
  return [value, setValue, loaded];
}
