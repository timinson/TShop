import { createContext, useContext } from 'react'

export const FavoritesContext = createContext(null)
export const useFavorites = () => useContext(FavoritesContext)
