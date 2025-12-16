import { useState, useCallback } from 'react';
import './ThermalPanel.css';

interface BedZone {
  temperature: number | null;
  target: number | null;
}

interface ThermalPanelProps {
  bedTemp: number | null;
  bedTarget: number | null;
  nozzleTemp: number | null;
  nozzleTarget: number | null;
  bedZones?: Record<string, BedZone>;
  onRefresh?: () => void;
}

type HeaterType = 'heater_bed' | 'heater_bed1' | 'heater_bed2' | 'heater_bed3' | 'extruder';

interface HeaterConfig {
  id: HeaterType;
  label: string;
  maxTemp: number;
}

const HEATERS: HeaterConfig[] = [
  { id: 'extruder', label: 'Extruder', maxTemp: 350 },
  { id: 'heater_bed', label: 'Heater Bed', maxTemp: 120 },
  { id: 'heater_bed1', label: 'Heater Bed 1', maxTemp: 120 },
  { id: 'heater_bed2', label: 'Heater Bed 2', maxTemp: 120 },
  { id: 'heater_bed3', label: 'Heater Bed 3', maxTemp: 120 },
];

export default function ThermalPanel({
  nozzleTemp,
  nozzleTarget,
  bedZones,
  onRefresh,
}: ThermalPanelProps) {
  const [targets, setTargets] = useState<Record<string, string>>({
    extruder: '200',
    heater_bed: '60',
    heater_bed1: '60',
    heater_bed2: '60',
    heater_bed3: '60',
  });
  const [settingTemp, setSettingTemp] = useState<HeaterType | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getHeaterData = (heaterId: HeaterType): { temp: number | null; target: number | null } => {
    if (heaterId === 'extruder') {
      return { temp: nozzleTemp, target: nozzleTarget };
    }
    if (bedZones && bedZones[heaterId]) {
      return {
        temp: bedZones[heaterId].temperature,
        target: bedZones[heaterId].target,
      };
    }
    return { temp: null, target: null };
  };

  const setTemperature = useCallback(async (heater: HeaterType, target: number) => {
    setSettingTemp(heater);
    setError(null);

    try {
      const response = await fetch('/api/fabrication/elegoo/temperature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ heater, target }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to set temperature');
      }

      if (onRefresh) {
        setTimeout(onRefresh, 500);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set temperature');
    } finally {
      setSettingTemp(null);
    }
  }, [onRefresh]);

  const handleSetTemp = (heaterId: HeaterType, maxTemp: number) => {
    const target = parseFloat(targets[heaterId] || '0');
    if (!isNaN(target) && target >= 0 && target <= maxTemp) {
      setTemperature(heaterId, target);
    }
  };

  const handleTurnOff = (heaterId: HeaterType) => {
    setTemperature(heaterId, 0);
  };

  const handlePreheat = async (preset: 'PLA' | 'PETG' | 'ABS') => {
    const temps = {
      PLA: { extruder: 200, bed: 60 },
      PETG: { extruder: 240, bed: 80 },
      ABS: { extruder: 250, bed: 100 },
    };
    const t = temps[preset];

    // Set all heaters
    await Promise.all([
      setTemperature('extruder', t.extruder),
      setTemperature('heater_bed', t.bed),
      setTemperature('heater_bed1', t.bed),
      setTemperature('heater_bed2', t.bed),
      setTemperature('heater_bed3', t.bed),
    ]);
  };

  const handleCooldown = async () => {
    await Promise.all([
      setTemperature('extruder', 0),
      setTemperature('heater_bed', 0),
      setTemperature('heater_bed1', 0),
      setTemperature('heater_bed2', 0),
      setTemperature('heater_bed3', 0),
    ]);
  };

  const formatTemp = (temp: number | null): string => {
    if (temp === null) return '--';
    return temp.toFixed(1);
  };

  const getPowerState = (target: number | null): string => {
    if (target === null || target === 0) return 'off';
    return 'on';
  };

  return (
    <div className="thermal-panel">
      <div className="thermal-header">
        <h4>Thermals</h4>
        <div className="thermal-actions">
          {onRefresh && (
            <button className="refresh-btn" onClick={onRefresh} title="Refresh">
              &#x21bb;
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="thermal-error">
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      {/* Heater List - Fluidd style */}
      <div className="heater-list">
        <div className="heater-list-header">
          <span className="col-name">Name</span>
          <span className="col-power">Power</span>
          <span className="col-actual">Actual</span>
          <span className="col-target">Target</span>
        </div>

        {HEATERS.map((heater) => {
          const data = getHeaterData(heater.id);
          const powerState = getPowerState(data.target);

          return (
            <div key={heater.id} className="heater-row">
              <span className="col-name">
                <span className={`heater-icon ${powerState}`}>&#x1F525;</span>
                {heater.label}
              </span>
              <span className={`col-power ${powerState}`}>{powerState}</span>
              <span className="col-actual">{formatTemp(data.temp)}°C /</span>
              <span className="col-target">
                <input
                  type="number"
                  value={targets[heater.id]}
                  onChange={(e) => setTargets(prev => ({ ...prev, [heater.id]: e.target.value }))}
                  min="0"
                  max={heater.maxTemp}
                  step="5"
                  disabled={settingTemp !== null}
                />
                <span className="unit">°C</span>
                <button
                  className="set-btn"
                  onClick={() => handleSetTemp(heater.id, heater.maxTemp)}
                  disabled={settingTemp === heater.id}
                  title="Set temperature"
                >
                  {settingTemp === heater.id ? '...' : '✓'}
                </button>
                <button
                  className="off-btn"
                  onClick={() => handleTurnOff(heater.id)}
                  disabled={settingTemp === heater.id}
                  title="Turn off"
                >
                  ✕
                </button>
              </span>
            </div>
          );
        })}
      </div>

      {/* Preheat Presets */}
      <div className="thermal-presets">
        <span className="preset-label">Preheat:</span>
        <button
          className="preset-btn"
          onClick={() => handlePreheat('PLA')}
          disabled={settingTemp !== null}
        >
          PLA
        </button>
        <button
          className="preset-btn"
          onClick={() => handlePreheat('PETG')}
          disabled={settingTemp !== null}
        >
          PETG
        </button>
        <button
          className="preset-btn"
          onClick={() => handlePreheat('ABS')}
          disabled={settingTemp !== null}
        >
          ABS
        </button>
        <button
          className="cooldown-btn"
          onClick={handleCooldown}
          disabled={settingTemp !== null}
        >
          Cooldown
        </button>
      </div>
    </div>
  );
}
