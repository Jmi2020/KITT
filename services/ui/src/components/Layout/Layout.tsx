import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useTheme } from '../../contexts/ThemeContext';
import './Layout.css';

interface NavItem {
  path: string;
  icon: string;
  label: string;
}

const navItems: NavItem[] = [
  { path: '/voice', icon: '🎙️', label: 'Voice' },
  { path: '/shell', icon: '💬', label: 'Shell' },
  { path: '/console', icon: '🎨', label: 'Fabricate' },
  { path: '/dashboard', icon: '🖨️', label: 'Printers' },
  { path: '/research', icon: '🔬', label: 'Research' },
  { path: '/settings', icon: '⚙️', label: 'Settings' },
];

export function Layout() {
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const isHome = location.pathname === '/';

  return (
    <div className="kitty-app">
      <header>
        <div className="header-left">
          <NavLink to="/" className="logo-link">
            <h1>KITTY</h1>
          </NavLink>
        </div>
        <nav>
          {!isHome && navItems.map((item) => (
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
      <main>
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
