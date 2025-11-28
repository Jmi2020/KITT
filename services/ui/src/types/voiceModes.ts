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
}

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

export type VoiceModeId = 'basic' | 'maker' | 'research' | 'home' | 'creative';
