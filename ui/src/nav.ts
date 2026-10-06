import { createContext, useContext } from 'react'

export type Route =
  | { page: 'stores' }
  | { page: 'catalogue' }
  | { page: 'photos' }
  | { page: 'planograms'; fixtureId?: string }
  | { page: 'planogram'; id: string }
  | { page: 'compliance-check'; id: string }
  | { page: 'history' }

export const NavContext = createContext<(route: Route) => void>(() => {})

export function useNav() {
  return useContext(NavContext)
}
