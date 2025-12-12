/**
 * Types for Media Hub - Image generation and gallery
 */

// === Gallery Types ===
export interface ImageResult {
  id: string;
  title?: string;
  description?: string;
  image_url: string;
  thumbnail_url?: string;
  source?: string;
  score?: number;
  clip_score?: number;
}

export interface SearchResult {
  results: ImageResult[];
  total?: number;
}

export interface FilterResult {
  results: ImageResult[];
}

export interface StoreRequest {
  session_id: string;
  images: {
    id: string;
    image_url: string;
    title?: string;
    source?: string;
    caption?: string;
  }[];
}

export interface StoreResponse {
  session_id: string;
  stored: { id: string }[];
}

// === Generator Types ===
export interface GenerateRequest {
  prompt: string;
  width: number;
  height: number;
  steps: number;
  cfg: number;
  seed?: number;
  model: string;
  refiner?: string;
}

export interface JobStatusResponse {
  status: 'queued' | 'started' | 'finished' | 'failed';
  result?: {
    png_key: string;
    meta_key: string;
  };
  error?: string;
}

export interface RecentImage {
  key: string;
  size: number;
  last_modified: string;
}

// === Configuration ===
export interface ModelConfig {
  value: string;
  label: string;
}

export interface SizeConfig {
  width: number;
  height: number;
  label: string;
}

export const MODELS: ModelConfig[] = [
  { value: 'sdxl_base', label: 'SDXL Base (1024x1024)' },
  { value: 'sd15_base', label: 'SD 1.5 (512x512, faster)' },
];

export const SIZES: SizeConfig[] = [
  { width: 512, height: 512, label: '512x512' },
  { width: 768, height: 768, label: '768x768' },
  { width: 1024, height: 1024, label: '1024x1024' },
  { width: 1024, height: 768, label: '1024x768' },
  { width: 768, height: 1024, label: '768x1024' },
];

export const GALLERY_STARTER_PROMPTS = [
  'neon-lit robotics lab surveillance shot',
  'macro photo of bio-luminescent coral drone',
  'studio render of modular robot arm for surgery',
  'retro-futurist rover exploring a sandstorm',
  'architectural axonometric of floating research hub',
];

export const GENERATOR_STARTER_PROMPTS = [
  'studio photo of a matte black water bottle',
  'futuristic drone with 4 propellers',
  'minimalist phone stand with cable routing',
  'mechanical keyboard with RGB lighting',
  'ergonomic 3D printed bracket',
  'modular organizer tray with compartments',
];
