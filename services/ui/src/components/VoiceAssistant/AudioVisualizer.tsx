import { CodeCircleVisualizer } from './CodeCircleVisualizer';

// Re-export props interface for compatibility
export interface AudioVisualizerProps {
  fftData: number[];
  audioLevel: number;
  status: 'idle' | 'listening' | 'responding' | 'error';
  isProcessing?: boolean;
  progress?: number | null;
  size?: number;
  modeColor?: 'cyan' | 'orange' | 'purple' | 'green' | 'pink';
  enable3D?: boolean;
  visualizerMode?: 'ring' | 'wave' | 'code'; // Added 'code'
}

/**
 * Main Visualizer Component
 * Now defaults to the "Code Circle" design requested.
 */
export function AudioVisualizer(props: AudioVisualizerProps) {
  // Default to code visualizer as requested
  if (props.visualizerMode === 'code' || !props.visualizerMode || props.visualizerMode === 'ring') {
    return <CodeCircleVisualizer {...props} />;
  }

  // Fallback or legacy modes could go here if needed, 
  // but for now we replace the primary experience.
  return <CodeCircleVisualizer {...props} />;
}
