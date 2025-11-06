import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import FabricationConsole from './pages/FabricationConsole';
import Projects from './pages/Projects';
import WallTerminal from './pages/WallTerminal';
import useRemoteMode from './hooks/useRemoteMode';

const App = () => {
  const [activeView, setActiveView] = useState<'dashboard' | 'projects' | 'console' | 'wall'>('dashboard');
  const remoteMode = useRemoteMode();

  const renderView = () => {
    switch (activeView) {
      case 'projects':
        return <Projects />;
      case 'console':
        return <FabricationConsole />;
      case 'wall':
        return <WallTerminal remoteMode={remoteMode} />;
      default:
        return <Dashboard remoteMode={remoteMode} />;
    }
  };

  return (
    <div className="kitty-app">
      <header>
        <h1>KITTY Control Console</h1>
        <nav>
          <button onClick={() => setActiveView('dashboard')}>Dashboard</button>
          <button onClick={() => setActiveView('projects')}>Projects</button>
          <button onClick={() => setActiveView('console')}>Fabrication Console</button>
          <button onClick={() => setActiveView('wall')}>Wall Terminal</button>
        </nav>
      </header>
      <main>{renderView()}</main>
    </div>
  );
};

export default App;
