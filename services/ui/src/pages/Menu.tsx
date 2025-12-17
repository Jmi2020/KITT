import { useCallback } from 'react';

interface MenuProps {
  onNavigate: (view: string) => void;
}

interface MenuItem {
  id: string;
  title: string;
  description: string;
  icon?: string;
}

const menuItems: MenuItem[] = [
  {
    id: 'voice',
    title: 'KITTY (Voice)',
    description: 'Real-time voice assistant with STT/TTS',
    icon: '🎙️',
  },
  {
    id: 'shell',
    title: 'Chat Shell',
    description: 'Text chat with function calling',
    icon: '💬',
  },
  {
    id: 'console',
    title: 'Fabrication Console',
    description: 'Text-to-3D model generation',
    icon: '🎨',
  },
  {
    id: 'projects',
    title: 'Projects',
    description: 'Manage 3D printing projects',
    icon: '📁',
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    description: 'Printers, cameras, and material inventory',
    icon: '🖨️',
  },
  {
    id: 'media',
    title: 'Media Hub',
    description: 'Vision gallery and image generation',
    icon: '🖼️',
  },
  {
    id: 'research',
    title: 'Research Hub',
    description: 'Research, results, and scheduling',
    icon: '🔬',
  },
  {
    id: 'collective',
    title: 'Collective',
    description: 'Multi-agent deliberation for better decisions',
    icon: '👥',
  },
  {
    id: 'intelligence',
    title: 'Intelligence',
    description: 'Analytics and insights dashboard',
    icon: '📈',
  },
  {
    id: 'wall',
    title: 'Wall Terminal',
    description: 'Full-screen display mode',
    icon: '🖥️',
  },
  {
    id: 'settings',
    title: 'Settings',
    description: 'Connections, preferences, and system features',
    icon: '⚙️',
  },
];

export default function Menu({ onNavigate }: MenuProps) {
  const handleNavigate = useCallback(
    (id: string) => {
      onNavigate(id);
    },
    [onNavigate]
  );

  return (
    <div className="menu-page">
      <div className="menu-grid">
        {menuItems.map((item) => (
          <div
            key={item.id}
            className="menu-card"
            onClick={() => handleNavigate(item.id)}
          >
            <div className="menu-card-header">
              {item.icon && <span className="menu-card-icon">{item.icon}</span>}
              <h3 className="menu-card-title">{item.title}</h3>
            </div>
            <p className="menu-card-description">{item.description}</p>
            <span className="menu-card-link">
              Go <span className="arrow">→</span>
            </span>
          </div>
        ))}
      </div>

      {/* KITTY Logo */}
      <div className="menu-logo">
        <div className="logo-circle">
          <span className="logo-text">K.I.T.T.Y.</span>
        </div>
      </div>

      <style>{`
        .menu-page {
          min-height: calc(100vh - 80px);
          padding: 2rem;
          position: relative;
        }

        .menu-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 1.5rem;
          max-width: 1400px;
          margin: 0 auto;
        }

        .menu-card {
          background: rgba(30, 41, 59, 0.5);
          border: 1px solid rgba(100, 116, 139, 0.3);
          border-radius: 12px;
          padding: 1.5rem;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .menu-card:hover {
          background: rgba(30, 41, 59, 0.8);
          border-color: rgba(34, 211, 238, 0.5);
          transform: translateY(-2px);
          box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
        }

        .menu-card-header {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          margin-bottom: 0.5rem;
        }

        .menu-card-icon {
          font-size: 1.25rem;
        }

        .menu-card-title {
          font-size: 1.1rem;
          font-weight: 600;
          color: #fff;
          margin: 0;
        }

        .menu-card-description {
          color: #94a3b8;
          font-size: 0.9rem;
          margin: 0 0 1rem 0;
          line-height: 1.4;
        }

        .menu-card-link {
          color: #22d3ee;
          font-size: 0.9rem;
          font-weight: 500;
          display: inline-flex;
          align-items: center;
          gap: 0.25rem;
        }

        .menu-card-link .arrow {
          transition: transform 0.2s ease;
        }

        .menu-card:hover .menu-card-link .arrow {
          transform: translateX(4px);
        }

        .menu-logo {
          position: fixed;
          bottom: 2rem;
          right: 2rem;
          pointer-events: none;
        }

        .logo-circle {
          width: 120px;
          height: 120px;
          border-radius: 50%;
          border: 2px solid rgba(34, 211, 238, 0.3);
          display: flex;
          align-items: center;
          justify-content: center;
          background: radial-gradient(circle, rgba(34, 211, 238, 0.1) 0%, transparent 70%);
          box-shadow:
            0 0 30px rgba(34, 211, 238, 0.1),
            inset 0 0 30px rgba(34, 211, 238, 0.05);
        }

        .logo-text {
          color: #22d3ee;
          font-size: 1rem;
          font-weight: 600;
          letter-spacing: 0.1em;
          text-shadow: 0 0 10px rgba(34, 211, 238, 0.5);
        }

        @media (max-width: 768px) {
          .menu-page {
            padding: 1rem;
          }

          .menu-grid {
            grid-template-columns: 1fr;
          }

          .menu-logo {
            display: none;
          }
        }
      `}</style>
    </div>
  );
}
