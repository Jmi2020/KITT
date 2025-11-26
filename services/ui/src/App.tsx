import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard';
import FabricationConsole from './pages/FabricationConsole';
import Projects from './pages/Projects';
import Shell from './pages/Shell';
import WallTerminal from './pages/WallTerminal';
import VisionGallery from './pages/VisionGallery';
import ImageGenerator from './pages/ImageGenerator';
import Research from './pages/Research';
import Results from './pages/Results';
import IOControl from './pages/IOControl';
import MaterialInventory from './pages/MaterialInventory';
import PrintIntelligence from './pages/PrintIntelligence';
import VisionService from './pages/VisionService';
import AutonomyCalendar from './pages/AutonomyCalendar';
import Voice from './pages/Voice';
import Settings from './pages/Settings';
import Menu from './pages/Menu';
import useRemoteMode from './hooks/useRemoteMode';
import { useTheme } from './contexts/ThemeContext';

type ViewType = 'menu' | 'dashboard' | 'projects' | 'console' | 'shell' | 'wall' | 'vision' | 'images' | 'research' | 'results' | 'iocontrol' | 'inventory' | 'intelligence' | 'cameras' | 'calendar' | 'voice' | 'settings';

const App = () => {
  const [activeView, setActiveView] = useState<ViewType>('menu');
  const remoteMode = useRemoteMode();
  const { theme, toggleTheme } = useTheme();

  const handleNavigate = (view: string) => {
    setActiveView(view as ViewType);
  };

  const renderView = () => {
    switch (activeView) {
      case 'menu':
        return <Menu onNavigate={handleNavigate} />;
      case 'projects':
        return <Projects />;
      case 'console':
        return <FabricationConsole />;
      case 'shell':
        return <Shell />;
      case 'wall':
        return <WallTerminal remoteMode={remoteMode} />;
      case 'vision':
        return <VisionGallery />;
      case 'images':
        return <ImageGenerator />;
      case 'research':
        return <Research />;
      case 'results':
        return <Results />;
      case 'iocontrol':
        return <IOControl />;
      case 'inventory':
        return <MaterialInventory />;
      case 'intelligence':
        return <PrintIntelligence />;
      case 'cameras':
        return <VisionService />;
      case 'calendar':
        return <AutonomyCalendar />;
      case 'voice':
        return <Voice />;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard remoteMode={remoteMode} />;
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const viewParam = params.get('view');
    const validViews: ViewType[] = ['menu', 'dashboard', 'projects', 'console', 'shell', 'wall', 'vision', 'images', 'research', 'results', 'iocontrol', 'inventory', 'intelligence', 'cameras', 'calendar', 'voice', 'settings'];
    if (viewParam && validViews.includes(viewParam as ViewType)) {
      setActiveView(viewParam as ViewType);
    }
  }, []);

  return (
    <div className="kitty-app">
      <header>
        <div className="header-left">
          {activeView !== 'menu' && (
            <button className="menu-button" onClick={() => setActiveView('menu')}>
              ☰
            </button>
          )}
          <h1>KITTY</h1>
        </div>
        <nav>
          {activeView !== 'menu' && (
            <>
              <button onClick={() => setActiveView('voice')}>🎙️ Voice</button>
              <button onClick={() => setActiveView('shell')}>💬 Shell</button>
              <button onClick={() => setActiveView('console')}>🎨 Fabricate</button>
              <button onClick={() => setActiveView('dashboard')}>🖨️ Printers</button>
              <button onClick={() => setActiveView('settings')}>⚙️ Settings</button>
            </>
          )}
          <button className="theme-toggle" onClick={toggleTheme} title="Toggle theme">
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </nav>
      </header>
      <main>{renderView()}</main>
    </div>
  );
};

export default App;
