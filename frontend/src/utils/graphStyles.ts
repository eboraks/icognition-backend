/**
 * Shared graph node styling config — single source of truth for colors and shapes.
 * Cytoscape shape values: 'ellipse' | 'rectangle' | 'diamond' | 'hexagon' | 'triangle' | 'star' etc.
 */

import personIcon from '@/assets/images/graph_icons/user_14724037.png'
import organizationIcon from '@/assets/images/graph_icons/office_9702976.png'
import locationIcon from '@/assets/images/graph_icons/country_17942527.png'
import documentIcon from '@/assets/images/graph_icons/article_1959778.png'

export interface NodeStyle {
  color: string
  shape: string
  icon?: string
}

export const NODE_STYLES: Record<string, NodeStyle> = {
  // Entities
  person:            { color: '#4F46E5', shape: 'ellipse', icon: personIcon },         // indigo
  organization:      { color: '#059669', shape: 'ellipse', icon: organizationIcon },   // emerald
  institution:       { color: '#047857', shape: 'ellipse', icon: organizationIcon },   // emerald-dark
  location:          { color: '#DC2626', shape: 'ellipse', icon: locationIcon },       // red
  event:             { color: '#0891B2', shape: 'triangle' },        // cyan
  technology:        { color: '#0284C7', shape: 'round-rectangle' }, // sky blue
  product:           { color: '#EA580C', shape: 'barrel' },          // orange-red
  science:           { color: '#7C3AED', shape: 'diamond' },         // violet
  medical_condition: { color: '#E11D48', shape: 'diamond' },         // rose
  organism:          { color: '#16A34A', shape: 'hexagon' },         // green
  regulation:        { color: '#4338CA', shape: 'round-rectangle' }, // indigo-dark
  financial:         { color: '#CA8A04', shape: 'diamond' },         // yellow-dark
  creative_work:     { color: '#C026D3', shape: 'round-rectangle' }, // fuchsia
  concept:           { color: '#6D28D9', shape: 'diamond' },         // purple
  // Legacy type (existing data)
  topic:             { color: '#6D28D9', shape: 'diamond' },         // purple (same as concept)
  // Document nodes
  document:          { color: '#D97706', shape: 'rectangle', icon: documentIcon }, // amber
}

const DEFAULT_STYLE: NodeStyle = { color: '#6B7280', shape: 'ellipse' }

export function getNodeStyle(type: string): NodeStyle {
  return NODE_STYLES[type.toLowerCase()] ?? DEFAULT_STYLE
}

export function getNodeColor(type: string): string {
  return getNodeStyle(type).color
}

export function getNodeShape(type: string): string {
  return getNodeStyle(type).shape
}
