import { useState, useCallback, useEffect } from 'react';

// Types
export interface Artifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata: Record<string, string>;
}

export interface BedZone {
  temperature: number | null;
  target: number | null;
}

export interface PrinterStatus {
  printer_id: string;
  is_online: boolean;
  is_printing: boolean;
  status: string;
  current_job: string | null;
  progress_percent: number | null;
  bed_temp: number | null;
  bed_target: number | null;
  extruder_temp: number | null;
  extruder_target: number | null;
  bed_zones?: Record<string, BedZone>;
}

export interface PrinterRecommendation {
  printer: PrinterStatus;
  recommended: boolean;
  reason: string;
  fits: boolean;
  available: boolean;
}

export interface DimensionCheckResult {
  needs_segmentation: boolean;
  dimensions: [number, number, number];
  build_volume: [number, number, number];
  exceeds_by?: [number, number, number];
}

export interface SegmentResult {
  job_id: string;
  parts: Array<{
    file_path: string;
    dimensions: [number, number, number];
  }>;
  combined_3mf_path: string;
  hardware_required?: Record<string, number>;
}

export interface SlicerSettings {
  material_id: string;
  support_type: 'none' | 'normal' | 'tree';
  infill_percent: number;
  layer_height?: number;
  nozzle_temp?: number;
  bed_temp?: number;
}

export interface SliceResult {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  gcode_path?: string;
  estimated_print_time_seconds?: number;
  estimated_filament_grams?: number;
  error?: string;
}

// Orientation types
export interface OrientationOption {
  id: string;
  label: string;
  rotation_matrix: number[][];
  up_vector: [number, number, number];
  overhang_ratio: number;
  support_estimate: 'none' | 'minimal' | 'moderate' | 'significant';
  is_recommended: boolean;
}

export interface OrientationAnalysis {
  success: boolean;
  original_dimensions: [number, number, number];
  face_count: number;
  orientations: OrientationOption[];
  best_orientation_id: string;
  analysis_time_ms: number;
  error?: string;
}

export type WorkflowStep = 1 | 2 | 3 | 4 | 5;
export type GenerationProvider = 'meshy' | 'tripo' | 'zoo' | null;
export type GenerationMode = 'generate' | 'import';
export type QualityPreset = 'quick' | 'standard' | 'quality';

export interface WorkflowState {
  currentStep: WorkflowStep;

  // Step 1: Generate
  provider: GenerationProvider;
  mode: GenerationMode;
  prompt: string;
  refineMode: boolean;  // For Meshy: run HD refine after preview
  artifacts: Artifact[];
  selectedArtifact: Artifact | null;
  generationLoading: boolean;
  generationError: string | null;
  uploadProgress: number; // 0-100 for file upload progress

  // Step 2: Orient
  orientationAnalysis: OrientationAnalysis | null;
  selectedOrientation: OrientationOption | null;
  orientedMeshPath: string | null;
  orientationSkipped: boolean;
  orientationLoading: boolean;
  orientationError: string | null;

  // Step 3: Segment
  dimensionCheck: DimensionCheckResult | null;
  segmentationRequired: boolean;
  segmentationSkipped: boolean;
  segmentResult: SegmentResult | null;
  segmentationLoading: boolean;
  segmentationError: string | null;

  // Step 4: Slice
  selectedPrinter: string | null;
  printerRecommendations: PrinterRecommendation[];
  preset: QualityPreset;
  advancedSettings: SlicerSettings;
  showAdvanced: boolean;
  sliceResult: SliceResult | null;
  slicingLoading: boolean;
  slicingError: string | null;

  // Step 5: Print
  printJobId: string | null;
  printStatus: string;
  printLoading: boolean;
}

const ARTIFACTS_BASE_URL = '/api/cad/artifacts';

export const translateArtifactPath = (location: string): string => {
  if (location.startsWith('artifacts/')) {
    return `${ARTIFACTS_BASE_URL}/${location.replace('artifacts/', '')}`;
  }
  if (location.startsWith('storage/artifacts/')) {
    return `${ARTIFACTS_BASE_URL}/${location.replace('storage/artifacts/', '')}`;
  }
  if (location.startsWith('/')) {
    const filename = location.split('/').pop() || location;
    return `${ARTIFACTS_BASE_URL}/${filename}`;
  }
  return location;
};

