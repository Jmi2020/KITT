import useKittyContext from '../hooks/useKittyContext';

interface WallTerminalProps {
  remoteMode: boolean;
}

const WallTerminal = ({ remoteMode }: WallTerminalProps) => {
  const { context } = useKittyContext();
  const activeConversation = Object.values(context.conversations)[0];

  return (
    <section className="wall-terminal">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2>Wall Terminal</h2>
          <p className="text-secondary mt-1">Live conversation monitoring and context display</p>
        </div>
        {remoteMode && <span className="badge badge-warning">Remote Read-Only</span>}
      </div>

      {activeConversation ? (
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Active Conversation</h3>
              <p className="text-muted" style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                ID: {activeConversation.conversationId}
              </p>
            </div>
            <span className="badge badge-success">Live</span>
          </div>
          <div className="card-body">
            <div className="mb-3">
              <strong className="text-primary">Last Intent:</strong>
              <span className="text-secondary" style={{ marginLeft: '0.5rem' }}>
                {activeConversation.lastIntent ?? 'n/a'}
              </span>
            </div>

            {activeConversation.state && Object.keys(activeConversation.state).length > 0 ? (
              <details>
                <summary style={{ cursor: 'pointer', color: 'var(--accent-secondary)' }}>
                  View conversation state
                </summary>
                <pre style={{ marginTop: '1rem' }}>
                  {JSON.stringify(activeConversation.state, null, 2)}
                </pre>
              </details>
            ) : (
              <p className="text-muted">No state data available</p>
            )}
          </div>
        </div>
      ) : (
        <div className="card text-center">
          <div className="card-body">
            <h3 className="mb-2">No Active Conversation</h3>
            <p className="text-secondary mb-3">
              Conversations will appear here when initiated through voice, CLI, or the Fabrication Console.
            </p>
            <p className="text-muted">
              Start a conversation to see live context updates.
            </p>
          </div>
        </div>
      )}
    </section>
  );
};

export default WallTerminal;
