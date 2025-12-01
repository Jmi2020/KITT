/**
 * Voice mode definitions for the KITTY voice assistant.
 * Each mode configures different tool access and processing preferences.
 */

export interface VoiceMode {
  id: string;
  name: string;
  icon: string;
  description: string;
  allowPaid: boolean;
  preferLocal: boolean;
  enabledTools: string[];
  color: string;
  bgClass: string;
  borderClass: string;
  glowClass: string;
  isCustom?: boolean;
}

/** Color presets for voice modes with Tailwind classes */
export const MODE_COLOR_PRESETS = {
  cyan: { bgClass: 'bg-cyan-500/10', borderClass: 'border-cyan-500/50', glowClass: 'shadow-cyan-500/30' },
  orange: { bgClass: 'bg-orange-500/10', borderClass: 'border-orange-500/50', glowClass: 'shadow-orange-500/30' },
  purple: { bgClass: 'bg-purple-500/10', borderClass: 'border-purple-500/50', glowClass: 'shadow-purple-500/30' },
  green: { bgClass: 'bg-green-500/10', borderClass: 'border-green-500/50', glowClass: 'shadow-green-500/30' },
  pink: { bgClass: 'bg-pink-500/10', borderClass: 'border-pink-500/50', glowClass: 'shadow-pink-500/30' },
  blue: { bgClass: 'bg-blue-500/10', borderClass: 'border-blue-500/50', glowClass: 'shadow-blue-500/30' },
  red: { bgClass: 'bg-red-500/10', borderClass: 'border-red-500/50', glowClass: 'shadow-red-500/30' },
  yellow: { bgClass: 'bg-yellow-500/10', borderClass: 'border-yellow-500/50', glowClass: 'shadow-yellow-500/30' },
} as const;

export type ModeColorName = keyof typeof MODE_COLOR_PRESETS;

/** Tool categories with all available tools */
export const AVAILABLE_TOOLS = {
  CAD: [
    { id: 'generate_cad_model', name: 'Generate CAD Model', description: 'Generate 3D CAD models from text descriptions', paid: true },
  ],
  Research: [
    { id: 'web_search', name: 'Web Search', description: 'Search the web using DuckDuckGo (free)', paid: false },
    { id: 'research_deep', name: 'Deep Research', description: 'Deep research using Perplexity AI', paid: true },
    { id: 'fetch_webpage', name: 'Fetch Webpage', description: 'Fetch and parse web pages', paid: false },
    { id: 'get_citations', name: 'Get Citations', description: 'Get formatted citations', paid: false },
    { id: 'reset_research_session', name: 'Reset Research', description: 'Clear research session', paid: false },
  ],
  'Home Assistant': [
    { id: 'control_device', name: 'Control Device', description: 'Control HA devices', paid: false },
    { id: 'get_entity_state', name: 'Get Entity State', description: 'Get entity state', paid: false },
    { id: 'list_entities', name: 'List Entities', description: 'List all entities', paid: false },
  ],
  Vision: [
    { id: 'image_search', name: 'Image Search', description: 'Search for images', paid: false },
    { id: 'image_filter', name: 'Image Filter', description: 'Score image relevance', paid: false },
    { id: 'store_selection', name: 'Store Selection', description: 'Store reference images', paid: false },
  ],
  'Image Generation': [
    { id: 'generate_image', name: 'Generate Image', description: 'Generate images with Stable Diffusion (local)', paid: false },
    { id: 'image_job_status', name: 'Check Job Status', description: 'Check image generation job status', paid: false },
    { id: 'list_generated_images', name: 'List Images', description: 'List recently generated images', paid: false },
  ],
  Memory: [
    { id: 'store_memory', name: 'Store Memory', description: 'Store semantic memories', paid: false },
    { id: 'recall_memory', name: 'Recall Memory', description: 'Search memories', paid: false },
    { id: 'delete_memory', name: 'Delete Memory', description: 'Delete memories', paid: false },
  ],
  Fabrication: [
    { id: 'fabrication.open_in_slicer', name: 'Open in Slicer', description: 'Open model in slicer', paid: false },
    { id: 'fabrication.analyze_model', name: 'Analyze Model', description: 'Analyze STL dimensions', paid: false },
    { id: 'fabrication.printer_status', name: 'Printer Status', description: 'Check printer status', paid: false },
  ],
  Discovery: [
    { id: 'discover_devices', name: 'Discover Devices', description: 'Scan network for devices', paid: false },
    { id: 'list_devices', name: 'List Devices', description: 'List discovered devices', paid: false },
    { id: 'search_devices', name: 'Search Devices', description: 'Search devices', paid: false },
    { id: 'get_device_status', name: 'Get Device Status', description: 'Get device status', paid: false },
    { id: 'approve_device', name: 'Approve Device', description: 'Approve device', paid: false },
    { id: 'reject_device', name: 'Reject Device', description: 'Reject device', paid: false },
    { id: 'list_printers', name: 'List Printers', description: 'List printers', paid: false },
  ],
  Reasoning: [
    { id: 'reason_with_f16', name: 'Reason with F16', description: 'Delegate to local GPTOSS 120B reasoning engine', paid: false },
  ],
} as const;

