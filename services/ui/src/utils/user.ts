const STORAGE_KEY = 'kitty_user_id';

export const generateId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `web-${Math.random().toString(16).slice(2, 10)}-${Date.now().toString(16)}`;
};

export const getWebUserId = (): string => {
  // Prefer explicit env for alignment with CLI (set VITE_KITTY_USER_ID to KITTY_USER_ID)
  const envId =
    import.meta.env.VITE_KITTY_USER_ID ||
    import.meta.env.VITE_USER_ID ||
    '';
  if (envId.trim()) {
    return envId.trim();
  }

  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && stored.trim()) {
      return stored.trim();
    }
    const generated = generateId();
    localStorage.setItem(STORAGE_KEY, generated);
    return generated;
  }

  return generateId();
};
