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
import useRemoteMode from './hooks/useRemoteMode';
import { useTheme } from './contexts/ThemeContext';

const App = () => {
  const [activeView, setActiveView] = useState<'dashboard' | 'projects' | 'console' | 'shell' | 'wall' | 'vision' | 'images' | 'research' | 'results' | 'iocontrol' | 'inventory' | 'intelligence' | 'cameras'>('shell');
  const remoteMode = useRemoteMode();
  const { theme, toggleTheme } = useTheme();

  const renderView = () => {
    switch (activeView) {
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
      default:
        return <Dashboard remoteMode={remoteMode} />;
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const viewParam = params.get('view');
    if (viewParam === 'vision') {
      setActiveView('vision');
    } else if (viewParam === 'images') {
      setActiveView('images');
    } else if (viewParam === 'shell') {
      setActiveView('shell');
    } else if (viewParam === 'research') {
      setActiveView('research');
    } else if (viewParam === 'results') {
      setActiveView('results');
    } else if (viewParam === 'iocontrol') {
      setActiveView('iocontrol');
    } else if (viewParam === 'inventory') {
      setActiveView('inventory');
    } else if (viewParam === 'intelligence') {
      setActiveView('intelligence');
    } else if (viewParam === 'cameras') {
      setActiveView('cameras');
    }
  }, []);

  return (
    <div className="kitty-app">
      <header>
        <h1>KITTY Control Console</h1>
        <nav>
          <button onClick={() => setActiveView('shell')}>💬 Shell</button>
          <button onClick={() => setActiveView('research')}>🔬 Research</button>
          <button onClick={() => setActiveView('results')}>📊 Results</button>
          <button onClick={() => setActiveView('iocontrol')}>⚙️ I/O Control</button>
          <button onClick={() => setActiveView('inventory')}>📦 Inventory</button>
          <button onClick={() => setActiveView('intelligence')}>📊 Intelligence</button>
          <button onClick={() => setActiveView('cameras')}>📹 Cameras</button>
          <button onClick={() => setActiveView('dashboard')}>Dashboard</button>
          <button onClick={() => setActiveView('projects')}>Projects</button>
          <button onClick={() => setActiveView('console')}>Fabrication Console</button>
          <button onClick={() => setActiveView('wall')}>Wall Terminal</button>
          <button onClick={() => setActiveView('vision')}>Vision Gallery</button>
          <button onClick={() => setActiveView('images')}>Image Generator</button>
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
