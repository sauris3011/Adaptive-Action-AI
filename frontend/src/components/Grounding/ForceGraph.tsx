import { useEffect, useMemo, useRef, useState } from 'react'
import type { GraphNode, GraphView } from '../../lib/api'

/* Force-directed graph (FR-15), hand-rolled in SVG.

   No graph library: the seed graph is ~50 nodes, the simulation below is a
   textbook Fruchterman-Reingold, and a rendering dependency would be the
   largest thing in the bundle for a view this small. It also keeps every colour
   on a design token (FR-12), which a canvas-based library would not.

   The simulation runs on a fixed tick budget rather than to convergence, so the
   layout is deterministic across reloads - a graph that settles differently
   each time is harder to read, not more alive. */

const TICKS = 260
const WIDTH = 900
const HEIGHT = 460

/* Semantic token per node label. Read from CSS variables so the toggle repaints
   the graph with the rest of the app. */
const LABEL_TOKEN: Record<string, string> = {
  Customer: '--accent',
  Account: '--info',
  Merchant: '--warning',
  Transaction: '--success',
  Dispute: '--danger',
  Policy: '--text-muted',
}

export const NODE_LABELS = Object.keys(LABEL_TOKEN)

type Positioned = GraphNode & { x: number; y: number }

function simulate(view: GraphView): Positioned[] {
  const nodes = view.nodes.map((n, i) => {
    /* Deterministic ring seed - same input, same layout, every time. */
    const angle = (i / Math.max(1, view.nodes.length)) * Math.PI * 2
    return {
      ...n,
      x: WIDTH / 2 + Math.cos(angle) * (WIDTH / 3.2),
      y: HEIGHT / 2 + Math.sin(angle) * (HEIGHT / 3.2),
    }
  })
  const index = new Map(nodes.map((n, i) => [n.id, i]))
  const edges = view.links
    .map((l) => [index.get(l.source), index.get(l.target)] as const)
    .filter((e): e is readonly [number, number] => e[0] !== undefined && e[1] !== undefined)

  const area = WIDTH * HEIGHT
  const k = Math.sqrt(area / Math.max(1, nodes.length)) * 0.72
  let temperature = WIDTH / 8

  for (let tick = 0; tick < TICKS; tick++) {
    const dx = new Array(nodes.length).fill(0)
    const dy = new Array(nodes.length).fill(0)

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let vx = nodes[i].x - nodes[j].x
        let vy = nodes[i].y - nodes[j].y
        let dist = Math.hypot(vx, vy) || 0.01
        if (dist < 0.05) {
          vx = (i % 3) - 1
          vy = (j % 3) - 1
          dist = 1
        }
        const force = (k * k) / dist
        dx[i] += (vx / dist) * force
        dy[i] += (vy / dist) * force
        dx[j] -= (vx / dist) * force
        dy[j] -= (vy / dist) * force
      }
    }

    for (const [a, b] of edges) {
      const vx = nodes[a].x - nodes[b].x
      const vy = nodes[a].y - nodes[b].y
      const dist = Math.hypot(vx, vy) || 0.01
      const force = (dist * dist) / k
      dx[a] -= (vx / dist) * force
      dy[a] -= (vy / dist) * force
      dx[b] += (vx / dist) * force
      dy[b] += (vy / dist) * force
    }

    for (let i = 0; i < nodes.length; i++) {
      const dist = Math.hypot(dx[i], dy[i]) || 0.01
      const step = Math.min(dist, temperature)
      nodes[i].x = Math.max(28, Math.min(WIDTH - 28, nodes[i].x + (dx[i] / dist) * step))
      nodes[i].y = Math.max(24, Math.min(HEIGHT - 24, nodes[i].y + (dy[i] / dist) * step))
    }
    temperature *= 0.975
  }
  return nodes
}

/* Keep the nearest `limit` nodes to the root and drop the rest.

   A neighbourhood answer is a comprehension aid: past roughly two dozen nodes
   the picture stops being readable and the honest thing is to say how many were
   left out rather than to draw a hairball. Distance is the right axis to trim
   on because it is the one the question asked about. */
function trim(view: GraphView, limit: number): { view: GraphView; hidden: number } {
  if (view.nodes.length <= limit) return { view, hidden: 0 }

  const kept = [...view.nodes]
    .sort((a, b) => (a.distance ?? 0) - (b.distance ?? 0))
    .slice(0, limit)
  const ids = new Set(kept.map((node) => node.id))
  return {
    view: {
      ...view,
      nodes: kept,
      links: view.links.filter((link) => ids.has(link.source) && ids.has(link.target)),
    },
    hidden: view.nodes.length - kept.length,
  }
}

