import { createElement, useEffect, useRef, type ReactNode } from 'react'

/* Some components own their disclosure state internally (EvidencePanel's
   Evidence header) or only populate on a user action (RetrievalPreview's
   Retrieve button), with no prop to set. Rendered statically they show only the
   collapsed or empty state, so every variant looks identical.

   This clicks the real control once on mount, so the card shows the component's
   own populated render — the real interaction, not a reimplementation of it.

   Deliberately a .ts file using createElement rather than .tsx: the converter
   treats every <Name>.tsx in this directory as a component preview and warns
   "stale preview: _open" otherwise. */
export function OpenOnMount({
  children,
  selector = 'button',
}: {
  children: ReactNode
  selector?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>(selector)?.click()
  }, [selector])
  return createElement('div', { ref }, children)
}
