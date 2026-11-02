import { createContext, useContext } from 'react'

export const CartContext = createContext(null)
export const money = value => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(value)
export function useCart() { return useContext(CartContext) }
