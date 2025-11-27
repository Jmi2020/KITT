/**
 * KITTY Function Definitions
 *
 * Maps voice commands and tool calls to KITTY service endpoints.
 * Adapted from Jarvis function patterns to work with KITTY's API structure.
 */

export interface FunctionDefinition {
  name: string;
  description: string;
  parameters: {
    type: 'object';
    properties: Record<string, { type: string; description: string; enum?: string[] }>;
    required?: string[];
  };
  handler: (args: Record<string, unknown>) => Promise<unknown>;
}

/**
 * Create an AI-generated image.
 */
const createImage: FunctionDefinition = {
  name: 'create_image',
  description: 'Generate an AI image from a text prompt',
  parameters: {
    type: 'object',
    properties: {
      prompt: {
        type: 'string',
        description: 'Description of the image to generate',
      },
      size: {
        type: 'string',
        description: 'Image size (square, portrait, landscape)',
        enum: ['square', 'portrait', 'landscape'],
      },
      style: {
        type: 'string',
        description: 'Image style',
        enum: ['realistic', 'artistic', 'sketch', 'cartoon'],
      },
    },
    required: ['prompt'],
  },
  handler: async (args) => {
    const response = await fetch('/api/images/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: args.prompt,
        size: args.size || 'square',
        style: args.style || 'realistic',
      }),
    });
    return response.json();
  },
};

/**
 * Create a 3D model from text.
 */
const create3DModel: FunctionDefinition = {
  name: 'create_3d_model',
  description: 'Generate a 3D model from a text description',
  parameters: {
    type: 'object',
    properties: {
      prompt: {
        type: 'string',
        description: 'Description of the 3D model to generate',
      },
      format: {
        type: 'string',
        description: 'Output format',
        enum: ['stl', 'glb', 'both'],
      },
    },
    required: ['prompt'],
  },
  handler: async (args) => {
    const response = await fetch('/api/cad/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: args.prompt,
        format: args.format || 'both',
        provider: 'auto',
      }),
    });
    return response.json();
  },
};

/**
 * Navigate to a page in the UI.
 */
const navigateToPage: FunctionDefinition = {
  name: 'navigate_to_page',
  description: 'Navigate to a specific page in the KITTY interface',
  parameters: {
    type: 'object',
    properties: {
      page: {
        type: 'string',
        description: 'Page to navigate to',
        enum: [
          'dashboard',
          'shell',
          'voice',
          'projects',
          'console',
          'images',
          'research',
          'cameras',
          'inventory',
          'calendar',
        ],
      },
    },
    required: ['page'],
  },
  handler: async (args) => {
    // This is handled client-side
    window.dispatchEvent(
      new CustomEvent('kitty:navigate', { detail: { page: args.page } })
    );
    return { success: true, navigated_to: args.page };
  },
};

/**
 * Search for files in the project storage.
 */
const searchFiles: FunctionDefinition = {
  name: 'search_files',
  description: 'Search for files in KITTY storage',
  parameters: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Search query (filename or pattern)',
      },
      type: {
        type: 'string',
        description: 'File type filter',
        enum: ['stl', 'gcode', 'image', 'all'],
      },
    },
    required: ['query'],
  },
  handler: async (args) => {
    const params = new URLSearchParams({
      q: args.query as string,
      type: (args.type as string) || 'all',
    });
    const response = await fetch(`/api/projects/local/list?${params}`);
    return response.json();
  },
};

/**
 * Open a file for viewing or editing.
 */
const openFile: FunctionDefinition = {
  name: 'open_file',
  description: 'Open a file from KITTY storage',
  parameters: {
    type: 'object',
    properties: {
      path: {
        type: 'string',
        description: 'Path to the file',
      },
    },
    required: ['path'],
  },
  handler: async (args) => {
    // For STL files, open in slicer
    if ((args.path as string).endsWith('.stl')) {
      const response = await fetch('/api/fabrication/open_in_slicer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stl_path: args.path }),
      });
      return response.json();
    }
    // For other files, return URL
    return { url: `/storage/${args.path}`, path: args.path };
  },
};

