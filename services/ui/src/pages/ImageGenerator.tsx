import { useState } from 'react';
import './ImageGenerator.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8080';

interface GenerateRequest {
  prompt: string;
  width: number;
  height: number;
  steps: number;
  cfg: number;
  seed?: number;
  model: string;
  refiner?: string;
}

interface JobStatusResponse {
  status: string;
  result?: {
    png_key: string;
    meta_key: string;
  };
  error?: string;
}

interface ImageItem {
  key: string;
  size: number;
  last_modified: string;
}

const STARTER_PROMPTS = [
  'studio photo of a matte black water bottle',
  'futuristic drone with 4 propellers',
  'minimalist phone stand with cable routing',
  'mechanical keyboard with RGB lighting',
  'ergonomic 3D printed bracket',
  'modular organizer tray with compartments',
];

const MODELS = [
  { value: 'sdxl_base', label: 'SDXL Base (1024x1024)' },
  { value: 'sd15_base', label: 'SD 1.5 (512x512, faster)' },
];

const SIZES = [
  { width: 512, height: 512, label: '512×512' },
  { width: 768, height: 768, label: '768×768' },
  { width: 1024, height: 1024, label: '1024×1024' },
  { width: 1024, height: 768, label: '1024×768' },
  { width: 768, height: 1024, label: '768×1024' },
];

