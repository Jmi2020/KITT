import { memo, useState, useRef, useEffect, useCallback } from 'react';
import { ConversationSummary } from './ConversationSelector';

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete?: (id: string) => void;
  onRename?: (id: string, title: string) => void;
  onClose?: () => void;
  isLoading?: boolean;
}

/**
 * Sidebar panel for browsing and managing conversation history.
 * Groups conversations by date and supports create/rename/delete.
 */
export const ConversationSidebar = memo(function ConversationSidebar({
  conversations,
  currentId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onClose,
  isLoading = false,
}: ConversationSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when editing
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  // Group conversations by date
  const groupedConversations = groupByDate(conversations);

  const handleStartEdit = useCallback((conv: ConversationSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  }, []);

  const handleSaveEdit = useCallback((id: string) => {
    if (editTitle.trim() && onRename) {
      onRename(id, editTitle.trim());
    }
    setEditingId(null);
  }, [editTitle, onRename]);

  const handleKeyDown = useCallback((id: string, e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveEdit(id);
    } else if (e.key === 'Escape') {
      setEditingId(null);
    }
  }, [handleSaveEdit]);

  const handleDelete = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && confirm('Delete this conversation?')) {
      onDelete(id);
      if (id === currentId) {
        onNew();
      }
    }
  }, [onDelete, currentId, onNew]);

  const formatTime = (date: Date) => {
    const d = new Date(date);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="h-full flex flex-col bg-gray-900/50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <h2 className="text-sm font-medium text-gray-300 tracking-wide uppercase">History</h2>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 text-gray-500 hover:text-white hover:bg-white/10 rounded-md transition-colors"
            title="Close sidebar"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        )}
      </div>

      {/* New Conversation Button */}
      <div className="p-3 border-b border-white/5">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg transition-colors text-sm font-medium"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>New Conversation</span>
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-cyan-400" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-500 text-sm">
            No conversations yet
          </div>
        ) : (
          Object.entries(groupedConversations).map(([group, convs]) => (
            <div key={group} className="py-1">
              {/* Group Header */}
              <div className="px-4 py-2 text-xs text-gray-600 uppercase tracking-wider font-medium">
                {group}
              </div>

              {/* Conversations in Group */}
              {convs.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  className={`group mx-2 px-3 py-2.5 rounded-lg cursor-pointer transition-all ${
                    conv.id === currentId
                      ? 'bg-cyan-500/20 border-l-2 border-cyan-400 ml-0 pl-4'
                      : 'hover:bg-white/5'
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
                      className="w-full px-2 py-1 bg-gray-900 border border-cyan-500 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate leading-snug">
                          {conv.title}
                        </div>
                        <div className="flex items-center gap-1.5 mt-1 text-xs text-gray-500">
                          <span>{conv.messageCount} msg</span>
                          <span className="text-gray-700">·</span>
                          <span>{formatTime(conv.updatedAt)}</span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 shrink-0 ml-2">
                        {onRename && (
                          <button
                            onClick={(e) => handleStartEdit(conv, e)}
                            className="w-8 h-8 flex items-center justify-center rounded-lg bg-gray-200/50 dark:bg-gray-700/50 hover:bg-cyan-100 dark:hover:bg-cyan-900/50 transition-all text-base"
                            title="Rename conversation"
                            aria-label="Rename conversation"
                          >
                            ✏️
                          </button>
                        )}
                        {onDelete && (
                          <button
                            onClick={(e) => handleDelete(conv.id, e)}
                            className="w-8 h-8 flex items-center justify-center rounded-lg bg-gray-200/50 dark:bg-gray-700/50 hover:bg-red-100 dark:hover:bg-red-900/50 transition-all text-base"
                            title="Delete conversation"
                            aria-label="Delete conversation"
                          >
                            🗑️
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
});

/**
 * Groups conversations by relative date (Today, Yesterday, This Week, Older)
 */
function groupByDate(conversations: ConversationSummary[]): Record<string, ConversationSummary[]> {
  const groups: Record<string, ConversationSummary[]> = {};
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  for (const conv of conversations) {
    const date = new Date(conv.updatedAt);
    const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    let group: string;
    if (dateOnly.getTime() >= today.getTime()) {
      group = 'Today';
    } else if (dateOnly.getTime() >= yesterday.getTime()) {
      group = 'Yesterday';
    } else if (dateOnly.getTime() >= weekAgo.getTime()) {
      group = 'This Week';
    } else {
      group = 'Older';
    }

    if (!groups[group]) {
      groups[group] = [];
    }
    groups[group].push(conv);
  }

  // Return in chronological group order
  const orderedGroups: Record<string, ConversationSummary[]> = {};
  const order = ['Today', 'Yesterday', 'This Week', 'Older'];
  for (const key of order) {
    if (groups[key]) {
      orderedGroups[key] = groups[key];
    }
  }

  return orderedGroups;
}

export default ConversationSidebar;
