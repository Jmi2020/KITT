import { ReactNode } from 'react';
import { colors } from '../../design-system/tokens';

interface HUDFrameProps {
  children: ReactNode;
  className?: string;
  glow?: boolean;
}

/**
 * Modern Glass Card component.
 * Replaces the old HUDFrame with a cleaner, sophisticated look.
 */
export function HUDFrame({
  children,
  className = '',
  glow = false,
}: HUDFrameProps) {
  
  return (
    <div
      className={`
        relative rounded-2xl border border-white/5 
        bg-zinc-900/40 backdrop-blur-xl
        transition-all duration-300
        ${glow ? 'shadow-[0_0_30px_-5px_rgba(0,0,0,0.3)] ring-1 ring-white/10' : 'shadow-xl'}
        ${className}
      `}
    >
      {/* Subtle Top Highlight */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-50" />
      
      {/* Content */}
      <div className="relative z-10">{children}</div>
    </div>
  );
}

/**
 * Section Label - Clean Uppercase
 */
export function HUDLabel({ children, icon }: { children: ReactNode; icon?: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      {icon && <span className="text-zinc-500 text-lg">{icon}</span>}
      <span className="text-xs font-semibold tracking-widest text-zinc-500 uppercase">
        {children}
      </span>
    </div>
  );
}

/**
 * Divider - Subtle Line
 */
export function HUDDivider() {
  return <div className="h-px w-full bg-white/5 my-4" />;
}