/**
 * Capture images from cameras.
 */
const captureImages: FunctionDefinition = {
  name: 'capture_images',
  description: 'Capture images from printer cameras',
  parameters: {
    type: 'object',
    properties: {
      printer_id: {
        type: 'string',
        description: 'Printer to capture from',
        enum: ['bamboo_h2d', 'elegoo_giga', 'snapmaker_artisan', 'all'],
      },
      job_id: {
        type: 'string',
        description: 'Job ID to associate with snapshot',
      },
    },
    required: ['printer_id'],
  },
  handler: async (args) => {
    const printerId = args.printer_id === 'all' ? 'bamboo_h2d' : args.printer_id;
    const response = await fetch(`/api/fabrication/cameras/${printerId}/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: args.job_id || `manual_${Date.now()}`,
        milestone: 'manual',
      }),
    });
    return response.json();
  },
};

/**
 * Get printer status.
 */
const getPrinterStatus: FunctionDefinition = {
  name: 'get_printer_status',
  description: 'Get status of 3D printers',
  parameters: {
    type: 'object',
    properties: {
      printer_id: {
        type: 'string',
        description: 'Specific printer or "all"',
        enum: ['bamboo_h2d', 'elegoo_giga', 'snapmaker_artisan', 'all'],
      },
    },
  },
  handler: async (args) => {
    // First try Bambu cloud for cloud-connected printers
    try {
      const bambuResponse = await fetch('/api/bambu/telemetry');
      if (bambuResponse.ok) {
        const bambuData = await bambuResponse.json();
        if (args.printer_id && args.printer_id !== 'all') {
          return bambuData[args.printer_id as string] || { error: 'Printer not found' };
        }
        return bambuData;
      }
    } catch {
      // Fall through to fabrication service
    }

    // Fallback to fabrication service
    const response = await fetch('/api/fabrication/printer_status');
    const data = await response.json();

    if (args.printer_id && args.printer_id !== 'all') {
      return data.printers?.[args.printer_id as string] || { error: 'Printer not found' };
    }
    return data;
  },
};

/**
 * Control a printer (pause, resume, stop).
 */
const controlPrinter: FunctionDefinition = {
  name: 'control_printer',
  description: 'Control a 3D printer (pause, resume, stop)',
  parameters: {
    type: 'object',
    properties: {
      printer_id: {
        type: 'string',
        description: 'Printer to control',
      },
      command: {
        type: 'string',
        description: 'Command to send',
        enum: ['pause', 'resume', 'stop'],
      },
    },
    required: ['printer_id', 'command'],
  },
  handler: async (args) => {
    const response = await fetch(`/api/bambu/printers/${args.printer_id}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: args.command }),
    });
    return response.json();
  },
};

/**
 * Start a research session.
 */
const startResearch: FunctionDefinition = {
  name: 'start_research',
  description: 'Start a web research session on a topic',
  parameters: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Research topic or question',
      },
      depth: {
        type: 'string',
        description: 'Research depth',
        enum: ['quick', 'standard', 'deep'],
      },
    },
    required: ['query'],
  },
  handler: async (args) => {
    const response = await fetch('/api/research/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: args.query,
        depth: args.depth || 'standard',
      }),
    });
    return response.json();
  },
};

/**
 * Analyze a camera view with vision model.
 */
