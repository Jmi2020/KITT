import { palette } from './palette';

/**
 * KITTY Design System Tokens - Modern Clean
 */

export const colors = {
  primary: {
    DEFAULT: palette.brand.primary,
    hover: '#14b8a6',   // teal-500
    active: '#0d9488',  // teal-600
    bg: 'rgba(45, 212, 191, 0.1)',
    border: 'rgba(45, 212, 191, 0.2)',
    glow: '0 0 20px rgba(45, 212, 191, 0.25)',
  },
  surface: {
    base: palette.bg.app,
    card: palette.bg.card,
    hover: '#3f3f46', // zinc-700
    border: palette.border.subtle,
  },
  text: {
    primary: palette.text.primary,
    secondary: palette.text.secondary,
    muted: palette.text.tertiary,
  },
  status: {
    success: palette.status.success,
    warning: palette.status.warning,
    error: palette.status.error,
    info: palette.status.info,
  }
};

export const typography = {
  h1: 'text-4xl font-bold tracking-tight text-zinc-100',
  h2: 'text-2xl font-semibold tracking-tight text-zinc-100',
  h3: 'text-xl font-medium tracking-normal text-zinc-200',
  body: 'text-base font-normal leading-relaxed text-zinc-300',
  caption: 'text-xs font-medium uppercase tracking-wider text-zinc-500',
  mono: 'font-mono text-sm tracking-tight',
};

export const layout = {
  maxWidth: 'max-w-7xl',
  pagePadding: 'px-6 sm:px-8 lg:px-12', // Increased padding
  cardPadding: 'p-6',
  gap: {
    sm: 'gap-3',
    md: 'gap-5',
    lg: 'gap-8',
    xl: 'gap-12',
  }
};

export const animation = {
  spring: {
    type: 'spring',
    stiffness: 300,
    damping: 30,
  },
  ease: [0.23, 1, 0.32, 1], // Cubic bezier
};
