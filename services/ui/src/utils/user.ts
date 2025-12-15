const STORAGE_KEY = 'kitty_user_id';

export const generateId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback: Generate UUID v4 format for non-secure contexts
  const hex = () => Math.floor(Math.random() * 16).toString(16);
  const hex4 = () => hex() + hex() + hex() + hex();
  const hex8 = () => hex4() + hex4();
  // UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
  // y is 8, 9, a, or b
  const y = ['8', '9', 'a', 'b'][Math.floor(Math.random() * 4)];
  return `${hex8()}-${hex4()}-4${hex4().slice(1)}-${y}${hex4().slice(1)}-${hex8()}${hex4()}`;
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