const ImageGenerator = () => {
  const [prompt, setPrompt] = useState('');
  const [width, setWidth] = useState(1024);
  const [height, setHeight] = useState(1024);
  const [steps, setSteps] = useState(30);
  const [cfg, setCfg] = useState(7.0);
  const [seed, setSeed] = useState<string>('');
  const [model, setModel] = useState('sdxl_base');
  const [useRefiner, setUseRefiner] = useState(false);

  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [generatedImage, setGeneratedImage] = useState<string | null>(null);

  const [recentImages, setRecentImages] = useState<ImageItem[]>([]);
  const [showRecent, setShowRecent] = useState(false);

  const pickRandomPrompt = () => {
    const randomPrompt = STARTER_PROMPTS[Math.floor(Math.random() * STARTER_PROMPTS.length)];
    setPrompt(randomPrompt);
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setError('Enter a prompt to generate an image.');
      return;
    }

    setError('');
    setStatus('Submitting job...');
    setLoading(true);
    setGeneratedImage(null);

    const payload: GenerateRequest = {
      prompt: prompt.trim(),
      width,
      height,
      steps,
      cfg,
      model,
    };

    if (seed.trim()) {
      payload.seed = parseInt(seed);
    }

    if (useRefiner && model === 'sdxl_base') {
      payload.refiner = 'sdxl_refiner';
    }

    try {
      // Submit generation job
      const generateResponse = await fetch(`${API_BASE}/api/images/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!generateResponse.ok) {
        throw new Error(`Generation failed (${generateResponse.status})`);
      }

      const generateData = await generateResponse.json();
      const jobId = generateData.job_id;

      if (!jobId) {
        throw new Error('No job ID returned');
      }

      setCurrentJobId(jobId);
      setStatus(`Job queued: ${jobId}`);

      // Poll for completion
      await pollJobStatus(jobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed');
      setStatus('');
      setLoading(false);
    }
  };

  const pollJobStatus = async (jobId: string) => {
    const maxAttempts = 60; // 2 minutes max
    let attempts = 0;

    const poll = async () => {
      try {
        const statusResponse = await fetch(`${API_BASE}/api/images/jobs/${jobId}`);
        if (!statusResponse.ok) {
          throw new Error(`Status check failed (${statusResponse.status})`);
        }

        const statusData: JobStatusResponse = await statusResponse.json();

        if (statusData.status === 'finished' && statusData.result) {
          setStatus('Image generated successfully!');
          setGeneratedImage(statusData.result.png_key);
          setLoading(false);
          return;
        }

        if (statusData.status === 'failed') {
          throw new Error(statusData.error || 'Generation failed');
        }

        // Still processing
        if (statusData.status === 'queued') {
          setStatus('Waiting in queue...');
        } else if (statusData.status === 'started') {
          setStatus('Generating image...');
        }

        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 2000); // Poll every 2 seconds
        } else {
          throw new Error('Generation timed out');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Status check failed');
        setStatus('');
        setLoading(false);
      }
    };

    poll();
  };

  const loadRecentImages = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/images/latest?limit=20`);
      if (!response.ok) {
        throw new Error(`Failed to load recent images (${response.status})`);
      }
      const data = await response.json();
      setRecentImages(data.items || []);
      setShowRecent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load recent images');
    }
  };

  const getImageUrl = (key: string) => {
    // Construct MinIO URL
    const endpoint = import.meta.env.VITE_MINIO_ENDPOINT ?? 'http://localhost:9000';
    const bucket = 'kitty-artifacts';
    return `${endpoint}/${bucket}/${key}`;
  };

  return (
    <div className="image-generator">
      <div className="generator-header">
        <h2>🎨 Stable Diffusion Image Generator</h2>
        <p className="subtitle">Local text-to-image generation with Apple Silicon MPS acceleration</p>
      </div>

      <div className="generator-container">
        <div className="generator-form">
          <div className="form-group">
            <label>Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the image you want to generate..."
              rows={3}
              disabled={loading}
            />
            <button
              onClick={pickRandomPrompt}
              className="btn-secondary"
              disabled={loading}
            >
              Random Prompt
            </button>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Model</label>
              <select value={model} onChange={(e) => setModel(e.target.value)} disabled={loading}>
                {MODELS.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Size</label>
              <select
                value={`${width}x${height}`}
                onChange={(e) => {
                  const [w, h] = e.target.value.split('x').map(Number);
                  setWidth(w);
                  setHeight(h);
                }}
                disabled={loading}
              >
                {SIZES.map((size) => (
                  <option key={`${size.width}x${size.height}`} value={`${size.width}x${size.height}`}>
                    {size.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Steps: {steps}</label>
              <input
                type="range"
                min="10"
                max="50"
                value={steps}
                onChange={(e) => setSteps(parseInt(e.target.value))}
                disabled={loading}
              />
            </div>

            <div className="form-group">
              <label>Guidance Scale: {cfg.toFixed(1)}</label>
              <input
                type="range"
                min="1"
                max="15"
                step="0.5"
                value={cfg}
                onChange={(e) => setCfg(parseFloat(e.target.value))}
                disabled={loading}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Seed (optional)</label>
              <input
                type="text"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder="Random"
                disabled={loading}
              />
            </div>

            {model === 'sdxl_base' && (
              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={useRefiner}
                    onChange={(e) => setUseRefiner(e.target.checked)}
                    disabled={loading}
                  />
                  Use SDXL Refiner (slower, better quality)
                </label>
              </div>
            )}
          </div>

          <div className="form-actions">
            <button
              onClick={handleGenerate}
              className="btn-primary"
              disabled={loading || !prompt.trim()}
            >
              {loading ? 'Generating...' : 'Generate Image'}
            </button>

            <button
              onClick={loadRecentImages}
              className="btn-secondary"
              disabled={loading}
            >
              View Recent
            </button>
          </div>

          {status && <div className="status-message">{status}</div>}
          {error && <div className="error-message">{error}</div>}
        </div>

        <div className="generator-preview">
          {generatedImage ? (
            <div className="generated-image-container">
              <img
                src={getImageUrl(generatedImage)}
                alt="Generated"
                className="generated-image"
              />
              <div className="image-info">
                <p><strong>S3 Key:</strong> {generatedImage}</p>
                <a
                  href={getImageUrl(generatedImage)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-secondary"
                >
                  Open Full Size
                </a>
              </div>
            </div>
          ) : (
            <div className="preview-placeholder">
              <p>Generated image will appear here</p>
              {loading && <div className="spinner"></div>}
            </div>
          )}
        </div>
      </div>

      {showRecent && (
        <div className="recent-images">
          <div className="recent-header">
            <h3>Recent Generations</h3>
            <button onClick={() => setShowRecent(false)} className="btn-close">×</button>
          </div>
          <div className="recent-grid">
            {recentImages.map((item) => (
              <div key={item.key} className="recent-item" onClick={() => setGeneratedImage(item.key)}>
                <img
                  src={getImageUrl(item.key)}
                  alt={item.key}
                  loading="lazy"
                />
                <div className="recent-info">
                  <span className="recent-size">{(item.size / 1024).toFixed(0)} KB</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ImageGenerator;
