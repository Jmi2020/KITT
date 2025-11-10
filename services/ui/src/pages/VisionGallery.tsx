import { useEffect, useMemo, useState } from 'react';
import VisionNyan from '../components/VisionNyan';
import './VisionGallery.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8080';

interface ImageResult {
  id: string;
  title?: string;
  description?: string;
  image_url: string;
  thumbnail_url?: string;
  source?: string;
  score?: number;
  clip_score?: number;
}

const STARTER_PROMPTS = [
  'neon-lit robotics lab surveillance shot',
  'macro photo of bio-luminescent coral drone',
  'studio render of modular robot arm for surgery',
  'retro-futurist rover exploring a sandstorm',
  'architectural axonometric of floating research hub',
];

const VisionGallery = () => {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const initialQuery = params.get('query') ?? '';
  const initialSession = params.get('session') ?? crypto.randomUUID();

  const [query, setQuery] = useState(initialQuery);
  const [sessionId, setSessionId] = useState(initialSession);
  const [maxResults, setMaxResults] = useState(12);
  const [minScore, setMinScore] = useState(0.2);
  const [results, setResults] = useState<ImageResult[]>([]);
  const [selected, setSelected] = useState<Record<string, ImageResult>>({});
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (initialQuery) {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pickRandomPrompt = () => STARTER_PROMPTS[Math.floor(Math.random() * STARTER_PROMPTS.length)];

  const handleSearch = async (inputQuery?: string) => {
    const nextQuery = typeof inputQuery === 'string' ? inputQuery : query;
    if (typeof inputQuery === 'string') {
      setQuery(inputQuery);
    }
    if (!nextQuery.trim()) {
      setError('Enter a query to search for images.');
      return;
    }
    setError('');
    setStatus('Searching...');
    setLoading(true);
    try {
      const searchResponse = await fetch(`${API_BASE}/api/vision/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: nextQuery, max_results: maxResults }),
      });
      if (!searchResponse.ok) {
        throw new Error(`Search failed (${searchResponse.status})`);
      }
      const searchData = await searchResponse.json();
      const rawResults: ImageResult[] = searchData.results ?? [];
      if (!rawResults.length) {
        setResults([]);
        setStatus('No results found.');
        setLoading(false);
        return;
      }
      const filterResponse = await fetch(`${API_BASE}/api/vision/filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: nextQuery, images: rawResults, min_score: minScore }),
      });
      if (!filterResponse.ok) {
        throw new Error(`Filter failed (${filterResponse.status})`);
      }
      const filterData = await filterResponse.json();
      setResults(filterData.results ?? rawResults);
      setSelected({});
      setStatus(`Fetched ${filterData.results?.length ?? rawResults.length} candidates.`);
    } catch (err) {
      setError((err as Error).message);
      setStatus('');
    } finally {
      setLoading(false);
    }
  };

  const toggleSelection = (image: ImageResult) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[image.id]) {
        delete next[image.id];
      } else {
        next[image.id] = image;
      }
      return next;
    });
  };

  const handleStore = async () => {
    const picks = Object.values(selected);
    if (!picks.length) {
      setError('Select at least one image to store.');
      return;
    }
    setError('');
    setStatus('Storing selections...');
    try {
      const payload = {
        session_id: sessionId,
        images: picks.map((item) => ({
          id: item.id,
          image_url: item.image_url,
          title: item.title,
          source: item.source,
          caption: item.description,
        })),
      };
      const resp = await fetch(`${API_BASE}/api/vision/store`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        throw new Error(`Store failed (${resp.status})`);
      }
      const data = await resp.json();
      setStatus(`Stored ${data.stored?.length ?? 0} references for session ${data.session_id}.`);
      setSelected({});
    } catch (err) {
      setError((err as Error).message);
      setStatus('');
    }
  };

  return (
    <section className="vision-gallery">
      <header>
        <h2>Vision Gallery</h2>
        <p>Session: {sessionId}</p>
      </header>
      <div className="controls">
        <label>
          Query
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g., gandalf rubber duck" />
        </label>
        <label>
          Max results
          <input
            type="number"
            min={3}
            max={24}
            value={maxResults}
            onChange={(e) => setMaxResults(Number(e.target.value))}
          />
        </label>
        <label>
          Min score
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
          />
        </label>
        <label>
          Session ID
          <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
        </label>
        <button onClick={() => handleSearch()} disabled={loading}>
          {loading ? 'Fetching...' : 'Search & Filter'}
        </button>
        <button onClick={handleStore} disabled={!Object.keys(selected).length || loading}>
          Store Selected
        </button>
      </div>
      {status && <div className="status">{status}</div>}
      {error && <div className="error">{error}</div>}
      <div className="gallery-region">
        {loading && (
          <div className="loading-state" role="status" aria-live="polite">
            <span className="spinner" />
            <p>Scanning creative memory...</p>
          </div>
        )}
        {!loading && !results.length && (
          <div className="empty-state">
            <VisionNyan />
            <div className="empty-graphic">
              <span />
            </div>
            <h3>Awaiting your next visual brief</h3>
            <p>Describe the vibe, medium, or subject you want and we will pull the closest matches.</p>
            <div className="prompt-chips">
              {STARTER_PROMPTS.map((prompt) => (
                <button key={prompt} type="button" onClick={() => handleSearch(prompt)}>
                  {prompt}
                </button>
              ))}
              <button
                type="button"
                className="surprise"
                onClick={() => {
                  const surprise = pickRandomPrompt();
                  handleSearch(surprise);
                }}
              >
                Surprise me
              </button>
            </div>
          </div>
        )}
        {results.length > 0 && (
          <div className="gallery-grid">
            {results.map((item) => (
              <article key={item.id} className={`gallery-card ${selected[item.id] ? 'selected' : ''}`}>
                <img src={item.thumbnail_url || item.image_url} alt={item.title || 'candidate'} loading="lazy" />
                <div className="card-body">
                  <h3>{item.title || 'Untitled'}</h3>
                  <p>{item.source || 'unknown source'}</p>
                  {item.score !== undefined && <p className="score">Score {item.score.toFixed(2)}</p>}
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={Boolean(selected[item.id])}
                      onChange={() => toggleSelection(item)}
                    />
                    Select
                  </label>
                  <a href={item.image_url} target="_blank" rel="noreferrer">
                    Open full image
                  </a>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

export default VisionGallery;