const analyzeCameraView: FunctionDefinition = {
  name: 'analyze_camera_view',
  description: 'Analyze a camera view using vision AI',
  parameters: {
    type: 'object',
    properties: {
      printer_id: {
        type: 'string',
        description: 'Camera/printer to analyze',
      },
      question: {
        type: 'string',
        description: 'What to analyze or check',
      },
    },
    required: ['printer_id'],
  },
  handler: async (args) => {
    // First capture a snapshot
    const captureResponse = await fetch(`/api/fabrication/cameras/${args.printer_id}/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: `analysis_${Date.now()}`,
        milestone: 'analysis',
      }),
    });
    const capture = await captureResponse.json();

    if (!capture.success) {
      return { error: 'Failed to capture image', details: capture };
    }

    // Then analyze with vision model
    const analyzeResponse = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: args.question || 'Describe what you see in this image',
        image_url: capture.url,
        model: 'vision',
      }),
    });
    return analyzeResponse.json();
  },
};

/**
 * Check material inventory.
 */
const checkInventory: FunctionDefinition = {
  name: 'check_inventory',
  description: 'Check material inventory levels',
  parameters: {
    type: 'object',
    properties: {
      material_type: {
        type: 'string',
        description: 'Filter by material type',
        enum: ['pla', 'petg', 'abs', 'tpu', 'all'],
      },
      low_only: {
        type: 'string',
        description: 'Only show low inventory items',
        enum: ['true', 'false'],
      },
    },
  },
  handler: async (args) => {
    if (args.low_only === 'true') {
      const response = await fetch('/api/fabrication/inventory/low');
      return response.json();
    }

    const params = new URLSearchParams();
    if (args.material_type && args.material_type !== 'all') {
      params.set('material_type', args.material_type as string);
    }

    const response = await fetch(`/api/fabrication/inventory?${params}`);
    return response.json();
  },
};

/**
 * Check print readiness and available printers.
 */
const checkPrintStatus: FunctionDefinition = {
  name: 'check_print_status',
  description: 'Check if printers are available and ready for printing',
  parameters: {
    type: 'object',
    properties: {},
  },
  handler: async () => {
    const response = await fetch('/api/cad/print-status');
    return response.json();
  },
};

/**
 * Queue a model for printing.
 */
const queuePrint: FunctionDefinition = {
  name: 'queue_print',
  description: 'Queue a generated 3D model for printing on a Bambu printer',
  parameters: {
    type: 'object',
    properties: {
      artifact_path: {
        type: 'string',
        description: 'Path to the STL or 3MF file',
      },
      printer_id: {
        type: 'string',
        description: 'Target printer ID (auto-select if not provided)',
      },
      material: {
        type: 'string',
        description: 'Material type (pla, petg, abs, tpu)',
      },
    },
    required: ['artifact_path'],
  },
  handler: async (args) => {
    const response = await fetch('/api/cad/queue-print', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        artifact_path: args.artifact_path,
        printer_id: args.printer_id,
        material: args.material,
      }),
    });
    return response.json();
  },
};

/**
 * Get AMS filament materials loaded in printers.
 */
const getLoadedMaterials: FunctionDefinition = {
  name: 'get_loaded_materials',
  description: 'Get the filament materials currently loaded in Bambu printer AMS units',
  parameters: {
    type: 'object',
    properties: {},
  },
  handler: async () => {
    const response = await fetch('/api/cad/ams-materials');
    return response.json();
  },
};

/**
 * All available KITTY functions.
 */
export const kittyFunctions: FunctionDefinition[] = [
  createImage,
  create3DModel,
  navigateToPage,
  searchFiles,
  openFile,
  captureImages,
  getPrinterStatus,
  controlPrinter,
  startResearch,
  analyzeCameraView,
  checkInventory,
  checkPrintStatus,
  queuePrint,
  getLoadedMaterials,
];

/**
 * Get function definition by name.
 */
export function getFunction(name: string): FunctionDefinition | undefined {
  return kittyFunctions.find((f) => f.name === name);
}

/**
 * Get all function schemas (for sending to LLM).
 */
export function getFunctionSchemas() {
  return kittyFunctions.map((f) => ({
    name: f.name,
    description: f.description,
    parameters: f.parameters,
  }));
}
