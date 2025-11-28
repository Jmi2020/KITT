# KITTY UI Design System

This document captures the design patterns and styling conventions used in the KITTY UI, starting with the Voice Mode SettingsDrawer as the reference implementation.

## Design Philosophy

**Sci-Fi Glassmorphism**: The KITTY UI uses a futuristic aesthetic combining:
- Frosted glass effects (backdrop blur)
- Glowing accent colors
- Animated borders and transitions
- Dark backgrounds with translucent overlays

---

## Color Palette

### Mode-Specific Colors

Each mode in KITTY has a dedicated color theme:

```typescript
const colorValues = {
  cyan: {
    bg: 'rgba(34, 211, 238, 0.15)',      // Background tint
    border: 'rgba(34, 211, 238, 0.5)',   // Border color
    accent: '#22d3ee',                    // Solid accent
    glow: '0 0 20px rgba(34, 211, 238, 0.3)'  // Box shadow glow
  },
  orange: {
    bg: 'rgba(249, 115, 22, 0.15)',
    border: 'rgba(249, 115, 22, 0.5)',
    accent: '#f97316',
    glow: '0 0 20px rgba(249, 115, 22, 0.3)'
  },
  purple: {
    bg: 'rgba(168, 85, 247, 0.15)',
    border: 'rgba(168, 85, 247, 0.5)',
    accent: '#a855f7',
    glow: '0 0 20px rgba(168, 85, 247, 0.3)'
  },
  green: {
    bg: 'rgba(34, 197, 94, 0.15)',
    border: 'rgba(34, 197, 94, 0.5)',
    accent: '#22c55e',
    glow: '0 0 20px rgba(34, 197, 94, 0.3)'
  },
  pink: {
    bg: 'rgba(236, 72, 153, 0.15)',
    border: 'rgba(236, 72, 153, 0.5)',
    accent: '#ec4899',
    glow: '0 0 20px rgba(236, 72, 153, 0.3)'
  }
};
```

### Neutral Colors

| Purpose | Value | Usage |
|---------|-------|-------|
| Unselected border | `rgba(255, 255, 255, 0.15)` | Card borders in default state |
| Hover border | `rgba(255, 255, 255, 0.3)` | Card borders on hover |
| Unselected background | `rgba(255, 255, 255, 0.05)` | Card background default |
| Hover background | `rgba(255, 255, 255, 0.1)` | Card background on hover |
| Text primary | `#ffffff` / `#e5e7eb` | Headings, selected text |
| Text secondary | `#d1d5db` / `#9ca3af` | Descriptions, labels |
| Text muted | `#6b7280` | Disabled, tertiary info |

---

## Component Patterns

### Selection Card (ModeCard Pattern)

Used for: Mode selection, option lists, feature toggles

**Structure:**
```
┌─────────────────────────────────────────┐
│ ▌ [Icon]  Title  [Badge]  [Active]    > │
│ ▌         Description text              │
│ ▌         [tag] [tag] [tag]             │
└─────────────────────────────────────────┘
```

**Styling:**

```typescript
// Card container
const cardStyle = {
  width: '100%',
  padding: '16px',
  borderRadius: '12px',
  border: isSelected
    ? `2px solid ${colors.border}`
    : '2px solid rgba(255, 255, 255, 0.15)',
  backgroundColor: isSelected
    ? colors.bg
    : 'rgba(255, 255, 255, 0.05)',
  boxShadow: isSelected ? colors.glow : 'none',
  transition: 'all 200ms ease',
  marginBottom: '12px',  // Spacing between cards
  textAlign: 'left',
  position: 'relative',
  overflow: 'hidden',
  cursor: 'pointer',
};

// Hover effects (via onMouseEnter/Leave)
onMouseEnter: () => {
  if (!isSelected) {
    el.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
    el.style.borderColor = 'rgba(255, 255, 255, 0.3)';
    el.style.transform = 'scale(1.02)';
  }
}
```

**Selected State Indicator (Left Accent Bar):**
```typescript
{isSelected && (
  <div style={{
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: '4px',
    background: `linear-gradient(to bottom, ${colors.accent}, ${colors.accent}dd)`,
    borderRadius: '12px 0 0 12px',
  }} />
)}
```

**Icon Container:**
```typescript
const iconStyle = {
  width: '48px',
  height: '48px',
  borderRadius: '12px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '24px',
  flexShrink: 0,
  background: isSelected
    ? `linear-gradient(135deg, ${colors.accent}, ${colors.accent}aa)`
    : 'rgba(255, 255, 255, 0.1)',
  boxShadow: isSelected ? '0 4px 12px rgba(0,0,0,0.3)' : 'none',
};
```

---

### Badge Components

**Paid Badge:**
```typescript
const paidBadgeStyle = {
  padding: '2px 8px',
  fontSize: '10px',
  fontWeight: 700,
  background: 'linear-gradient(135deg, rgba(251, 191, 36, 0.3), rgba(249, 115, 22, 0.3))',
  color: '#fcd34d',
  borderRadius: '9999px',
  border: '1px solid rgba(251, 191, 36, 0.4)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};
// Content: "💰 Paid"
```

**Active Badge:**
```typescript
const activeBadgeStyle = {
  padding: '2px 8px',
  fontSize: '11px',
  fontWeight: 500,
  background: 'rgba(34, 197, 94, 0.2)',
  color: '#4ade80',
  borderRadius: '9999px',
  border: '1px solid rgba(34, 197, 94, 0.3)',
  display: 'flex',
  alignItems: 'center',
  gap: '4px',
};
// Include pulsing dot indicator
```

