import { useState, useCallback } from 'react';
import {
  VoiceMode,
  VOICE_MODES,
  AVAILABLE_TOOLS,
  MODE_COLOR_PRESETS,
  ModeColorName,
  ToolCategory,
  createEmptyMode,
  duplicateMode,
  getColorClasses,
} from '../types/voiceModes';

interface VoiceModeEditorProps {
  customModes: VoiceMode[];
  onSave: (modes: VoiceMode[]) => Promise<void>;
}

interface EditModalProps {
  mode: VoiceMode;
  onSave: (mode: VoiceMode) => void;
  onCancel: () => void;
}

function EditModal({ mode, onSave, onCancel }: EditModalProps) {
  const [editedMode, setEditedMode] = useState<VoiceMode>({ ...mode });

  const handleToolToggle = (toolId: string) => {
    setEditedMode((prev) => ({
      ...prev,
      enabledTools: prev.enabledTools.includes(toolId)
        ? prev.enabledTools.filter((t) => t !== toolId)
        : [...prev.enabledTools, toolId],
    }));
  };

  const handleColorChange = (color: ModeColorName) => {
    const classes = getColorClasses(color);
    setEditedMode((prev) => ({
      ...prev,
      color,
      ...classes,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(editedMode);
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">
            {mode.isCustom ? 'Edit Mode' : 'Create Mode'}
          </h2>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={editedMode.name}
                onChange={(e) => setEditedMode((prev) => ({ ...prev, name: e.target.value }))}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Icon (emoji)</label>
              <input
                type="text"
                value={editedMode.icon}
                onChange={(e) => setEditedMode((prev) => ({ ...prev, icon: e.target.value }))}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                maxLength={4}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <input
              type="text"
              value={editedMode.description}
              onChange={(e) => setEditedMode((prev) => ({ ...prev, description: e.target.value }))}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
              placeholder="Brief description of this mode"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Color</label>
            <div className="flex gap-2 flex-wrap">
              {(Object.keys(MODE_COLOR_PRESETS) as ModeColorName[]).map((color) => {
                const colorMap: Record<ModeColorName, string> = {
                  cyan: '#22d3ee',
                  orange: '#f97316',
                  purple: '#a855f7',
                  green: '#22c55e',
                  pink: '#ec4899',
                  blue: '#3b82f6',
                  red: '#ef4444',
                  yellow: '#eab308',
                };
                return (
                  <button
                    key={color}
                    type="button"
                    onClick={() => handleColorChange(color)}
                    className={`w-8 h-8 rounded-lg border-2 transition-all overflow-hidden p-0 ${
                      editedMode.color === color
                        ? 'border-white scale-110'
                        : 'border-transparent hover:border-gray-500'
                    }`}
                    title={color}
                    style={{ backgroundColor: colorMap[color] }}
                  >
                  </button>
                );
              })}
            </div>
          </div>

          {/* Toggles */}
          <div className="flex gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={editedMode.allowPaid}
                onChange={(e) => setEditedMode((prev) => ({ ...prev, allowPaid: e.target.checked }))}
                className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-cyan-500 focus:ring-cyan-500"
              />
              <span className="text-white">Allow Paid APIs</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={editedMode.preferLocal}
                onChange={(e) => setEditedMode((prev) => ({ ...prev, preferLocal: e.target.checked }))}
                className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-cyan-500 focus:ring-cyan-500"
              />
              <span className="text-white">Prefer Local Models</span>
            </label>
          </div>

          {/* Tools */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">Enabled Tools</label>
            <div className="space-y-3 max-h-64 overflow-y-auto border border-gray-700 rounded-lg p-3">
              {(Object.entries(AVAILABLE_TOOLS) as [ToolCategory, typeof AVAILABLE_TOOLS[ToolCategory]][]).map(
                ([category, tools]) => (
                  <div key={category}>
                    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
                      {category}
                    </div>
                    <div className="space-y-1">
                      {tools.map((tool) => (
                        <label
                          key={tool.id}
                          className="flex items-center gap-2 cursor-pointer hover:bg-gray-700/50 rounded px-2 py-1"
                        >
                          <input
                            type="checkbox"
                            checked={editedMode.enabledTools.includes(tool.id)}
                            onChange={() => handleToolToggle(tool.id)}
                            className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-cyan-500 focus:ring-cyan-500"
                          />
                          <span className="text-white text-sm">{tool.name}</span>
                          {tool.paid && (
                            <span className="text-xs bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded">
                              Paid
                            </span>
                          )}
                        </label>
                      ))}
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        </form>

        <div className="flex justify-end gap-3 p-4 border-t border-gray-700">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
          >
            Save Mode
          </button>
        </div>
      </div>
    </div>
  );
}

interface ModeCardProps {
  mode: VoiceMode;
  isSystem: boolean;
  onEdit?: () => void;
  onDuplicate?: () => void;
  onDelete?: () => void;
}

function ModeCard({ mode, isSystem, onEdit, onDuplicate, onDelete }: ModeCardProps) {
  // Color values for mode-specific styling
  const colorValues: Record<string, { bg: string; border: string }> = {
    cyan: { bg: 'rgba(34, 211, 238, 0.1)', border: 'rgba(34, 211, 238, 0.5)' },
    orange: { bg: 'rgba(249, 115, 22, 0.1)', border: 'rgba(249, 115, 22, 0.5)' },
    purple: { bg: 'rgba(168, 85, 247, 0.1)', border: 'rgba(168, 85, 247, 0.5)' },
    green: { bg: 'rgba(34, 197, 94, 0.1)', border: 'rgba(34, 197, 94, 0.5)' },
    pink: { bg: 'rgba(236, 72, 153, 0.1)', border: 'rgba(236, 72, 153, 0.5)' },
    blue: { bg: 'rgba(59, 130, 246, 0.1)', border: 'rgba(59, 130, 246, 0.5)' },
    red: { bg: 'rgba(239, 68, 68, 0.1)', border: 'rgba(239, 68, 68, 0.5)' },
    yellow: { bg: 'rgba(234, 179, 8, 0.1)', border: 'rgba(234, 179, 8, 0.5)' },
  };
  const colors = colorValues[mode.color] || colorValues.cyan;

  return (
    <div
      className="flex items-center justify-between p-3 rounded-lg"
      style={{
        backgroundColor: colors.bg,
        border: `1px solid ${colors.border}`,
      }}
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">{mode.icon}</span>
        <div>
          <div className="text-white font-medium">{mode.name}</div>
          <div className="text-sm text-gray-400">{mode.description}</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {mode.allowPaid && (
          <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">
            Paid
          </span>
        )}
        {isSystem ? (
          <button
            onClick={onDuplicate}
            className="px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
          >
            Duplicate
          </button>
        ) : (
          <>
            <button
              onClick={onEdit}
              className="px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
            >
              Edit
            </button>
            <button
              onClick={onDelete}
              className="px-3 py-1 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/20 rounded transition-colors"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function VoiceModeEditor({ customModes, onSave }: VoiceModeEditorProps) {
  const [editingMode, setEditingMode] = useState<VoiceMode | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const handleCreate = useCallback(() => {
    setEditingMode(createEmptyMode());
    setIsCreating(true);
  }, []);

  const handleDuplicate = useCallback((mode: VoiceMode) => {
    setEditingMode(duplicateMode(mode));
    setIsCreating(true);
  }, []);

  const handleEdit = useCallback((mode: VoiceMode) => {
    setEditingMode({ ...mode });
    setIsCreating(false);
  }, []);

  const handleDelete = useCallback(async (modeId: string) => {
    const newModes = customModes.filter((m) => m.id !== modeId);
    await onSave(newModes);
    setDeleteConfirm(null);
  }, [customModes, onSave]);

  const handleSaveMode = useCallback(async (mode: VoiceMode) => {
    if (isCreating) {
      // Add new mode
      await onSave([...customModes, mode]);
    } else {
      // Update existing mode
      const newModes = customModes.map((m) => (m.id === mode.id ? mode : m));
      await onSave(newModes);
    }
    setEditingMode(null);
    setIsCreating(false);
  }, [customModes, onSave, isCreating]);

  const handleCancel = useCallback(() => {
    setEditingMode(null);
    setIsCreating(false);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header with Create button */}
      <div className="flex items-center justify-between">
        <p className="text-gray-400">
          Customize voice modes by creating new ones or duplicating existing system modes.
        </p>
        <button
          onClick={handleCreate}
          className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create Mode
        </button>
      </div>

      {/* System Modes */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
          System Modes (read-only)
        </h3>
        <div className="space-y-2">
          {VOICE_MODES.map((mode) => (
            <ModeCard
              key={mode.id}
              mode={mode}
              isSystem={true}
              onDuplicate={() => handleDuplicate(mode)}
            />
          ))}
        </div>
      </div>

      {/* Custom Modes */}
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Custom Modes
        </h3>
        {customModes.length === 0 ? (
          <div className="text-center py-8 text-gray-500 border border-dashed border-gray-700 rounded-lg">
            No custom modes yet. Create one or duplicate a system mode to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {customModes.map((mode) => (
              <ModeCard
                key={mode.id}
                mode={mode}
                isSystem={false}
                onEdit={() => handleEdit(mode)}
                onDelete={() => setDeleteConfirm(mode.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editingMode && (
        <EditModal
          mode={editingMode}
          onSave={handleSaveMode}
          onCancel={handleCancel}
        />
      )}

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 max-w-md">
            <h3 className="text-lg font-semibold text-white mb-2">Delete Mode?</h3>
            <p className="text-gray-400 mb-4">
              This action cannot be undone. The mode will be permanently removed.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