// Build volume lookup (mm)
const PRINTER_BUILD_VOLUMES: Record<string, [number, number, number]> = {
  bambu_h2d: [325, 320, 325],
  elegoo_giga: [800, 800, 1000],
  snapmaker_artisan: [400, 400, 400],
};

const DEFAULT_SLICER_SETTINGS: SlicerSettings = {
  material_id: 'pla_generic',
  support_type: 'tree',
  infill_percent: 20,
};

const PRESET_SETTINGS: Record<QualityPreset, Partial<SlicerSettings>> = {
  quick: { layer_height: 0.3 },
  standard: { layer_height: 0.2 },
  quality: { layer_height: 0.12 },
};

const initialState: WorkflowState = {
  currentStep: 1,

  // Step 1
  provider: 'meshy',  // Primary provider (Tripo is fallback)
  mode: 'generate',
  prompt: '',
  refineMode: false,  // HD refine disabled by default
  artifacts: [],
  selectedArtifact: null,
  generationLoading: false,
  generationError: null,
  uploadProgress: 0,

  // Step 2: Orient
  orientationAnalysis: null,
  selectedOrientation: null,
  orientedMeshPath: null,
  orientationSkipped: false,
  orientationLoading: false,
  orientationError: null,

  // Step 3: Segment
  dimensionCheck: null,
  segmentationRequired: false,
  segmentationSkipped: false,
  segmentResult: null,
  segmentationLoading: false,
  segmentationError: null,

  // Step 4: Slice
  selectedPrinter: null,
  printerRecommendations: [],
  preset: 'standard',
  advancedSettings: DEFAULT_SLICER_SETTINGS,
  showAdvanced: false,
  sliceResult: null,
  slicingLoading: false,
  slicingError: null,

  // Step 5: Print
  printJobId: null,
  printStatus: '',
  printLoading: false,
};

export interface WorkflowActions {
  // Step navigation
  goToStep: (step: WorkflowStep) => void;
  canAdvanceToStep: (step: WorkflowStep) => boolean;

  // Step 1 actions
  setProvider: (provider: GenerationProvider) => void;
  setMode: (mode: GenerationMode) => void;
  setPrompt: (prompt: string) => void;
  setRefineMode: (refine: boolean) => void;
  generateModel: () => Promise<void>;
  importModel: (file: File) => Promise<void>;
  selectArtifact: (artifact: Artifact) => void;

  // Step 2 actions (Orient)
  analyzeOrientation: () => Promise<void>;
  selectOrientation: (orientation: OrientationOption) => void;
  applyOrientation: () => Promise<void>;
  skipOrientation: () => void;

  // Step 3 actions (Segment)
  checkDimensions: (printerId?: string) => Promise<void>;
  runSegmentation: (options?: Record<string, unknown>) => Promise<void>;
  skipSegmentation: () => void;

  // Step 4 actions (Slice)
  selectPrinter: (printerId: string) => void;
  setPreset: (preset: QualityPreset) => void;
  setAdvancedSettings: (settings: Partial<SlicerSettings>) => void;
  toggleAdvanced: () => void;
  startSlicing: () => Promise<void>;
  pollSlicingStatus: (jobId: string) => Promise<SliceResult>;

  // Step 5 actions (Print)
  sendToPrinter: (startPrint: boolean) => Promise<void>;
  addToQueue: () => Promise<void>;

  // Printers
  fetchPrinters: () => Promise<void>;

  // General
  reset: () => void;
}

