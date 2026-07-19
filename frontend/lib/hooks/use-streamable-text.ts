import { StreamableValue, readStreamableValue } from 'ai/rsc'
import { useEffect, useRef, useState } from 'react'

export const useStreamableText = (
  content: string | StreamableValue<string>
) => {
  const [rawContent, setRawContent] = useState(
    typeof content === 'string' ? content : ''
  )

  useEffect(() => {
    ;(async () => {
      if (typeof content === 'object') {
        let value = ''
        for await (const delta of readStreamableValue(content)) {
          if (typeof delta === 'string') {
            setRawContent((value = value + delta))
          }
        }
      }
    })()
  }, [content])

  return rawContent
}

// Smooth reveal: decouple network arrival from display. Streamed chunks land
// in a target buffer; a requestAnimationFrame loop reveals the text character
// by character at an adaptive rate, so rendering flows evenly regardless of
// how bursty the chunks arrive over the wire.
const BASE_CPS = 80          // baseline reveal speed, characters per second
const MAX_LAG_SECONDS = 1.2  // never trail the received text by more than this
const DONE_BOOST = 3         // flush faster once the stream has ended

export const useSmoothText = (
  content: string | StreamableValue<string>
) => {
  const [displayText, setDisplayText] = useState(
    typeof content === 'string' ? content : ''
  )
  const targetRef = useRef(typeof content === 'string' ? content : '')
  const shownRef = useRef(typeof content === 'string' ? content.length : 0)
  const doneRef = useRef(typeof content === 'string')

  useEffect(() => {
    if (typeof content === 'string') {
      targetRef.current = content
      shownRef.current = content.length
      doneRef.current = true
      setDisplayText(content)
      return
    }

    let cancelled = false

    ;(async () => {
      let value = ''
      for await (const delta of readStreamableValue(content)) {
        if (cancelled) return
        if (typeof delta === 'string') {
          targetRef.current = value = value + delta
        }
      }
      doneRef.current = true
    })()

    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      if (cancelled) return
      const dt = Math.min((now - last) / 1000, 0.1)
      last = now

      const target = targetRef.current
      const backlog = target.length - shownRef.current

      if (backlog > 0) {
        let rate = Math.max(BASE_CPS, backlog / MAX_LAG_SECONDS)
        if (doneRef.current) rate *= DONE_BOOST
        const step = Math.max(1, Math.floor(rate * dt))
        shownRef.current = Math.min(target.length, shownRef.current + step)
        setDisplayText(target.slice(0, shownRef.current))
      } else if (doneRef.current) {
        return // stream finished and fully revealed: stop the loop
      }

      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
    }
  }, [content])

  return displayText
}
