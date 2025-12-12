/**
 * Dashboard - Unified monitoring hub for devices, cameras, and materials
 * Consolidates: Dashboard (MQTT devices), VisionService (cameras), MaterialInventory
 */

import { useSearchParams } from 'react-router-dom';
import { DashboardTab, DASHBOARD_TABS } from '../../types/dashboard';
import DevicesTab from './tabs/Devices';
import CamerasTab from './tabs/Cameras';
import MaterialsTab from './tabs/Materials';
import './Dashboard.css';

interface DashboardProps {
  remoteMode?: { isRemote: boolean };
}

const Dashboard = ({ remoteMode }: DashboardProps) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as DashboardTab | null;
  const activeTab: DashboardTab = tabParam && DASHBOARD_TABS.some(t => t.id === tabParam)
    ? tabParam
    : 'devices';

  const handleTabChange = (tab: DashboardTab) => {
    setSearchParams({ tab });
  };

  const isRemote = remoteMode?.isRemote ?? false;

  return (
    <div className="dashboard-hub">
      <header className="dashboard-header">
        <div className="header-content">
          <h1>System Dashboard</h1>
          <p className="header-subtitle">
            Monitor devices, cameras, and material inventory
          </p>
        </div>
        {isRemote && <span className="badge badge-warning">Remote Read-Only Mode</span>}
      </header>

      <nav className="dashboard-tabs">
        {DASHBOARD_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      <div className="dashboard-content">
        {activeTab === 'devices' && <DevicesTab remoteMode={isRemote} />}
        {activeTab === 'cameras' && <CamerasTab />}
        {activeTab === 'materials' && <MaterialsTab />}
      </div>
    </div>
  );
};

export default Dashboard;
