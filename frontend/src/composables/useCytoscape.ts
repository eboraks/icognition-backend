import { ref, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import coseBilkent from 'cytoscape-cose-bilkent'
import { NODE_STYLES } from '@/utils/graphStyles'

// Register layout extension once
cytoscape.use(coseBilkent)

export interface UseCytoscapeOptions {
  container: Ref<HTMLElement | null>
  elements: Ref<ElementDefinition[]>
  onEntitySelect?: (entityId: string) => void
  onRelationshipSelect?: (relId: string) => void
  onDocumentSelect?: (docId: string) => void
  onEntityExpand?: (entityId: string) => void
}

export function useCytoscape(options: UseCytoscapeOptions) {
  const cy = ref<Core | null>(null)

  // Build per-type shape selectors from shared config
  const typeShapeStyles: cytoscape.Stylesheet[] = Object.entries(NODE_STYLES).map(
    ([type, { shape }]) => ({
      selector: `node[type = "${type}"]`,
      style: { 'shape': shape } as any,
    })
  )

  const graphStyle: cytoscape.Stylesheet[] = [
    {
      selector: 'node',
      style: {
        'label': 'data(name)',
        'background-color': 'data(color)',
        'shape': 'ellipse',
        'width': 40,
        'height': 40,
        'font-size': '11px',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'color': '#374151',
        'text-wrap': 'ellipsis',
        'text-max-width': '80px',
      },
    },
    // Per-type shapes (person=ellipse, organization=ellipse, topic=diamond, etc.)
    ...typeShapeStyles,
    {
      selector: 'node[nodeKind = "document"]',
      style: {
        'width': 30,
        'height': 36,
        'font-size': '10px',
        'text-max-width': '100px',
      },
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': '#D1D5DB',
        'target-arrow-color': '#D1D5DB',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(relationship_type)',
        'font-size': '9px',
        'text-rotation': 'autorotate',
        'color': '#9CA3AF',
      },
    },
    {
      selector: ':selected',
      style: {
        'border-width': 3,
        'border-color': '#2563EB',
      },
    },
    {
      selector: 'node.highlighted',
      style: {
        'background-color': '#F59E0B',
        'border-width': 2,
        'border-color': '#D97706',
      },
    },
  ]

  function init() {
    if (!options.container.value) return

    cy.value = cytoscape({
      container: options.container.value,
      elements: options.elements.value,
      style: graphStyle,
      layout: {
        name: 'cose-bilkent',
        animate: 'end',
        animationDuration: 500,
        nodeDimensionsIncludeLabels: true,
      } as any,
      minZoom: 0.2,
      maxZoom: 5,
      wheelSensitivity: 0.3,
    })

    cy.value.on('tap', 'node', (evt) => {
      const nodeId = evt.target.id()
      const nodeKind = evt.target.data('nodeKind')
      if (nodeKind === 'document') {
        options.onDocumentSelect?.(nodeId)
      } else {
        options.onEntitySelect?.(nodeId)
      }
    })

    cy.value.on('tap', 'edge', (evt) => {
      const edgeId = evt.target.id()
      // Strip "rel-" prefix to get the actual relationship ID
      const relId = edgeId.startsWith('rel-') ? edgeId.slice(4) : edgeId
      options.onRelationshipSelect?.(relId)
    })

    cy.value.on('dbltap', 'node', (evt) => {
      const nodeKind = evt.target.data('nodeKind')
      if (nodeKind !== 'document') {
        options.onEntityExpand?.(evt.target.id())
      }
    })

    cy.value.on('tap', (evt) => {
      if (evt.target === cy.value) {
        options.onEntitySelect?.('')
      }
    })
  }

  function addElements(elements: ElementDefinition[]) {
    if (!cy.value) return
    cy.value.add(elements)
    runLayout()
  }

  function runLayout() {
    cy.value?.layout({
      name: 'cose-bilkent',
      animate: 'end',
      animationDuration: 500,
      fit: true,
      nodeDimensionsIncludeLabels: true,
    } as any).run()
  }

  function focusEntity(entityId: string) {
    if (!cy.value) return
    const node = cy.value.getElementById(entityId)
    if (node.length === 0) return
    cy.value.animate({
      center: { eles: node },
      zoom: 2,
    }, { duration: 400 })
    node.select()
  }

  function resetView() {
    cy.value?.fit(undefined, 50)
  }

  function clearGraph() {
    cy.value?.elements().remove()
  }

  watch(options.elements, (newElements) => {
    if (!cy.value) return
    cy.value.elements().remove()
    if (newElements.length > 0) {
      cy.value.add(newElements)
      runLayout()
    }
  }, { deep: true })

  onMounted(() => init())
  onBeforeUnmount(() => {
    cy.value?.destroy()
    cy.value = null
  })

  return {
    cy,
    addElements,
    focusEntity,
    resetView,
    runLayout,
    clearGraph,
  }
}
