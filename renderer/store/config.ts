/**
 * Config store — manages user configuration state in the renderer
 */

import { create } from 'zustand'

interface ConfigState {
  firstLaunch: boolean
  preset: string
  loaded: boolean
  setFirstLaunch: (v: boolean) => void
  setPreset: (v: string) => void
  setLoaded: (v: boolean) => void
  load: () => Promise<void>
}

export const useConfigStore = create<ConfigState>((set) => ({
  firstLaunch: true,
  preset: 'balanced',
  loaded: false,
  setFirstLaunch: (v) => set({ firstLaunch: v }),
  setPreset: (v) => set({ preset: v }),
  setLoaded: (v) => set({ loaded: v }),
  load: async () => {
    const config = await window.datamoa?.config.get()
    if (config) {
      set({
        firstLaunch: config.first_launch as boolean ?? true,
        preset: config.preset as string ?? 'balanced',
        loaded: true,
      })
    }
  },
}))
