import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard';
import FabricationConsole from './pages/FabricationConsole';
import Projects from './pages/Projects';
import WallTerminal from './pages/WallTerminal';
import VisionGallery from './pages/VisionGallery';
import ImageGenerator from './pages/ImageGenerator';
import useRemoteMode from './hooks/useRemoteMode';

const App = () => {
  const [activeView, setActiveView] = useState<'dashboard' | 'projects' | 'console' | 'wall' | 'vision' | 'images'>('dashboard');
  const remoteMode = useRemoteMode();

  const renderView = () => {
    switch (activeView) {
      case 'projects':
        return <Projects />;
      case 'console':
        return <FabricationConsole />;
      case 'wall':
        return <WallTerminal remoteMode={remoteMode} />;
      case 'vision':
        return <VisionGallery />;
      case 'images':
        return <ImageGenerator />;
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
    }
  }, []);

  return (
    <div className="kitty-app">
      <header>
        <h1>KITTY Control Console</h1>
        <nav>
          <button onClick={() => setActiveView('dashboard')}>Dashboard</button>
          <button onClick={() => setActiveView('projects')}>Projects</button>
          <button onClick={() => setActiveView('console')}>Fabrication Console</button>
          <button onClick={() => setActiveView('wall')}>Wall Terminal</button>
          <button onClick={() => setActiveView('vision')}>Vision Gallery</button>
          <button onClick={() => setActiveView('images')}>Image Generator</button>
        </nav>
      </header>
      <main>{renderView()}</main>
    </div>
  );
};

export default App;
