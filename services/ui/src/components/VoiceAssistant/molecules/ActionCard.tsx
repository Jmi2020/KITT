import { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { colors } from '../../../design-system/tokens';

interface ActionCardProps {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  children?: ReactNode;
  onClick?: () => void;
  isActive?: boolean;
  className?: string;
}

export const ActionCard = ({ 
  title, 
  subtitle, 
  icon, 
  children, 
  onClick, 
  isActive = false,
  className = '' 
}: ActionCardProps) => {
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className={`
        relative overflow-hidden rounded-xl border p-4 cursor-pointer transition-colors
        ${isActive 
          ? 'bg-cyan-900/20 border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.15)]' 
          : 'bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20'}
        ${className}
      `}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          {icon && (
            <div className={`p-2 rounded-lg ${isActive ? 'bg-cyan-500/20 text-cyan-400' : 'bg-white/10 text-gray-400'}`}>
              {icon}
            </div>
          )}
          <div>
            <h3 className={`font-semibold text-sm ${isActive ? 'text-white' : 'text-gray-200'}`}>
              {title}
            </h3>
            {subtitle && (
              <p className="text-xs text-gray-500 mt-0.5 font-medium uppercase tracking-wide">
                {subtitle}
              </p>
            )}
          </div>
        </div>
      </div>
      {children && <div className="mt-3">{children}</div>}
    </motion.div>
  );
};
