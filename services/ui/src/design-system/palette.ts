// Modern Clean Palette - Sophisticated Dark Mode

export const palette = {
  // Backgrounds
  bg: {
    app: '#09090b',      // zinc-950 (Main app background)
    panel: '#18181b',    // zinc-900 (Sidebars, panels)
    card: '#27272a',     // zinc-800 (Cards, inputs)
    overlay: 'rgba(9, 9, 11, 0.8)', // Backdrop blur
  },
  
  // Borders
  border: {
    subtle: 'rgba(255, 255, 255, 0.08)',
    medium: 'rgba(255, 255, 255, 0.12)',
    highlight: 'rgba(255, 255, 255, 0.2)',
  },

  // Typography
  text: {
    primary: '#f4f4f5',   // zinc-100
    secondary: '#a1a1aa', // zinc-400
    tertiary: '#71717a',  // zinc-500
    inverse: '#09090b',   // zinc-950
  },

  // Brand Colors (Softer, more professional)
  brand: {
    primary: '#2dd4bf',   // teal-400 (Main Action)
    secondary: '#818cf8', // indigo-400 (Secondary Action)
    tertiary: '#f472b6',  // pink-400 (Creative)
  },

  // Functional
  status: {
    success: '#34d399', // emerald-400
    warning: '#fbbf24', // amber-400
    error: '#f87171',   // red-400
    info: '#60a5fa',    // blue-400
  },
  
  // Gradients
  gradients: {
    primary: 'from-teal-500/20 to-teal-500/0',
    glow: 'from-white/5 to-white/0',
  }
};
