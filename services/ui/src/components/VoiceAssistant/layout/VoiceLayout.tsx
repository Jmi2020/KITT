import React, { ReactNode } from 'react';

interface VoiceLayoutProps {
  sidebar?: ReactNode;
  main: ReactNode;
  controls?: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export const VoiceLayout: React.FC<VoiceLayoutProps> = ({
  sidebar,
  main,
  controls,
  header,
  footer,
  className = '',
}) => {
  return (
    <div className={`voice-layout ${className}`}>
      {/* 1. Header */}
      {header && (
        <header className="voice-header">
          {header}
        </header>
      )}

      {/* 2. Middle Body */}
      <div className="voice-body">
        
        {/* Left Sidebar */}
        {sidebar && (
          <aside className="voice-sidebar">
            {sidebar}
          </aside>
        )}

        {/* Main Content Area */}
        <main className="voice-main">
          {/* Content Wrapper */}
          <div className="voice-content">
            {main}
          </div>
          
          {/* Footer (Input) */}
          {footer && (
            <div className="voice-footer">
              {footer}
            </div>
          )}
        </main>

        {/* Right Controls Panel */}
        {controls && (
          <aside className="voice-controls">
            {controls}
          </aside>
        )}
      </div>
    </div>
  );
};