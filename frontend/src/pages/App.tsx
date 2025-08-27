import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { Home } from './Home'
import { MapPage } from './MapPage'

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="*" element={<div style={{ padding: 24 }}><p>Not found. <Link to="/">Go home</Link></p></div>} />
      </Routes>
    </BrowserRouter>
  )
}


