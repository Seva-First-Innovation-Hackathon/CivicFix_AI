import React from 'react';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost' | 'ai';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  icon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  icon,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-medium transition-all rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

  const sizeStyles = {
    sm: 'px-3 py-1.5 text-xs gap-1.5',
    md: 'px-4 py-2 text-sm gap-2',
    lg: 'px-6 py-3 text-base gap-2.5 shadow-sm',
  };

  const variantStyles = {
    primary: 'bg-brand-600 hover:bg-brand-700 text-white focus:ring-brand-500 shadow-sm active:bg-brand-800',
    secondary: 'bg-slate-800 hover:bg-slate-900 text-white focus:ring-slate-700 active:bg-slate-950',
    outline: 'border border-slate-300 hover:bg-slate-100 text-slate-700 focus:ring-brand-500 bg-white',
    danger: 'bg-rose-600 hover:bg-rose-700 text-white focus:ring-rose-500 active:bg-rose-800',
    ghost: 'hover:bg-slate-100 text-slate-700 focus:ring-slate-400',
    ai: 'bg-ai-600 hover:bg-ai-700 text-white focus:ring-ai-500 shadow-sm shadow-ai-200 active:bg-ai-800',
  };

  return (
    <button
      disabled={disabled || isLoading}
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {isLoading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin mr-1.5" />
          <span>Processing...</span>
        </>
      ) : (
        <>
          {icon && <span className="flex-shrink-0">{icon}</span>}
          {children}
        </>
      )}
    </button>
  );
};

