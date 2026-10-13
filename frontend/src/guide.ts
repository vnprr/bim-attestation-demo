import { createContext, useState } from 'react'

/** Whether the presenter's guide is on. Each view decides itself which hint fits the current state. */
export const GuideOn = createContext(false)

const KEY = 'guide'

/** On by default; the choice is remembered in this browser (if storage is available). */
export function useGuideToggle() {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(KEY) !== 'off'
    } catch {
      return true
    }
  })
  function toggle() {
    setOn(!on)
    try {
      localStorage.setItem(KEY, on ? 'off' : 'on')
    } catch {
      // storage blocked: the toggle still works for this page view
    }
  }
  return { on, toggle }
}
