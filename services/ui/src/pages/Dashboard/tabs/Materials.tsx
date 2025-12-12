/**
 * Materials Tab - Filament inventory management
 * Extracted from MaterialInventory.tsx
 */

import { useEffect, useState } from 'react';
import type { Material, InventoryWithMaterial, InventoryItem, InventoryStats } from '../../../types/dashboard';
import { LOW_STOCK_THRESHOLD } from '../../../types/dashboard';

const MaterialsTab = () => {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [inventory, setInventory] = useState<InventoryWithMaterial[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string>('');
  const [manufacturerFilter, setManufacturerFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showLowStockOnly, setShowLowStockOnly] = useState(false);

  // Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [addSpoolForm, setAddSpoolForm] = useState({
    spool_id: '',
    material_id: '',
    initial_weight_grams: 1000,
    location: '',
    notes: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [materialsRes, inventoryRes] = await Promise.all([
        fetch('/api/fabrication/materials'),
        fetch('/api/fabrication/inventory'),
      ]);

      if (!materialsRes.ok) throw new Error('Failed to load materials');
      if (!inventoryRes.ok) throw new Error('Failed to load inventory');

      const materialsData: Material[] = await materialsRes.json();
      const inventoryData: InventoryItem[] = await inventoryRes.json();

      setMaterials(materialsData);

      // Join inventory with materials
      const itemsWithMaterials = inventoryData.map((item) => ({
        ...item,
        material: materialsData.find((m) => m.id === item.material_id),
      }));
      setInventory(itemsWithMaterials);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleAddSpool = async () => {
    try {
      const response = await fetch('/api/fabrication/inventory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...addSpoolForm,
          purchase_date: new Date().toISOString(),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to add spool');
      }

      setAddSpoolForm({
        spool_id: '',
        material_id: '',
        initial_weight_grams: 1000,
        location: '',
        notes: '',
      });
      setShowAddModal(false);
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to add spool');
    }
  };

  // Calculate stats
  const stats: InventoryStats = {
    totalSpools: inventory.length,
    availableSpools: inventory.filter((i) => i.status === 'available').length,
    depletedSpools: inventory.filter((i) => i.status === 'depleted').length,
    lowStockSpools: inventory.filter(
      (i) => i.current_weight_grams < LOW_STOCK_THRESHOLD && i.status !== 'depleted'
    ).length,
    totalValue: inventory.reduce((sum, item) => {
      const material = item.material;
      if (!material) return sum;
      const kg = item.current_weight_grams / 1000;
      return sum + kg * material.cost_per_kg_usd;
    }, 0),
    totalWeight: inventory.reduce((sum, item) => sum + item.current_weight_grams, 0),
  };

  // Filter inventory
  const filteredInventory = inventory.filter((item) => {
    if (statusFilter && item.status !== statusFilter) return false;
    if (showLowStockOnly && item.current_weight_grams >= LOW_STOCK_THRESHOLD) return false;
    if (materialTypeFilter && item.material?.material_type !== materialTypeFilter) return false;
    if (
      manufacturerFilter &&
      item.material &&
      !item.material.manufacturer.toLowerCase().includes(manufacturerFilter.toLowerCase())
    )
      return false;
    return true;
  });

  // Get unique material types
  const materialTypes = Array.from(new Set(materials.map((m) => m.material_type))).sort();

  const getStockBadge = (item: InventoryItem) => {
    if (item.status === 'depleted') {
      return <span className="badge badge-depleted">Depleted</span>;
    }
    if (item.current_weight_grams < LOW_STOCK_THRESHOLD) {
      return <span className="badge badge-low">Low Stock</span>;
    }
    if (item.status === 'in_use') {
      return <span className="badge badge-in-use">In Use</span>;
    }
    return <span className="badge badge-available">Available</span>;
  };

  const getPercentageRemaining = (item: InventoryItem) => {
    return Math.round((item.current_weight_grams / item.initial_weight_grams) * 100);
  };

  if (loading) {
    return <div className="loading-state">Loading inventory...</div>;
  }

  if (error) {
    return <div className="error-state">Error: {error}</div>;
  }

  return (
    <div className="materials-tab">
      {/* Header with Add button */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1.5rem' }}>
        <button className="btn-primary" onClick={() => setShowAddModal(true)}>
          + Add Spool
        </button>
      </div>

      {/* Statistics */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Spools</div>
          <div className="stat-value">{stats.totalSpools}</div>
        </div>
        <div className="stat-card stat-available">
          <div className="stat-label">Available</div>
          <div className="stat-value">{stats.availableSpools}</div>
        </div>
        <div className="stat-card stat-low-stock">
          <div className="stat-label">Low Stock</div>
          <div className="stat-value">{stats.lowStockSpools}</div>
        </div>
        <div className="stat-card stat-depleted">
          <div className="stat-label">Depleted</div>
          <div className="stat-value">{stats.depletedSpools}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Value</div>
          <div className="stat-value">${stats.totalValue.toFixed(2)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Weight</div>
          <div className="stat-value">{(stats.totalWeight / 1000).toFixed(2)} kg</div>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <div className="filter-group">
          <label>Material Type</label>
          <select value={materialTypeFilter} onChange={(e) => setMaterialTypeFilter(e.target.value)}>
            <option value="">All Types</option>
            {materialTypes.map((type) => (
              <option key={type} value={type}>
                {type.toUpperCase()}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label>Manufacturer</label>
          <input
            type="text"
            value={manufacturerFilter}
            onChange={(e) => setManufacturerFilter(e.target.value)}
            placeholder="Filter by manufacturer..."
          />
        </div>

        <div className="filter-group">
          <label>Status</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Status</option>
            <option value="available">Available</option>
            <option value="in_use">In Use</option>
            <option value="depleted">Depleted</option>
          </select>
        </div>

        <div className="filter-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={showLowStockOnly}
              onChange={(e) => setShowLowStockOnly(e.target.checked)}
            />
            <span>Low Stock Only</span>
          </label>
        </div>
      </div>

      {/* Inventory Table */}
      <div className="materials-section">
        <h2>Inventory ({filteredInventory.length} spools)</h2>
        {filteredInventory.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📦</div>
            <div className="empty-state-title">No inventory items found</div>
            <p className="empty-state-text">Try adjusting your filters or add a new spool.</p>
          </div>
        ) : (
          <div className="inventory-table">
            <table>
              <thead>
                <tr>
                  <th>Spool ID</th>
                  <th>Type</th>
                  <th>Color</th>
                  <th>Manufacturer</th>
                  <th>Location</th>
                  <th>Weight</th>
                  <th>Status</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {filteredInventory.map((item) => {
                  const material = item.material;
                  const percentRemaining = getPercentageRemaining(item);
                  const value = material
                    ? (item.current_weight_grams / 1000) * material.cost_per_kg_usd
                    : 0;

                  return (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td>{material?.material_type.toUpperCase() || 'N/A'}</td>
                      <td>
                        <span
                          className="color-badge"
                          style={{ backgroundColor: material?.color || '#ccc' }}
                        >
                          {material?.color || 'N/A'}
                        </span>
                      </td>
                      <td>{material?.manufacturer || 'N/A'}</td>
                      <td>{item.location || '—'}</td>
                      <td>
                        <div>
                          <div style={{ fontSize: '0.9rem' }}>
                            {item.current_weight_grams.toFixed(0)}g / {item.initial_weight_grams.toFixed(0)}g
                          </div>
                          <div className="weight-bar">
                            <div
                              className="weight-bar-fill"
                              style={{
                                width: `${percentRemaining}%`,
                                backgroundColor:
                                  percentRemaining < 10
                                    ? '#ef4444'
                                    : percentRemaining < 30
                                    ? '#f59e0b'
                                    : '#10b981',
                              }}
                            />
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary, #888)' }}>
                            {percentRemaining}%
                          </div>
                        </div>
                      </td>
                      <td>{getStockBadge(item)}</td>
                      <td>${value.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Material Catalog */}
      <div className="materials-section">
        <h2>Material Catalog ({materials.length} materials)</h2>
        <div className="inventory-table">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Color</th>
                <th>Manufacturer</th>
                <th>Cost/kg</th>
                <th>Nozzle Temp</th>
                <th>Bed Temp</th>
              </tr>
            </thead>
            <tbody>
              {materials.map((material) => (
                <tr key={material.id}>
                  <td>{material.id}</td>
                  <td>{material.material_type.toUpperCase()}</td>
                  <td>
                    <span className="color-badge" style={{ backgroundColor: material.color }}>
                      {material.color}
                    </span>
                  </td>
                  <td>{material.manufacturer}</td>
                  <td>${material.cost_per_kg_usd.toFixed(2)}</td>
                  <td>
                    {material.nozzle_temp_min_c}–{material.nozzle_temp_max_c}°C
                  </td>
                  <td>
                    {material.bed_temp_min_c}–{material.bed_temp_max_c}°C
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Spool Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add New Spool</h2>
              <button className="modal-close" onClick={() => setShowAddModal(false)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Spool ID *</label>
                <input
                  type="text"
                  value={addSpoolForm.spool_id}
                  onChange={(e) => setAddSpoolForm({ ...addSpoolForm, spool_id: e.target.value })}
                  placeholder="e.g., spool_001"
                  required
                />
              </div>

              <div className="form-group">
                <label>Material *</label>
                <select
                  value={addSpoolForm.material_id}
                  onChange={(e) => setAddSpoolForm({ ...addSpoolForm, material_id: e.target.value })}
                  required
                >
                  <option value="">Select material...</option>
                  {materials.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.material_type.toUpperCase()} - {m.color} ({m.manufacturer})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Initial Weight (grams) *</label>
                <input
                  type="number"
                  value={addSpoolForm.initial_weight_grams}
                  onChange={(e) =>
                    setAddSpoolForm({ ...addSpoolForm, initial_weight_grams: parseFloat(e.target.value) })
                  }
                  min="0"
                  required
                />
              </div>

              <div className="form-group">
                <label>Location</label>
                <input
                  type="text"
                  value={addSpoolForm.location}
                  onChange={(e) => setAddSpoolForm({ ...addSpoolForm, location: e.target.value })}
                  placeholder="e.g., Shelf A, Bin 3"
                />
              </div>

              <div className="form-group">
                <label>Notes</label>
                <textarea
                  value={addSpoolForm.notes}
                  onChange={(e) => setAddSpoolForm({ ...addSpoolForm, notes: e.target.value })}
                  placeholder="Optional notes..."
                  rows={3}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleAddSpool}
                disabled={!addSpoolForm.spool_id || !addSpoolForm.material_id}
              >
                Add Spool
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MaterialsTab;
