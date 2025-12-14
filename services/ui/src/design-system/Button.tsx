import React from 'react';
import { colors } from './tokens';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'filled' | 'outlined' | 'ghost' | 'icon';
  color?: 'primary' | 'secondary' | 'error' | 'surface';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  glow?: boolean;
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = 'filled',
      color = 'primary',
      size = 'md',
      fullWidth = false,
      glow = false,
      isLoading = false,
      className = '',
      disabled,
      ...props
    },
    ref
  ) => {
    // Size Styles
    const sizeStyles = {
      sm: 'px-3 py-1.5 text-xs rounded-lg',
      md: 'px-5 py-2.5 text-sm rounded-xl',
      lg: 'px-8 py-4 text-base rounded-2xl',
    };

    // Color Maps (Using Token Values)
    const colorMap = {
      primary: {
        text: 'text-zinc-950',
        bg: colors.primary.DEFAULT,
        hover: colors.primary.hover,
        border: colors.primary.DEFAULT,
      },
      secondary: {
        text: 'text-white',
        bg: '#3f3f46', // zinc-700
        hover: '#52525b', // zinc-600
        border: '#52525b',
      },
      error: {
        text: 'text-white',
        bg: colors.status.error,
        hover: '#ef4444',
        border: colors.status.error,
      },
      surface: {
        text: 'text-zinc-400 hover:text-zinc-100',
        bg: 'transparent',
        hover: 'rgba(255,255,255,0.05)',
        border: 'rgba(255,255,255,0.1)',
      }
    };
    
    const theme = colorMap[color] || colorMap.primary;

    // Variant Styles
    const variantStyles = {
      filled: `bg-[${theme.bg}] text-[${theme.text}] shadow-lg hover:shadow-xl border-transparent`,
      outlined: `bg-transparent border border-[${theme.border}] text-[${theme.text === 'text-zinc-950' ? 'text-zinc-200' : theme.text}] hover:bg-[${theme.hover}] hover:text-white`,
      ghost: `bg-transparent border-transparent ${theme.text} hover:bg-[${theme.hover}]`,
      icon: `p-2 rounded-full aspect-square flex items-center justify-center ${theme.text} hover:bg-white/10`,
    };

    // Custom overrides for specific combinations
    let finalVariantStyle = variantStyles[variant];
    
    if (variant === 'filled') {
       if (color === 'primary') finalVariantStyle = `bg-teal-400 text-zinc-950 hover:bg-teal-300 shadow-lg shadow-teal-900/20`;
       if (color === 'error') finalVariantStyle = `bg-red-500 text-white hover:bg-red-400 shadow-lg shadow-red-900/20`;
       if (color === 'surface') finalVariantStyle = `bg-zinc-800 text-zinc-300 hover:bg-zinc-700 border border-white/5`;
    }
    
    if (variant === 'outlined') {
        if (color === 'primary') finalVariantStyle = `border border-teal-500/30 text-teal-400 hover:bg-teal-500/10`;
        if (color === 'surface') finalVariantStyle = `border border-white/10 text-zinc-400 hover:text-zinc-200 hover:bg-white/5`;
    }

    if (variant === 'ghost') {
        finalVariantStyle = `text-zinc-400 hover:text-zinc-100 hover:bg-white/5`;
    }

    // Glow Effect
    const glowStyle = glow && color === 'primary' ? `shadow-[0_0_20px_rgba(45,212,191,0.3)]` : '';

    return (
      <button
        ref={ref}
        className={`
          inline-flex items-center justify-center font-semibold tracking-wide transition-all duration-200
          disabled:opacity-50 disabled:cursor-not-allowed
          ${sizeStyles[size]}
          ${finalVariantStyle}
          ${glowStyle}
          ${fullWidth ? 'w-full' : ''}
          ${className}
        `}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading ? 'Loading...' : children}
      </button>
    );
  }
);

Button.displayName = 'Button';