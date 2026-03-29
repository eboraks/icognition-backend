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

  // Font size presets
  type FontSize = 'small' | 'medium' | 'large'
  const fontSizeConfig = { small: 9, medium: 11, large: 14 }
  const edgeFontSizeConfig = { small: 7, medium: 9, large: 11 }
  const currentFontSize = ref<FontSize>('medium')

  function setFontSize(size: FontSize) {
    currentFontSize.value = size
    if (!cy.value) return
    cy.value.style()
      .selector('node')
      .style('font-size', `${fontSizeConfig[size]}px`)
      .selector('node[type = "document"]')
      .style('font-size', `${fontSizeConfig[size] - 1}px`)
      .selector('edge')
      .style('font-size', `${edgeFontSizeConfig[size]}px`)
      .update()
  }

  // Default cose-bilkent layout options with good spacing
  const coseBilkentDefaults = {
    name: 'cose-bilkent',
    animate: 'end',
    animationDuration: 500,
    nodeDimensionsIncludeLabels: true,
    idealEdgeLength: 120,
    nodeRepulsion: 8000,
    edgeElasticity: 0.45,
    nestingFactor: 0.1,
    gravity: 0.2,
    numIter: 2500,
    tile: true,
    fit: true,
    padding: 30,
  }

  // Build per-type shape + icon selectors from shared config
  const typeShapeStyles: cytoscape.Stylesheet[] = Object.entries(NODE_STYLES).flatMap(
    ([type, { shape, icon }]) => {
      const base: cytoscape.Stylesheet = {
        selector: `node[type = "${type}"]`,
        style: {
          'shape': shape,
          ...(icon ? {
            'background-image': icon,
            'background-fit': 'contain',
            'background-clip': 'none',
            'background-width': '70%',
            'background-height': '70%',
            'background-image-opacity': 0.9,
            'background-opacity': 0,
          } : {}),
        } as any,
      }
      return [base]
    }
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
        'border-color': '#3B82F6',
        'overlay-color': '#3B82F6',
        'overlay-padding': 6,
        'overlay-opacity': 0.15,
        'shadow-blur': 12,
        'shadow-color': '#3B82F6',
        'shadow-offset-x': 0,
        'shadow-offset-y': 0,
        'shadow-opacity': 0.6,
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
    {
      selector: 'node.dimmed',
      style: {
        'opacity': 0.15,
      },
    },
    {
      selector: 'edge.dimmed',
      style: {
        'opacity': 0.08,
      },
    },
    {
      selector: 'edge.highlighted',
      style: {
        'line-color': '#3B82F6',
        'target-arrow-color': '#3B82F6',
        'width': 3,
        'opacity': 1,
        'z-index': 10,
        'font-size': '11px',
        'font-weight': 'bold',
        'color': '#1E40AF',
        'text-background-color': '#DBEAFE',
        'text-background-opacity': 0.9,
        'text-background-padding': '3px',
        'text-background-shape': 'roundrectangle',
        'shadow-blur': 8,
        'shadow-color': '#93C5FD',
        'shadow-offset-x': 0,
        'shadow-offset-y': 0,
        'shadow-opacity': 0.5,
      } as any,
    },
  ]

  function init() {
    if (!options.container.value) return

    cy.value = cytoscape({
      container: options.container.value,
      elements: options.elements.value,
      style: graphStyle,
      layout: coseBilkentDefaults as any,
      minZoom: 0.2,
      maxZoom: 5,
      wheelSensitivity: 0.3,
    })

    // Use tapstart (fires on mousedown) so selection happens immediately,
    // even if the user drags the node afterwards.
    cy.value.on('tapstart', 'node', (evt) => {
      const node = evt.target
      const nodeId = node.id()
      const nodeKind = node.data('nodeKind')

      // Highlight connected edges
      cy.value!.edges().removeClass('highlighted')
      node.connectedEdges().addClass('highlighted')

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
        cy.value!.edges().removeClass('highlighted')
        cy.value!.elements().removeClass('dimmed')
        lastFocusedId = null
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
    runLayoutWithFocus({ ...coseBilkentDefaults })
  }

  // Queue a focus after any running layout completes
  let pendingFocus: string | null = null
  let layoutRunning = false
  let lastFocusedId: string | null = null

  function focusEntity(entityId: string) {
    if (!cy.value) return
    const node = cy.value.getElementById(entityId)
    if (node.length === 0) return

    lastFocusedId = entityId

    if (layoutRunning) {
      pendingFocus = entityId
      return
    }

    focusNodeRadial(entityId)
  }

  /**
   * Re-layout the graph concentrically around a selected node.
   * Center = selected node, ring 1 = direct neighbors, ring 2+ = further out.
   * Nodes beyond ring 2 are dimmed to reduce visual noise.
   */
  function focusNodeRadial(nodeId: string) {
    if (!cy.value) return
    const root = cy.value.getElementById(nodeId)
    if (root.length === 0) return

    // BFS to compute distance from root
    const distMap = new Map<string, number>()
    const bfs = cy.value.elements().bfs({
      roots: root,
      visit: (v, e, u, i, depth) => {
        distMap.set(v.id(), depth)
      },
      directed: false,
    })

    // Assign distance to unreachable nodes
    cy.value.nodes().forEach((n) => {
      if (!distMap.has(n.id())) {
        distMap.set(n.id(), 999)
      }
    })

    const maxVisibleDepth = 3

    // Dim far-away nodes, restore close ones
    cy.value.batch(() => {
      cy.value!.nodes().forEach((n) => {
        const dist = distMap.get(n.id()) ?? 999
        if (dist > maxVisibleDepth) {
          n.addClass('dimmed')
        } else {
          n.removeClass('dimmed')
        }
      })
      cy.value!.edges().forEach((e) => {
        const sDist = distMap.get(e.source().id()) ?? 999
        const tDist = distMap.get(e.target().id()) ?? 999
        if (sDist > maxVisibleDepth || tDist > maxVisibleDepth) {
          e.addClass('dimmed')
        } else {
          e.removeClass('dimmed')
        }
      })
    })

    // Run concentric layout centered on the selected node
    runLayoutWithFocus({
      name: 'concentric',
      concentric: (node: any) => {
        const dist = distMap.get(node.id()) ?? 999
        return dist <= maxVisibleDepth ? (maxVisibleDepth + 1 - dist) * 10 : -10
      },
      levelWidth: () => 1,
      animate: true,
      animationDuration: 500,
      fit: true,
      padding: 60,
      minNodeSpacing: 40,
      startAngle: (3 / 2) * Math.PI,  // top
    })

    root.select()
  }

  function runLayoutWithFocus(layoutOptions: any) {
    if (!cy.value) return
    layoutRunning = true
    const layout = cy.value.layout(layoutOptions)
    layout.on('layoutstop', () => {
      layoutRunning = false
      if (pendingFocus) {
        const id = pendingFocus
        pendingFocus = null
        focusEntity(id)
      }
    })
    layout.run()
  }

  function zoomBy(factor: number) {
    if (!cy.value) return

    // Prefer last focused entity, then selected node, then viewport center
    let centerPos: { x: number; y: number }
    if (lastFocusedId) {
      const focused = cy.value.getElementById(lastFocusedId)
      if (focused.length > 0) {
        centerPos = focused.renderedPosition()
      } else {
        centerPos = { x: cy.value.width() / 2, y: cy.value.height() / 2 }
      }
    } else {
      const selected = cy.value.nodes(':selected')
      centerPos = selected.length > 0
        ? selected.first().renderedPosition()
        : { x: cy.value.width() / 2, y: cy.value.height() / 2 }
    }

    const newZoom = Math.min(5, Math.max(0.2, cy.value.zoom() * factor))
    cy.value.animate({
      zoom: { level: newZoom, renderedPosition: centerPos },
    }, { duration: 200 })
  }

  function zoomIn() { zoomBy(1.3) }
  function zoomOut() { zoomBy(1 / 1.3) }

  function resetView() {
    cy.value?.fit(undefined, 50)
  }

  function clearGraph() {
    cy.value?.elements().remove()
  }

  watch(options.elements, (newElements, oldElements) => {
    if (!cy.value) return

    const currentIds = new Set(cy.value.elements().map((ele) => ele.id()))
    const newIds = new Set(newElements.map((e) => e.data?.id).filter(Boolean))

    // Full reset: if most elements changed (e.g. source filter switch)
    const isFullReset = !oldElements || oldElements.length === 0 || newElements.length === 0
      || (currentIds.size > 0 && [...currentIds].filter((id) => !newIds.has(id)).length > currentIds.size * 0.5)

    if (isFullReset) {
      cy.value.elements().remove()
      if (newElements.length > 0) {
        cy.value.add(newElements)
        runLayoutWithFocus({ ...coseBilkentDefaults })
      }
      return
    }

    // Incremental update: only add new elements, position near neighbors
    const toAdd = newElements.filter((e) => e.data?.id && !currentIds.has(e.data.id))
    const toRemove = [...currentIds].filter((id) => !newIds.has(id))

    if (toRemove.length > 0) {
      cy.value.remove(cy.value.collection(toRemove.map((id) => cy.value!.getElementById(id))))
    }
    if (toAdd.length > 0) {
      const edgesToAdd = toAdd.filter((e) => e.group === 'edges')
      const nodesToAdd = toAdd.filter((e) => e.group === 'nodes')

      // Use startBatch/endBatch so styles are applied after all mutations
      cy.value.startBatch()

      const addedNodes = nodesToAdd.length > 0 ? cy.value.add(nodesToAdd) : cy.value.collection()
      if (edgesToAdd.length > 0) {
        cy.value.add(edgesToAdd)
      }

      // Position new nodes near an existing connected neighbor
      addedNodes.forEach((added) => {
        const nodeId = added.id()
        const connectedEdge = newElements.find(
          (e) => e.group === 'edges' && (e.data?.source === nodeId || e.data?.target === nodeId)
        )
        if (connectedEdge) {
          const neighborId = connectedEdge.data?.source === nodeId
            ? connectedEdge.data?.target
            : connectedEdge.data?.source
          const neighbor = cy.value!.getElementById(neighborId as string)
          if (neighbor.length > 0) {
            const pos = neighbor.position()
            const angle = Math.random() * Math.PI * 2
            const dist = 60 + Math.random() * 40
            added.position({
              x: pos.x + Math.cos(angle) * dist,
              y: pos.y + Math.sin(angle) * dist,
            })
          }
        }
      })

      cy.value.endBatch()

      // Force style recalculation on ALL nodes — covers nodes added in
      // previous watch invocations that may still have stale default styles
      cy.value.nodes().forEach((node) => {
        const color = node.data('color')
        if (color && node.style('background-color') === 'rgb(153,153,153)') {
          node.style('background-color', color)
        }
      })
    }
  }, { deep: true })

  function onKeydown(e: KeyboardEvent) {
    const ctrl = e.ctrlKey || e.metaKey
    if (ctrl && (e.key === '=' || e.key === '+')) {
      e.preventDefault()
      zoomIn()
    } else if (ctrl && e.key === '-') {
      e.preventDefault()
      zoomOut()
    }
  }

  onMounted(() => {
    init()
    window.addEventListener('keydown', onKeydown)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKeydown)
    cy.value?.destroy()
    cy.value = null
  })

  function applyChatContextFilter(entityIds: Set<number>, documentIds: Set<number>) {
    if (!cy.value) return
    const contextNodeIds = new Set<string>()
    for (const id of entityIds) contextNodeIds.add(String(id))
    for (const id of documentIds) contextNodeIds.add(`doc-${id}`)

    // 1-hop bridge: add direct neighbors of context nodes
    const bridgeIds = new Set<string>()
    for (const nodeId of contextNodeIds) {
      const node = cy.value.getElementById(nodeId)
      if (node.length > 0) {
        node.neighborhood().nodes().forEach((n: any) => bridgeIds.add(n.id()))
      }
    }

    const visibleIds = new Set([...contextNodeIds, ...bridgeIds])

    cy.value.batch(() => {
      cy.value!.nodes().forEach((n: any) => {
        if (visibleIds.has(n.id())) {
          n.removeClass('dimmed')
        } else {
          n.addClass('dimmed')
        }
      })
      cy.value!.edges().forEach((e: any) => {
        const srcVisible = visibleIds.has(e.source().id())
        const tgtVisible = visibleIds.has(e.target().id())
        if (srcVisible && tgtVisible) {
          e.removeClass('dimmed')
        } else {
          e.addClass('dimmed')
        }
      })
    })
  }

  function clearChatContextFilter() {
    if (!cy.value) return
    cy.value.elements().removeClass('dimmed')
  }

  return {
    cy,
    addElements,
    focusEntity,
    focusNodeRadial,
    zoomIn,
    zoomOut,
    resetView,
    runLayout,
    clearGraph,
    setFontSize,
    currentFontSize,
    applyChatContextFilter,
    clearChatContextFilter,
  }
}
