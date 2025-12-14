import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  startIcon?: React.ReactNode;
  endIcon?: React.ReactNode;
  fullWidth?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      startIcon,
      endIcon,
      fullWidth = false,
      className = '',
      id,
      disabled,
      ...props
    },
    ref
  ) => {
    const inputId = id || React.useId();

    return (
      <div className={`${fullWidth ? 'w-full' : ''} ${className}`}>
        {label && (
          <label 
            htmlFor={inputId} 
            className="block text-xs font-medium text-gray-400 mb-1 uppercase tracking-wider"
          >
            {label}
          </label>
        )}
        
        <div className="relative group">
          {startIcon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500 group-focus-within:text-cyan-400 transition-colors">
              {startIcon}
            </div>
          )}
          
          <input
            ref={ref}
            id={inputId}
            disabled={disabled}
            className={`
              block w-full bg-black/30 border border-gray-700 rounded-lg 
              ${startIcon ? 'pl-10' : 'pl-3'} 
              ${endIcon ? 'pr-10' : 'pr-3'} 
              py-2 text-sm text-white placeholder-gray-600 
              focus:outline-none focus:border-cyan-500/50 focus:bg-black/50 focus:ring-1 focus:ring-cyan-500/20
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-all duration-200
              font-mono
              ${error ? 'border-red-500/50 focus:border-red-500 focus:ring-red-500/20' : ''}
            `}
            {...props}
          />
          
          {endIcon && (
            <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-gray-500">
              {endIcon}
            </div>
          )}
        </div>
        
        {error && (
          <p className="mt-1 text-xs text-red-400">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