**Tool Tag:**
```typescript
const toolTagStyle = {
  padding: '4px 8px',
  fontSize: '11px',
  borderRadius: '6px',
  background: isSelected
    ? 'rgba(255,255,255,0.1)'
    : 'rgba(255,255,255,0.05)',
  color: isSelected ? '#e5e7eb' : '#9ca3af',
  border: `1px solid ${isSelected
    ? 'rgba(255,255,255,0.15)'
    : 'rgba(255,255,255,0.08)'}`,
};
```

---

### Drawer/Modal Pattern

**Critical: Use Inline Styles for Portal Content**

When using React Portals (`createPortal`), Tailwind classes may not apply correctly. Always use inline styles for positioning:

```typescript
// Backdrop
<div
  onClick={onClose}
  style={{
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    backdropFilter: 'blur(8px)',
    WebkitBackdropFilter: 'blur(8px)',
    zIndex: 9998,
    opacity: isOpen ? 1 : 0,
    visibility: isOpen ? 'visible' : 'hidden',
    transition: 'opacity 300ms, visibility 300ms',
  }}
/>

// Drawer Panel
<div
  role="dialog"
  aria-modal="true"
  style={{
    position: 'fixed',
    right: 0,
    top: 0,
    height: '100vh',
    width: '384px',
    maxWidth: '95vw',
    zIndex: 9999,
    transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
    transition: 'transform 300ms ease-out',
  }}
>
```

**Glassmorphism Background:**
```typescript
// Apply inside drawer panel
<div className="absolute inset-0 bg-gradient-to-br from-gray-900/98 via-gray-900/95 to-gray-800/98 backdrop-blur-xl" />
```

**Animated Gradient Border:**
```typescript
<div
  className="absolute inset-y-0 left-0 w-[2px] bg-gradient-to-b from-cyan-400 via-purple-500 to-cyan-400 opacity-80"
  style={{
    backgroundSize: '100% 200%',
    animation: 'gradient-shift 3s ease infinite'
  }}
/>

// Required CSS keyframes
@keyframes gradient-shift {
  0%, 100% { background-position: 0% 0%; }
  50% { background-position: 0% 100%; }
}
```

---

### Button Patterns

**Settings/Mode Button:**
```typescript
<button
  className={`flex items-center gap-2 px-3 py-2 rounded-xl ${colors.bg} border ${colors.border} hover:scale-105 active:scale-95 transition-all duration-200 group`}
>
  <span className="text-lg">{icon}</span>
  <span className={`text-sm font-medium ${colors.text}`}>{label}</span>
  {/* Gear icon with rotation on hover */}
  <svg className="w-4 h-4 text-gray-400 group-hover:text-white group-hover:rotate-90 transition-all duration-300" />
</button>
```

**Close Button:**
```typescript
<button
  onClick={onClose}
  className="w-10 h-10 rounded-xl bg-white/5 hover:bg-red-500/20 border border-white/10 hover:border-red-500/50 flex items-center justify-center transition-all duration-200 text-gray-400 hover:text-red-400 hover:scale-105 active:scale-95"
>
  <svg className="w-5 h-5">
    <path d="M6 18L18 6M6 6l12 12" />
  </svg>
</button>
```

---

## Spacing & Layout

| Element | Value | Notes |
|---------|-------|-------|
| Card padding | `16px` | Internal card padding |
| Card margin | `12px` (bottom) | Space between cards |
| Card border radius | `12px` | Rounded corners |
| Icon size | `48px × 48px` | Square icon containers |
| Icon border radius | `12px` | Matches card radius |
| Badge padding | `2px 8px` | Compact pills |
| Tag padding | `4px 8px` | Slightly larger for readability |
| Content gap | `16px` | Between icon and text |
| Tag gap | `6px` | Between tool tags |
| Drawer width | `384px` | Fixed width (max 95vw) |
| Header/Footer padding | `20px` (`p-5`) | Drawer sections |

---

## Animation Guidelines

| Effect | Duration | Easing | Usage |
|--------|----------|--------|-------|
| Hover scale | `200ms` | `ease` | Cards, buttons |
| Color transitions | `200ms` | `ease` | Borders, backgrounds |
| Drawer slide | `300ms` | `ease-out` | Open/close |
| Backdrop fade | `300ms` | linear | Opacity, visibility |
| Gear rotation | `300ms` | default | Settings icon hover |
| Gradient shift | `3s` | `ease` | Animated borders |
| Pulse | `2s` | `infinite` | Active indicators |

---

## Accessibility Requirements

1. **ARIA roles**: Use `role="dialog"` and `aria-modal="true"` for modals
2. **Labels**: Provide `aria-label` for icon-only buttons
3. **Keyboard**: Support `Escape` to close modals
4. **Focus management**: Trap focus within open modals
5. **Body scroll**: Prevent background scroll when modal open (`document.body.style.overflow = 'hidden'`)
6. **Contrast**: Ensure text meets WCAG AA contrast ratios

---

## Implementation Checklist

When creating new components following this design system:

- [ ] Use inline styles for fixed positioning in portals
- [ ] Include 2px borders for clear visual boundaries
- [ ] Add hover effects (background, border, scale)
- [ ] Use mode-specific color values from the palette
- [ ] Include glow effects for selected states
- [ ] Add left accent bar for selected items
- [ ] Implement proper spacing (12px between items)
- [ ] Include transition animations (200-300ms)
- [ ] Support keyboard navigation
- [ ] Add appropriate ARIA attributes

---

## Reference Implementation

See `services/ui/src/components/VoiceAssistant/SettingsDrawer.tsx` for the complete reference implementation of these patterns.
