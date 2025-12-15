import { ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useWindowSize } from '../../../hooks/useWindowSize';
import { layout } from '../../../design-system/tokens';

interface MainLayoutProps {
  header: ReactNode;
  sidebar?: ReactNode;
  rightPanel?: ReactNode;
  content: ReactNode;
  bottomNav?: ReactNode;
  overlay?: ReactNode;
  className?: string;
}

export const MainLayout = ({ 
  header, 
  sidebar, 
  rightPanel,
  content, 
  bottomNav, 
  overlay,
  className = '' 
}: MainLayoutProps) => {
  const { isMobile, isDesktop } = useWindowSize();

  // Show sidebars on Tablet (>=768px) and Desktop
  const showSidebars = !isMobile;

  return (
    <div className={`relative w-full flex flex-col bg-black text-white ${className}`} style={{ height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
      {/* Background Ambience - Clean & Deep */}
      <div className="absolute inset-0 bg-gradient-to-b from-gray-950 via-black to-black pointer-events-none -z-20" />
      
      {/* Header */}
      <header className="z-40 w-full shrink-0 border-b border-white/5 bg-black/60 backdrop-blur-md h-16 flex items-center">
        {header}
      </header>

      {/* Main Layout Container (Flexbox) */}
      <div className="flex-1 flex overflow-hidden relative w-full" style={{ minHeight: 0 }}>
        
        {/* Left Sidebar (History) */}
        <AnimatePresence mode="wait">
          {sidebar && (
            <motion.aside
              initial={isMobile ? { x: -320, position: 'absolute' } : { width: 0, opacity: 0 }}
              animate={isMobile ? { x: 0, position: 'absolute' } : { width: 280, opacity: 1, position: 'relative' }}
              exit={isMobile ? { x: -320, position: 'absolute' } : { width: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
              className={`
                shrink-0 border-r border-white/5 bg-gray-900/10 backdrop-blur-sm z-30 flex flex-col overflow-hidden h-full min-h-0
                ${isMobile ? 'inset-y-0 left-0 w-80 shadow-2xl bg-black/90' : ''}
              `}
              style={{ minHeight: 0 }}
            >
              <div className="w-80 h-full flex flex-col min-h-0" style={{ minHeight: 0 }}>
                {sidebar}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Center Stage */}
        <main className="flex-1 min-w-0 min-h-0 relative h-full">
          {content}
        </main>

        {/* Right Panel (Context/Tools) */}
        <AnimatePresence mode="wait">
          {rightPanel && showSidebars && (
            <motion.aside 
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 320, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
              className="shrink-0 border-l border-white/5 bg-gray-900/10 backdrop-blur-sm z-30 flex flex-col overflow-hidden h-full"
            >
              <div className="w-80 h-full flex flex-col">
                {rightPanel}
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

      </div>

      {/* Bottom Navigation (Mobile Only) */}
      {isMobile && bottomNav && (
        <div className="z-50 shrink-0 pb-safe border-t border-white/10 bg-black/80 backdrop-blur-xl">
          {bottomNav}
        </div>
      )}

      {/* Global Overlays */}
      <AnimatePresence>
        {overlay}
      </AnimatePresence>
    </div>
  );
};