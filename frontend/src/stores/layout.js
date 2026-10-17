import { defineStore } from 'pinia'
// The shell remounts on every route change, so the collapse state has to live outside the
// component and survive reloads.
const storageKey = 'monitor-layout'
function readStored() {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || 'null')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}
export const useLayoutStore = defineStore('layout', {
  state: () => {
    const stored = readStored()
    return {
      pureMap: false,
      leftCollapsed: stored.leftCollapsed === true,
      rightCollapsed: stored.rightCollapsed === true,
      filterOpen: stored.filterOpen === true,
    }
  },
  actions: {
    persist() {
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            leftCollapsed: this.leftCollapsed,
            rightCollapsed: this.rightCollapsed,
            filterOpen: this.filterOpen,
          }),
        )
      } catch {
        // Storage unavailable (private mode / quota): keep the in-memory state only.
      }
    },
    togglePureMap() {
      this.pureMap = !this.pureMap
    },
    exitPureMap() {
      this.pureMap = false
    },
    revealRight() {
      this.pureMap = false
      this.rightCollapsed = false
      this.persist()
    },
    toggleLeft() {
      this.leftCollapsed = !this.leftCollapsed
      this.persist()
    },
    toggleRight() {
      this.rightCollapsed = !this.rightCollapsed
      this.persist()
    },
    toggleFilter() {
      this.filterOpen = !this.filterOpen
      this.persist()
    },
  },
})
