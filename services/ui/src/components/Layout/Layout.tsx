import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import { KittyBadge } from '../KittyBadge';
import './Layout.css';

interface NavItem {
  path: string;
  icon: string;
  label: string;
}

const navItems: NavItem[] = [
  { path: '/', icon: '🏠', label: 'Home' },
  { path: '/voice', icon: '🎙️', label: 'Voice' },
  { path: '/research', icon: '🔬', label: 'Research' },
  { path: '/console', icon: '🎨', label: 'Fabrication' },
  { path: '/settings', icon: '⚙️', label: 'Settings' },
];

export function Layout() {
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const isVoicePage = location.pathname === '/voice';

  return (
    <div className="kitty-app">
      <header>
        <div className="header-left">
          <NavLink to="/" className="logo-link">
            <h1>KITTY</h1>
          </NavLink>
        </div>
        <nav>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `nav-button ${isActive ? 'active' : ''}`
              }
            >
              {item.icon} {item.label}
            </NavLink>
          ))}
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            title="Toggle theme"
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </nav>
      </header>
      <main style={isVoicePage ? { padding: 0, maxWidth: 'none', margin: 0, height: 'calc(100vh - 64px)' } : undefined}>
        <Outlet />
      </main>

      {/* Floating KITTY badge - appears on all pages except Voice (which has its own with pause behavior) */}
      {!isVoicePage && (
        <KittyBadge size={80} wandering={true} wanderInterval={30000} />
      )}
    </div>
  );
}

export default Layout;
