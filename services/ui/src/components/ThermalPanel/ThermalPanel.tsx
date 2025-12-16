import { useState, useCallback } from 'react';
import './ThermalPanel.css';

interface ThermalPanelProps {
  bedTemp: number | null;
  bedTarget: number | null;
  nozzleTemp: number | null;
  nozzleTarget: number | null;
  onRefresh?: () => void;
}

type HeaterType = 'heater_bed' | 'extruder';

export default function ThermalPanel({
  bedTemp,
  bedTarget,
  nozzleTemp,
  nozzleTarget,
  onRefresh,
}: ThermalPanelProps) {
  const [newBedTarget, setNewBedTarget] = useState<string>('60');
  const [newNozzleTarget, setNewNozzleTarget] = useState<string>('200');
  const [settingTemp, setSettingTemp] = useState<HeaterType | null>(null);
  const [error, setError] = useState<string | null>(null);

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

      // Trigger refresh to get updated temps
      if (onRefresh) {
        setTimeout(onRefresh, 500);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set temperature');
    } finally {
      setSettingTemp(null);
    }
  }, [onRefresh]);

  const handleSetBedTemp = () => {
    const target = parseFloat(newBedTarget);
    if (!isNaN(target) && target >= 0 && target <= 120) {
      setTemperature('heater_bed', target);
    }
  };

  const handleSetNozzleTemp = () => {
    const target = parseFloat(newNozzleTarget);
    if (!isNaN(target) && target >= 0 && target <= 350) {
      setTemperature('extruder', target);
    }
  };

  const handleBedOff = () => setTemperature('heater_bed', 0);
  const handleNozzleOff = () => setTemperature('extruder', 0);

  // Temperature color coding
  const getTempColor = (current: number | null, target: number | null): string => {
    if (current === null) return 'temp-unknown';
    if (target === null || target === 0) {
      return current < 40 ? 'temp-cold' : 'temp-cooling';
    }
    const diff = Math.abs(current - target);
    if (diff <= 2) return 'temp-at-target';
    if (current < target) return 'temp-heating';
    return 'temp-cooling';
  };

  const formatTemp = (temp: number | null): string => {
    if (temp === null) return '--';
    return `${temp.toFixed(1)}`;
  };

  return (
    <div className="thermal-panel">
      <div className="thermal-header">
        <h4>Thermal Control</h4>
        {onRefresh && (
          <button className="refresh-btn" onClick={onRefresh} title="Refresh">
            &#x21bb;
          </button>
        )}
      </div>

      {error && (
        <div className="thermal-error">
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      <div className="thermal-grid">
        {/* Bed Temperature Card */}
        <div className="thermal-card">
          <div className="thermal-label">Bed</div>
          <div className={`thermal-current ${getTempColor(bedTemp, bedTarget)}`}>
            {formatTemp(bedTemp)}°C
          </div>
          <div className="thermal-target">
            Target: {bedTarget !== null ? `${bedTarget}°C` : '--'}
          </div>
          <div className="thermal-controls">
            <input
              type="number"
              value={newBedTarget}
              onChange={(e) => setNewBedTarget(e.target.value)}
              min="0"
              max="120"
              step="5"
              placeholder="60"
            />
            <button
              className="set-btn"
              onClick={handleSetBedTemp}
              disabled={settingTemp === 'heater_bed'}
            >
              {settingTemp === 'heater_bed' ? '...' : 'Set'}
            </button>
            <button
              className="off-btn"
              onClick={handleBedOff}
              disabled={settingTemp === 'heater_bed'}
            >
              Off
            </button>
          </div>
        </div>

        {/* Nozzle Temperature Card */}
        <div className="thermal-card">
          <div className="thermal-label">Nozzle</div>
          <div className={`thermal-current ${getTempColor(nozzleTemp, nozzleTarget)}`}>
            {formatTemp(nozzleTemp)}°C
          </div>
          <div className="thermal-target">
            Target: {nozzleTarget !== null ? `${nozzleTarget}°C` : '--'}
          </div>
          <div className="thermal-controls">
            <input
              type="number"
              value={newNozzleTarget}
              onChange={(e) => setNewNozzleTarget(e.target.value)}
              min="0"
              max="350"
              step="5"
              placeholder="200"
            />
            <button
              className="set-btn"
              onClick={handleSetNozzleTemp}
              disabled={settingTemp === 'extruder'}
            >
              {settingTemp === 'extruder' ? '...' : 'Set'}
            </button>
            <button
              className="off-btn"
              onClick={handleNozzleOff}
              disabled={settingTemp === 'extruder'}
            >
              Off
            </button>
          </div>
        </div>
      </div>

      {/* Quick Preheat Buttons */}
      <div className="thermal-presets">
        <span className="preset-label">Preheat:</span>
        <button
          className="preset-btn"
          onClick={() => {
            setTemperature('heater_bed', 60);
            setTemperature('extruder', 200);
          }}
          disabled={settingTemp !== null}
        >
          PLA
        </button>
        <button
          className="preset-btn"
          onClick={() => {
            setTemperature('heater_bed', 80);
            setTemperature('extruder', 240);
          }}
          disabled={settingTemp !== null}
        >
          PETG
        </button>
        <button
          className="preset-btn"
          onClick={() => {
            setTemperature('heater_bed', 100);
            setTemperature('extruder', 250);
          }}
          disabled={settingTemp !== null}
        >
          ABS
        </button>
        <button
          className="cooldown-btn"
          onClick={() => {
            setTemperature('heater_bed', 0);
            setTemperature('extruder', 0);
          }}
          disabled={settingTemp !== null}
        >
          Cooldown
        </button>
      </div>
    </div>
  );
}
