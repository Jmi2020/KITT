import { memo, useState, useRef, useEffect } from 'react';

export interface ConversationSummary {
  id: string;
  title: string;
  messageCount: number;
  lastMessage?: string;
  createdAt: Date;
  updatedAt: Date;
}

interface ConversationSelectorProps {
  conversations: ConversationSummary[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete?: (id: string) => void;
  onRename?: (id: string, title: string) => void;
  isLoading?: boolean;
  compact?: boolean;
}

/**
 * Dropdown selector for switching between conversations.
 * Supports creating new, renaming, and deleting conversations.
 */
export const ConversationSelector = memo(function ConversationSelector({
  conversations,
  currentId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  isLoading = false,
  compact = false,
}: ConversationSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Current conversation
  const current = conversations.find((c) => c.id === currentId);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setEditingId(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus input when editing
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const handleSelect = (id: string) => {
    onSelect(id);
    setIsOpen(false);
  };

  const handleStartEdit = (conv: ConversationSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const handleSaveEdit = (id: string) => {
    if (editTitle.trim() && onRename) {
      onRename(id, editTitle.trim());
    }
    setEditingId(null);
  };

  const handleKeyDown = (id: string, e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveEdit(id);
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && confirm('Delete this conversation?')) {
      onDelete(id);
      if (id === currentId) {
        onNew();
      }
    }
  };

  const formatDate = (date: Date) => {
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return 'Yesterday';
    } else if (days < 7) {
      return d.toLocaleDateString([], { weekday: 'short' });
    } else {
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className={`flex items-center gap-2 ${
          compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'
        } rounded-lg bg-gray-800/50 hover:bg-gray-700/50 border border-gray-700 text-gray-300 hover:text-white transition-all`}
      >
        {isLoading ? (
          <span className="animate-pulse">Loading...</span>
        ) : (
          <>
            <span className="truncate max-w-[120px] md:max-w-[180px]">
              {current?.title || 'New Conversation'}
            </span>
            <span className="text-gray-500 text-xs">▼</span>
          </>
        )}
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 max-h-80 overflow-y-auto bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50">
          {/* New conversation button */}
          <button
            onClick={() => {
              onNew();
              setIsOpen(false);
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-cyan-400 hover:bg-cyan-500/20 transition-colors border-b border-gray-700"
          >
            <span className="text-lg">+</span>
            <span>New Conversation</span>
          </button>

          {/* Conversation list */}
          {conversations.length === 0 ? (
            <div className="px-3 py-4 text-center text-gray-500 text-sm">
              No conversations yet
            </div>
          ) : (
            <div className="py-1">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => handleSelect(conv.id)}
                  className={`px-3 py-2 cursor-pointer transition-colors ${
                    conv.id === currentId
                      ? 'bg-cyan-500/20 border-l-2 border-cyan-400'
                      : 'hover:bg-gray-700/50'
                  }`}
                >
                  {editingId === conv.id ? (
                    <input
                      ref={inputRef}
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onBlur={() => handleSaveEdit(conv.id)}
                      onKeyDown={(e) => handleKeyDown(conv.id, e)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full px-2 py-1 bg-gray-900 border border-cyan-500 rounded text-white text-sm focus:outline-none"
                    />
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{conv.title}</div>
                        {conv.lastMessage && (
                          <div className="text-xs text-gray-500 truncate mt-0.5">
                            {conv.lastMessage}
                          </div>
                        )}
                        <div className="flex items-center gap-2 mt-1 text-xs text-gray-600">
                          <span>{conv.messageCount} messages</span>
                          <span>·</span>
                          <span>{formatDate(conv.updatedAt)}</span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 hover:opacity-100">
                        {onRename && (
                          <button
                            onClick={(e) => handleStartEdit(conv, e)}
                            className="p-1 text-gray-500 hover:text-cyan-400 transition-colors"
                            title="Rename"
                          >
                            ✎
                          </button>
                        )}
                        {onDelete && (
                          <button
                            onClick={(e) => handleDelete(conv.id, e)}
                            className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                            title="Delete"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default ConversationSelector;