interface Props {
  view: GraphView
  onSelect?: (node: GraphNode) => void
  selectedId?: string | null
  /* The entity the question was asked about, drawn larger with an accent ring
     so the centre of the answer is findable at a glance. */
  rootId?: string | null
  maxNodes?: number
}

export function ForceGraph({ view: fullView, onSelect, selectedId, rootId, maxNodes }: Props) {
  const { view, hidden } = useMemo(
    () => trim(fullView, maxNodes ?? Number.POSITIVE_INFINITY),
    [fullView, maxNodes],
  )
  const nodes = useMemo(() => simulate(view), [view])
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const [hovered, setHovered] = useState<string | null>(null)
  const wrapper = useRef<HTMLDivElement>(null)

  /* Re-render on theme change: the fills resolve CSS variables at paint time,
     but the legend swatches read them through inline styles. */
  const [, force] = useState(0)
  useEffect(() => {
    const observer = new MutationObserver(() => force((n) => n + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  if (!view.nodes.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-text-subtle">
        The graph is empty. Seed the domain pack to populate it.
      </div>
    )
  }

  const active = hovered ?? selectedId ?? null
  const neighbours = new Set<string>()
  if (active) {
    for (const link of view.links) {
      if (link.source === active) neighbours.add(link.target)
      if (link.target === active) neighbours.add(link.source)
    }
  }

  return (
    <div ref={wrapper} className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full min-w-[640px]"
        role="img"
        aria-label={`Knowledge graph: ${view.nodes.length} nodes, ${view.links.length} relationships`}
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 8 4 L 0 8 z" fill="hsl(var(--border-strong))" />
          </marker>
        </defs>

        {view.links.map((link, i) => {
          const a = byId.get(link.source)
          const b = byId.get(link.target)
          if (!a || !b) return null
          const dimmed = active !== null && link.source !== active && link.target !== active
          return (
            <g key={`${link.source}-${link.target}-${link.label}-${i}`} opacity={dimmed ? 0.15 : 1}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="hsl(var(--border-strong))"
                strokeWidth={1}
                markerEnd="url(#arrow)"
              />
              {active !== null && !dimmed && (
                <text
                  x={(a.x + b.x) / 2}
                  y={(a.y + b.y) / 2 - 4}
                  textAnchor="middle"
                  className="fill-text-subtle text-[9px]"
                >
                  {link.label}
                </text>
              )}
            </g>
          )
        })}

        {nodes.map((node) => {
          const token = LABEL_TOKEN[node.label] ?? '--text-muted'
          const dimmed = active !== null && node.id !== active && !neighbours.has(node.id)
          const isSelected = node.id === selectedId
          const isRoot = rootId != null && node.id === rootId
          return (
            <g
              key={node.id}
              transform={`translate(${node.x} ${node.y})`}
              opacity={dimmed ? 0.2 : 1}
              className="cursor-pointer"
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSelect?.(node)}
            >
              {isRoot && (
                <circle r={13} fill="none" stroke="hsl(var(--accent))" strokeWidth={1.5} />
              )}
              <circle
                r={isRoot ? 9 : isSelected ? 9 : 6}
                fill={`hsl(var(${token}))`}
                stroke="hsl(var(--surface-raised))"
                strokeWidth={isSelected ? 3 : 1.5}
              />
              <text
                y={isRoot ? -19 : -12}
                textAnchor="middle"
                className={`text-[10px] ${isRoot ? 'fill-text font-semibold' : 'fill-text font-medium'}`}
                style={{ pointerEvents: 'none' }}
              >
                {node.caption.length > 22 ? `${node.caption.slice(0, 21)}...` : node.caption}
              </text>
            </g>
          )
        })}
      </svg>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {NODE_LABELS.map((label) => (
          <span key={label} className="flex items-center gap-1.5 text-xs text-text-muted">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: `hsl(var(${LABEL_TOKEN[label]}))` }}
            />
            {label}
          </span>
        ))}
        {hidden > 0 && (
          <span className="text-xs text-text-subtle">+{hidden} more not drawn</span>
        )}
        {view.truncated && (
          <span className="text-xs text-warning">View truncated at the node cap.</span>
        )}
      </div>
    </div>
  )
}
