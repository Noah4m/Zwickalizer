import { useEffect, useState } from 'react'
import Chat from './Chat.jsx'
import PlotPanel from './PlotPanel.jsx'
import Sidebar from './Sidebar.jsx'

export default function App() {
  const [exampleQuery, setExampleQuery] = useState(null)
  const [currentPlot, setCurrentPlot] = useState(null)
  const [isCompact, setIsCompact] = useState(() => typeof window !== 'undefined' && window.innerWidth < 1120)

  useEffect(() => {
    const onResize = () => setIsCompact(window.innerWidth < 1120)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const layoutStyle = isCompact
    ? {
        display: 'grid',
        gridTemplateColumns: '1fr',
        gridTemplateRows: '220px minmax(0, 1fr) minmax(320px, 0.9fr)',
        height: '100vh',
        overflow: 'hidden',
      }
    : {
        display: 'grid',
        gridTemplateColumns: '220px minmax(0, 1.1fr) minmax(380px, 0.9fr)',
        height: '100vh',
        overflow: 'hidden',
      }

  return (
    <div style={layoutStyle}>
      <Sidebar onSelectExample={setExampleQuery} />
      <Chat
        exampleQuery={exampleQuery}
        onExampleConsumed={() => setExampleQuery(null)}
        onPlotUpdate={setCurrentPlot}
      />
      <PlotPanel plot={currentPlot} />
    </div>
  )
}