export type ToolCategory = keyof typeof AVAILABLE_TOOLS;

export const VOICE_MODES: VoiceMode[] = [
  {
    id: 'basic',
    name: 'Basic',
    icon: '💬',
    description: 'General conversation using local models',
    allowPaid: false,
    preferLocal: true,
    enabledTools: [],
    color: 'cyan',
    bgClass: 'bg-cyan-500/10',
    borderClass: 'border-cyan-500/50',
    glowClass: 'shadow-cyan-500/30',
  },
  {
    id: 'maker',
    name: 'Maker',
    icon: '🔧',
    description: 'CAD generation and 3D modeling enabled',
    allowPaid: true,
    preferLocal: false,
    enabledTools: ['generate_cad_model', 'web_search', 'image_search'],
    color: 'orange',
    bgClass: 'bg-orange-500/10',
    borderClass: 'border-orange-500/50',
    glowClass: 'shadow-orange-500/30',
  },
  {
    id: 'research',
    name: 'Research',
    icon: '🔬',
    description: 'Deep web search and analysis enabled',
    allowPaid: true,
    preferLocal: false,
    enabledTools: ['web_search', 'research_deep', 'reason_with_f16'],
    color: 'purple',
    bgClass: 'bg-purple-500/10',
    borderClass: 'border-purple-500/50',
    glowClass: 'shadow-purple-500/30',
  },
  {
    id: 'home',
    name: 'Smart Home',
    icon: '🏠',
    description: 'Control lights, devices, automation',
    allowPaid: false,
    preferLocal: true,
    enabledTools: ['control_device', 'query_sensors', 'set_automation'],
    color: 'green',
    bgClass: 'bg-green-500/10',
    borderClass: 'border-green-500/50',
    glowClass: 'shadow-green-500/30',
  },
  {
    id: 'creative',
    name: 'Creative',
    icon: '🎨',
    description: 'Image generation and writing assistance',
    allowPaid: true,
    preferLocal: false,
    enabledTools: ['generate_image', 'web_search', 'reason_with_f16'],
    color: 'pink',
    bgClass: 'bg-pink-500/10',
    borderClass: 'border-pink-500/50',
    glowClass: 'shadow-pink-500/30',
  },
];

export function getModeById(id: string): VoiceMode | undefined {
  return VOICE_MODES.find((m) => m.id === id);
}

export function getDefaultMode(): VoiceMode {
  return VOICE_MODES[0]; // basic mode
}

/** Get all modes including custom ones */
export function getAllModes(customModes: VoiceMode[] = []): VoiceMode[] {
  return [...VOICE_MODES, ...customModes];
}

/** Find mode by ID across both system and custom modes */
export function findModeById(id: string, customModes: VoiceMode[] = []): VoiceMode | undefined {
  return getAllModes(customModes).find((m) => m.id === id);
}

/** Create color classes from a color name */
export function getColorClasses(colorName: string): { bgClass: string; borderClass: string; glowClass: string } {
  return MODE_COLOR_PRESETS[colorName as ModeColorName] || MODE_COLOR_PRESETS.cyan;
}

/** Create a new custom mode with defaults */
export function createEmptyMode(): VoiceMode {
  return {
    id: `custom_${Date.now()}`,
    name: 'New Mode',
    icon: '⚡',
    description: '',
    allowPaid: false,
    preferLocal: true,
    enabledTools: [],
    color: 'cyan',
    ...MODE_COLOR_PRESETS.cyan,
    isCustom: true,
  };
}

/** Duplicate a mode with a new ID */
export function duplicateMode(mode: VoiceMode): VoiceMode {
  return {
    ...mode,
    id: `custom_${Date.now()}`,
    name: `Copy of ${mode.name}`,
    isCustom: true,
  };
}

export type VoiceModeId = 'basic' | 'maker' | 'research' | 'home' | 'creative';
