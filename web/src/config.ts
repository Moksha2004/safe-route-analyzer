const parsePositiveInt = (value: string | undefined, fallback: number): number => {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
};

export const MAX_ROUTES = Math.min(5, parsePositiveInt(import.meta.env.VITE_MAX_ROUTES, 5));
export const DEFAULT_MAX_ROUTES = Math.min(MAX_ROUTES, parsePositiveInt(import.meta.env.VITE_DEFAULT_MAX_ROUTES, 3));
export const SEARCH_DEBOUNCE_MS = parsePositiveInt(import.meta.env.VITE_SEARCH_DEBOUNCE_MS, 300);
export const MIN_SEARCH_LENGTH = parsePositiveInt(import.meta.env.VITE_MIN_SEARCH_LENGTH, 2);