export function useFabricationWorkflow(): [WorkflowState, WorkflowActions, PrinterStatus[]] {
  const [state, setState] = useState<WorkflowState>(initialState);
  const [printers, setPrinters] = useState<PrinterStatus[]>([]);
  const [conversationId, setConversationId] = useState(() => `ui-${Date.now()}`);

  // Fetch printers
  const fetchPrinters = useCallback(async () => {
    try {
      const response = await fetch('/api/fabrication/printer_status');
      if (response.ok) {
        const data = await response.json();
        const printerList = Object.values(data.printers) as PrinterStatus[];
        setPrinters(printerList);

        // Update recommendations when printers change
        if (state.selectedArtifact && state.dimensionCheck) {
          updatePrinterRecommendations(printerList, state.dimensionCheck.dimensions);
        }
      }
    } catch (err) {
      console.warn('Failed to fetch printers:', err);
    }
  }, [state.selectedArtifact, state.dimensionCheck]);

  // Update printer recommendations based on model dimensions
  const updatePrinterRecommendations = useCallback((
    printerList: PrinterStatus[],
    dimensions?: [number, number, number]
  ) => {
    const recommendations: PrinterRecommendation[] = printerList.map(printer => {
      const buildVolume = PRINTER_BUILD_VOLUMES[printer.printer_id] || [200, 200, 200];
      const fits = !dimensions || (
        dimensions[0] <= buildVolume[0] &&
        dimensions[1] <= buildVolume[1] &&
        dimensions[2] <= buildVolume[2]
      );
      const available = printer.is_online && !printer.is_printing;

      let reason = '';
      if (fits && available) {
        reason = 'Fits model, available now';
      } else if (fits && !available) {
        reason = printer.is_printing
          ? `Fits model, printing ${printer.progress_percent || 0}%`
          : 'Fits model, offline';
      } else if (!fits) {
        reason = 'Model exceeds build volume';
      }

      return {
        printer,
        recommended: fits && available,
        reason,
        fits,
        available,
      };
    });

    // Sort: recommended first, then by fits, then by available
    recommendations.sort((a, b) => {
      if (a.recommended !== b.recommended) return a.recommended ? -1 : 1;
      if (a.fits !== b.fits) return a.fits ? -1 : 1;
      if (a.available !== b.available) return a.available ? -1 : 1;
      return 0;
    });

    setState(prev => ({ ...prev, printerRecommendations: recommendations }));
  }, []);

  // Poll printers periodically
  useEffect(() => {
    fetchPrinters();
    const pollInterval = state.selectedPrinter === 'elegoo_giga' ? 2000 : 10000;
    const interval = setInterval(fetchPrinters, pollInterval);
    return () => clearInterval(interval);
  }, [fetchPrinters, state.selectedPrinter]);

  // Actions
  const actions: WorkflowActions = {
    // Navigation
    goToStep: useCallback((step: WorkflowStep) => {
      setState(prev => ({ ...prev, currentStep: step }));
    }, []),

    canAdvanceToStep: useCallback((step: WorkflowStep): boolean => {
      switch (step) {
        case 1: return true;
        case 2: return state.selectedArtifact !== null;
        case 3: return state.selectedArtifact !== null &&
          (state.orientationSkipped || state.orientedMeshPath !== null);
        case 4: return state.selectedArtifact !== null &&
          (state.orientationSkipped || state.orientedMeshPath !== null) &&
          (state.segmentationSkipped || !state.segmentationRequired || state.segmentResult !== null);
        case 5: return state.sliceResult?.status === 'completed' && state.selectedPrinter !== null;
        default: return false;
      }
    }, [state.selectedArtifact, state.orientationSkipped, state.orientedMeshPath,
        state.segmentationSkipped, state.segmentationRequired, state.segmentResult,
        state.sliceResult, state.selectedPrinter]),

    // Step 1
    setProvider: useCallback((provider: GenerationProvider) => {
      setState(prev => ({ ...prev, provider }));
    }, []),

    setMode: useCallback((mode: GenerationMode) => {
      setState(prev => ({ ...prev, mode }));
    }, []),

    setPrompt: useCallback((prompt: string) => {
      setState(prev => ({ ...prev, prompt }));
    }, []),

    setRefineMode: useCallback((refineMode: boolean) => {
      setState(prev => ({ ...prev, refineMode }));
    }, []),

    generateModel: useCallback(async () => {
      if (!state.prompt.trim()) {
        setState(prev => ({ ...prev, generationError: 'Enter a prompt first' }));
        return;
      }

      setState(prev => ({
        ...prev,
        generationLoading: true,
        generationError: null,
        artifacts: [],
        selectedArtifact: null,
      }));

      try {
        const response = await fetch('/api/cad/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversationId,
            prompt: state.prompt,
            mode: state.provider === 'zoo' ? 'parametric' : 'organic',
            refine: state.refineMode,  // For Meshy: run HD refine after preview
          }),
        });

        if (!response.ok) throw new Error('CAD generation failed');

        const data = await response.json();
        const artifacts = data.artifacts as Artifact[];

        setState(prev => ({
          ...prev,
          artifacts,
          selectedArtifact: artifacts[0] || null,
          generationLoading: false,
          currentStep: artifacts.length > 0 ? 2 : 1,
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          generationLoading: false,
          generationError: (error as Error).message,
        }));
      }
    }, [state.prompt, state.provider, state.refineMode, conversationId]),

    importModel: useCallback(async (file: File) => {
      setState(prev => ({
        ...prev,
        generationLoading: true,
        generationError: null,
        uploadProgress: 0,
      }));

      const formData = new FormData();
      formData.append('file', file);

      // Use XMLHttpRequest for progress tracking
      const xhr = new XMLHttpRequest();

      const uploadPromise = new Promise<{ container_path: string }>((resolve, reject) => {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            setState(prev => ({ ...prev, uploadProgress: progress }));
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const data = JSON.parse(xhr.responseText);
              resolve(data);
            } catch {
              reject(new Error('Invalid response format'));
            }
          } else {
            reject(new Error(`Upload failed: ${xhr.statusText || 'Server error'}`));
          }
        };

        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.onabort = () => reject(new Error('Upload cancelled'));

        xhr.open('POST', '/api/fabrication/segmentation/upload');
        xhr.send(formData);
      });

      try {
        const data = await uploadPromise;
        const artifact: Artifact = {
          provider: 'import',
          artifactType: file.name.endsWith('.3mf') ? '3mf' : 'stl',
          location: data.container_path,
          metadata: { filename: file.name },
        };

        setState(prev => ({
          ...prev,
          artifacts: [artifact],
          selectedArtifact: artifact,
          generationLoading: false,
          uploadProgress: 100,
          currentStep: 2,
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          generationLoading: false,
          uploadProgress: 0,
          generationError: (error as Error).message,
        }));
      }
    }, []),

    selectArtifact: useCallback((artifact: Artifact) => {
      setState(prev => ({
        ...prev,
        selectedArtifact: artifact,
        // Reset downstream state
        orientationAnalysis: null,
        selectedOrientation: null,
        orientedMeshPath: null,
        orientationSkipped: false,
        dimensionCheck: null,
        segmentResult: null,
        sliceResult: null,
      }));
    }, []),

    // Step 2: Orientation
    analyzeOrientation: useCallback(async () => {
      if (!state.selectedArtifact) return;

      setState(prev => ({ ...prev, orientationLoading: true, orientationError: null }));

      try {
        const meshPath = state.selectedArtifact.metadata?.stl_location ||
          state.selectedArtifact.location;

        const response = await fetch('/api/fabrication/orientation/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mesh_path: meshPath,
            threshold_angle: 45.0,
            include_intermediate: false,
          }),
        });

        if (!response.ok) throw new Error('Orientation analysis failed');

        const result = await response.json() as OrientationAnalysis;

        if (!result.success) {
          throw new Error(result.error || 'Orientation analysis failed');
        }

        // Auto-select recommended orientation
        const recommended = result.orientations.find(o => o.is_recommended) || result.orientations[0];

        setState(prev => ({
          ...prev,
          orientationAnalysis: result,
          selectedOrientation: recommended,
          orientationLoading: false,
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          orientationLoading: false,
          orientationError: (error as Error).message,
        }));
      }
    }, [state.selectedArtifact]),

    selectOrientation: useCallback((orientation: OrientationOption) => {
      setState(prev => ({ ...prev, selectedOrientation: orientation }));
    }, []),

    applyOrientation: useCallback(async () => {
      if (!state.selectedArtifact || !state.selectedOrientation) return;

      setState(prev => ({ ...prev, orientationLoading: true, orientationError: null }));

      try {
        const meshPath = state.selectedArtifact.metadata?.stl_location ||
          state.selectedArtifact.location;

        const response = await fetch('/api/fabrication/orientation/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mesh_path: meshPath,
            orientation_id: state.selectedOrientation.id,
            rotation_matrix: state.selectedOrientation.rotation_matrix,
          }),
        });

        if (!response.ok) throw new Error('Failed to apply orientation');

        const result = await response.json();

        if (!result.success) {
          throw new Error(result.error || 'Failed to apply orientation');
        }

        setState(prev => ({
          ...prev,
          orientedMeshPath: result.oriented_mesh_path,
          orientationLoading: false,
          currentStep: 3,
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          orientationLoading: false,
          orientationError: (error as Error).message,
        }));
      }
    }, [state.selectedArtifact, state.selectedOrientation]),

    skipOrientation: useCallback(() => {
      setState(prev => ({
        ...prev,
        orientationSkipped: true,
        currentStep: 3,
      }));
    }, []),

    // Step 3: Segmentation
    checkDimensions: useCallback(async (printerId?: string) => {
      if (!state.selectedArtifact) return;

      setState(prev => ({ ...prev, segmentationLoading: true, segmentationError: null }));

      try {
        const stlPath = state.selectedArtifact.metadata?.stl_location ||
          state.selectedArtifact.location;

        const response = await fetch('/api/fabrication/segmentation/check', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mesh_path: stlPath,
            printer_id: printerId || state.selectedPrinter || 'bambu_h2d',
          }),
        });

        if (!response.ok) throw new Error('Dimension check failed');

        const result = await response.json() as DimensionCheckResult;

        setState(prev => ({
          ...prev,
          dimensionCheck: result,
          segmentationRequired: result.needs_segmentation,
          segmentationLoading: false,
        }));

        // Update printer recommendations with new dimensions
        updatePrinterRecommendations(printers, result.dimensions);
      } catch (error) {
        setState(prev => ({
          ...prev,
          segmentationLoading: false,
          segmentationError: (error as Error).message,
        }));
      }
    }, [state.selectedArtifact, state.selectedPrinter, printers, updatePrinterRecommendations]),

    runSegmentation: useCallback(async (options?: Record<string, unknown>) => {
      if (!state.selectedArtifact) return;

      setState(prev => ({ ...prev, segmentationLoading: true, segmentationError: null }));

      try {
        const stlPath = state.selectedArtifact.metadata?.stl_location ||
          state.selectedArtifact.location;

        const response = await fetch('/api/fabrication/segmentation/segment/async', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mesh_path: stlPath,
            printer_id: state.selectedPrinter || 'bambu_h2d',
            ...options,
          }),
        });

        if (!response.ok) throw new Error('Segmentation failed');

        const { job_id } = await response.json();

        // Poll for completion
        const pollResult = async (): Promise<SegmentResult> => {
          const statusResponse = await fetch(`/api/fabrication/segmentation/jobs/${job_id}`);
          const statusData = await statusResponse.json();

          if (statusData.status === 'completed') {
            return statusData.result;
          } else if (statusData.status === 'failed') {
            throw new Error(statusData.error || 'Segmentation failed');
          }

          await new Promise(resolve => setTimeout(resolve, 1000));
          return pollResult();
        };

        const result = await pollResult();

        setState(prev => ({
          ...prev,
          segmentResult: result,
          segmentationLoading: false,
          currentStep: 4,
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          segmentationLoading: false,
          segmentationError: (error as Error).message,
        }));
      }
    }, [state.selectedArtifact, state.selectedPrinter]),

    skipSegmentation: useCallback(() => {
      setState(prev => ({
        ...prev,
        segmentationSkipped: true,
        currentStep: 4,
      }));
    }, []),

    // Step 4: Slicing
    selectPrinter: useCallback((printerId: string) => {
      setState(prev => ({ ...prev, selectedPrinter: printerId }));
    }, []),

    setPreset: useCallback((preset: QualityPreset) => {
      setState(prev => ({
        ...prev,
        preset,
        advancedSettings: {
          ...prev.advancedSettings,
          ...PRESET_SETTINGS[preset],
        },
      }));
    }, []),

    setAdvancedSettings: useCallback((settings: Partial<SlicerSettings>) => {
      setState(prev => ({
        ...prev,
        advancedSettings: { ...prev.advancedSettings, ...settings },
      }));
    }, []),

    toggleAdvanced: useCallback(() => {
      setState(prev => ({ ...prev, showAdvanced: !prev.showAdvanced }));
    }, []),

    startSlicing: useCallback(async () => {
      if (!state.selectedArtifact || !state.selectedPrinter) return;

      setState(prev => ({ ...prev, slicingLoading: true, slicingError: null }));

      try {
        // Priority: segmented output > oriented mesh > original artifact
        const inputPath = state.segmentResult?.combined_3mf_path ||
          state.orientedMeshPath ||
          state.selectedArtifact.metadata?.stl_location ||
          state.selectedArtifact.location;

        // Include rotation matrix if orientation was applied
        const rotationMatrix = state.selectedOrientation?.rotation_matrix;

        const response = await fetch('/api/fabrication/slicer/slice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            input_path: inputPath,
            config: {
              printer_id: state.selectedPrinter,
              material_id: state.advancedSettings.material_id,
              quality: state.preset,
              support_type: state.advancedSettings.support_type,
              infill_percent: state.advancedSettings.infill_percent,
              rotation_matrix: rotationMatrix,
            },
          }),
        });

        if (!response.ok) throw new Error('Slicing request failed');

        const { job_id } = await response.json();

        // Poll for completion
        const pollSlicing = async (): Promise<SliceResult> => {
          const statusResponse = await fetch(`/api/fabrication/slicer/jobs/${job_id}`);
          const statusData = await statusResponse.json() as SliceResult;

          setState(prev => ({ ...prev, sliceResult: statusData }));

          if (statusData.status === 'completed') {
            return statusData;
          } else if (statusData.status === 'failed') {
            throw new Error(statusData.error || 'Slicing failed');
          }

          await new Promise(resolve => setTimeout(resolve, 1000));
          return pollSlicing();
        };

        const result = await pollSlicing();

        setState(prev => ({
          ...prev,
          sliceResult: result,
          slicingLoading: false,
          currentStep: 5,
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          slicingLoading: false,
          slicingError: (error as Error).message,
        }));
      }
    }, [state.selectedArtifact, state.selectedPrinter, state.segmentResult,
        state.orientedMeshPath, state.selectedOrientation, state.advancedSettings, state.preset]),

    pollSlicingStatus: useCallback(async (jobId: string): Promise<SliceResult> => {
      const response = await fetch(`/api/fabrication/slicer/jobs/${jobId}`);
      return response.json();
    }, []),

    // Step 5: Print
    sendToPrinter: useCallback(async (startPrint: boolean) => {
      if (!state.sliceResult?.job_id || !state.selectedPrinter) return;

      setState(prev => ({ ...prev, printLoading: true, printStatus: 'Uploading to printer...' }));

      try {
        const response = await fetch(`/api/fabrication/slicer/jobs/${state.sliceResult.job_id}/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            printer_id: state.selectedPrinter,
            start_print: startPrint,
          }),
        });

        if (!response.ok) throw new Error('Upload failed');

        const data = await response.json();

        setState(prev => ({
          ...prev,
          printJobId: data.job_id,
          printLoading: false,
          printStatus: startPrint
            ? 'Print started successfully!'
            : 'G-code uploaded to printer queue.',
        }));
      } catch (error) {
        setState(prev => ({
          ...prev,
          printLoading: false,
          printStatus: (error as Error).message,
        }));
      }
    }, [state.sliceResult, state.selectedPrinter]),

    addToQueue: useCallback(async () => {
      await actions.sendToPrinter(false);
    }, []),

    fetchPrinters,

    reset: useCallback(() => {
      setConversationId(`ui-${Date.now()}`);
      setState(initialState);
    }, []),
  };

  return [state, actions, printers];
}

export default useFabricationWorkflow;
