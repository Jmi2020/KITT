/**
 * Type definitions for Dashboard - device monitoring, cameras, and materials
 */

// Device types from MQTT context
export interface Device {
  deviceId: string;
  status: 'online' | 'offline' | 'error';
  payload?: Record<string, unknown>;
  lastSeen?: number;
}

// Camera types
export interface Camera {
  camera_id: string;
  friendly_name: string;
  online: boolean;
  resolution?: string;
  fps?: number;
}

export interface CameraFrame {
  camera_id: string;
  jpeg_base64: string;
  timestamp: number;
  width?: number;
  height?: number;
}

// Material types
export interface Material {
  id: string;
  material_type: string;
  color: string;
  manufacturer: string;
  cost_per_kg_usd: number;
  density_g_cm3: number;
  nozzle_temp_min_c: number;
  nozzle_temp_max_c: number;
  bed_temp_min_c: number;
  bed_temp_max_c: number;
  properties: Record<string, unknown>;
  sustainability_score: number | null;
}

export interface InventoryItem {
  id: string;
  material_id: string;
  location: string | null;
  purchase_date: string;
  initial_weight_grams: number;
  current_weight_grams: number;
  status: 'available' | 'in_use' | 'depleted';
  notes: string | null;
}

export interface InventoryWithMaterial extends InventoryItem {
  material?: Material;
}

export interface InventoryStats {
  totalSpools: number;
  availableSpools: number;
  depletedSpools: number;
  lowStockSpools: number;
  totalValue: number;
  totalWeight: number;
}

// Dashboard tab configuration
export type DashboardTab = 'devices' | 'cameras' | 'materials';

export interface TabConfig {
  id: DashboardTab;
  label: string;
  icon: string;
}

export const DASHBOARD_TABS: TabConfig[] = [
  { id: 'devices', label: 'Devices', icon: '📡' },
  { id: 'cameras', label: 'Cameras', icon: '📹' },
  { id: 'materials', label: 'Materials', icon: '📦' },
];

// Constants
export const LOW_STOCK_THRESHOLD = 100; // grams
