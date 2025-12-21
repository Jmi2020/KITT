/**
 * Type definitions for the Projects/Artifact Library page
 */

export interface LocalArtifact {
  filename: string;
  artifactType: string;
  category: string;
  sizeBytes: number;
  modifiedAt: string;
  downloadUrl: string;
  parentDir?: string; // For gcode: the job UUID
}

export interface ArtifactStats {
  totalCount: number;
  totalSizeBytes: number;
  byType: Record<string, number>;
  byCategory: Record<string, number>;
  mostRecent?: string;
}

export interface ProjectArtifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata: Record<string, string>;
}

export interface ProjectModel {
  projectId: string;
  conversationId: string;
  title?: string | null;
  summary?: string | null;
  artifacts: ProjectArtifact[];
  metadata: Record<string, string>;
  updatedAt: string;
}

export interface UnifiedArtifact {
  id: string;
  source: 'filesystem' | 'database';
  filename: string;
  artifactType: string;
  category: string;
  sizeBytes?: number;
  modifiedAt: string;
  downloadUrl: string;
  parentDir?: string;
  projectTitle?: string;
  conversationId?: string;
  provider?: string;
  metadata?: Record<string, string>;
}

export type ArtifactTab = 'all' | 'database' | 'local' | 'coding';
export type SortField = 'date' | 'name' | 'size' | 'type';
export type SortOrder = 'asc' | 'desc';
export type ArtifactTypeFilter = 'all' | 'stl' | 'glb' | '3mf' | 'gcode' | 'step' | 'png' | 'jpg' | 'py' | 'js' | 'ts';

/**
 * Coding project - represents a coding session with working directory and conversation
 */
export interface CodingProject {
  id: string;
  title: string;
  workingDir?: string;
  conversationId?: string;
  status: 'active' | 'completed' | 'archived';
  createdAt: string;
  updatedAt: string;
  metadata?: {
    gitRepo?: boolean;
    lastRequest?: string;
    filesGenerated?: number;
  };
}

/**
 * Coding artifact - generated code files
 */
export interface CodingArtifact {
  id: string;
  projectId: string;
  filename: string;
  language: 'python' | 'javascript' | 'typescript' | 'other';
  path: string;
  sizeBytes: number;
  createdAt: string;
}

export const ARTIFACT_TYPE_INFO: Record<string, { icon: string; color: string; label: string }> = {
  stl: { icon: '📐', color: '#3b82f6', label: 'STL' },
  glb: { icon: '🎨', color: '#8b5cf6', label: 'GLB' },
  gltf: { icon: '🎨', color: '#8b5cf6', label: 'GLTF' },
  '3mf': { icon: '🖨️', color: '#10b981', label: '3MF' },
  step: { icon: '🔧', color: '#f59e0b', label: 'STEP' },
  gcode: { icon: '⚙️', color: '#ef4444', label: 'G-Code' },
  png: { icon: '🖼️', color: '#ec4899', label: 'PNG' },
  jpg: { icon: '🖼️', color: '#ec4899', label: 'JPG' },
  py: { icon: '🐍', color: '#3776ab', label: 'Python' },
  js: { icon: '📜', color: '#f7df1e', label: 'JavaScript' },
  ts: { icon: '📘', color: '#3178c6', label: 'TypeScript' },
};

export const CATEGORY_INFO: Record<string, { label: string; color: string }> = {
  mesh: { label: 'Mesh', color: '#3b82f6' },
  printable: { label: 'Printable', color: '#10b981' },
  cad: { label: 'CAD', color: '#f59e0b' },
  instruction: { label: 'Instruction', color: '#ef4444' },
  image: { label: 'Image', color: '#ec4899' },
  code: { label: 'Code', color: '#3776ab' },
};
